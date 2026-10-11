// Minimal Parquet writer for the two fixed output tables (no Arrow, no compression).
//
// The verifier reads the files with pandas/pyarrow and compares the table contents; it checks the
// file's sha256 only against the value we declare in events.json. So the file does not have to be
// byte-identical to pyarrow's -- it has to be a valid Parquet file that reads back as the same
// table (same column names, order, types, nulls, values and the same "pandas" metadata, which is
// what restores the nullable Int64 dtypes).
//
// Layout: row groups of at most 2^20 rows, one data page (V1) per column chunk, every column
// OPTIONAL like pyarrow writes them. int64/int32 are PLAIN and are written straight from the
// engine's column buffers (no copy); string columns are dictionary pages + bit-packed indices.
#pragma once
#include <cstdint>
#include <cstring>
#include <deque>
#include <string>
#include <vector>

namespace pqf {

enum Kind { K_I64, K_I32, K_DICT, K_I64_NULLABLE };

struct Col {
    const char* name;
    Kind kind;
    const void* data;                      // int64_t[] / int32_t[] / int8_t codes[]
    const int8_t* present = nullptr;       // K_I64_NULLABLE: 1 where the value is present
    const char* const* names = nullptr;    // K_DICT
    int n_names = 0;
};

struct Seg {
    const uint8_t* p;
    size_t n;
};

struct File {
    std::deque<std::string> own;  // small owned pieces; deque keeps their addresses stable
    std::vector<Seg> segs;
    uint64_t size = 0;
    void add_own(std::string&& s) {
        own.push_back(std::move(s));
        segs.push_back({(const uint8_t*)own.back().data(), own.back().size()});
        size += own.back().size();
    }
    void add_ref(const void* p, size_t n) {
        if (!n) return;
        segs.push_back({(const uint8_t*)p, n});
        size += n;
    }
};

// ---- Thrift compact protocol
struct TW {
    std::string& o;
    std::vector<int> st;
    int last = 0;
    explicit TW(std::string& out) : o(out) {}
    void varint(uint64_t v) {
        while (v >= 0x80) { o.push_back((char)(v | 0x80)); v >>= 7; }
        o.push_back((char)v);
    }
    static uint64_t zz(int64_t v) { return ((uint64_t)v << 1) ^ (uint64_t)(v >> 63); }
    void field(int id, int type) {
        int d = id - last;
        if (d > 0 && d <= 15) o.push_back((char)((d << 4) | type));
        else { o.push_back((char)type); varint(zz(id)); }
        last = id;
    }
    void i32(int id, int32_t v) { field(id, 5); varint(zz(v)); }
    void i64(int id, int64_t v) { field(id, 6); varint(zz(v)); }
    void str(int id, const char* s, size_t n) { field(id, 8); varint(n); o.append(s, n); }
    void str(int id, const std::string& s) { str(id, s.data(), s.size()); }
    void begin(int id) { field(id, 12); st.push_back(last); last = 0; }
    void end() { o.push_back(0); last = st.back(); st.pop_back(); }
    void list(int id, int elem_type, size_t n) {
        field(id, 9);
        if (n < 15) o.push_back((char)((n << 4) | elem_type));
        else { o.push_back((char)(0xF0 | elem_type)); varint(n); }
    }
    // list elements
    void el_i32(int32_t v) { varint(zz(v)); }
    void el_str(const char* s) { size_t n = strlen(s); varint(n); o.append(s, n); }
    void el_begin() { st.push_back(last); last = 0; }
    void el_end() { o.push_back(0); last = st.back(); st.pop_back(); }
};

inline void put_u32(std::string& s, uint32_t v) { s.append((const char*)&v, 4); }

struct ChunkMeta {
    int64_t n = 0, bytes = 0, data_off = 0, dict_off = -1;
};

// Builds the whole file as a list of segments. `scratch` receives compacted nullable columns.
inline void build(File& f, const Col* cols, int nc, int64_t n_rows, const char* pandas_md,
                  std::deque<std::vector<int64_t>>& scratch) {
    const int64_t RG = 1 << 20;
    f.add_own(std::string("PAR1"));
    std::vector<std::vector<ChunkMeta>> groups;
    std::vector<int64_t> group_rows;
    for (int64_t r0 = 0; r0 < n_rows; r0 += RG) {
        const int64_t k = n_rows - r0 < RG ? n_rows - r0 : RG;
        std::vector<ChunkMeta> metas((size_t)nc);
        for (int c = 0; c < nc; c++) {
            const Col& col = cols[c];
            ChunkMeta& m = metas[(size_t)c];
            const uint64_t start = f.size;
            m.n = k;
            int enc = 0;                 // PLAIN
            std::string lead;            // definition levels (+ dictionary indices)
            const void* ref = nullptr;   // zero-copy values
            size_t ref_bytes = 0;

            auto all_present = [&] {     // one RLE run of k ones, bit width 1
                std::string d;
                TW t(d);
                t.varint((uint64_t)k << 1);
                d.push_back(1);
                put_u32(lead, (uint32_t)d.size());
                lead += d;
            };

            if (col.kind == K_DICT) {
                std::string body;
                for (int i = 0; i < col.n_names; i++) {
                    put_u32(body, (uint32_t)strlen(col.names[i]));
                    body += col.names[i];
                }
                std::string page;
                TW t(page);
                t.i32(1, 2);  // DICTIONARY_PAGE
                t.i32(2, (int32_t)body.size());
                t.i32(3, (int32_t)body.size());
                t.begin(7);
                t.i32(1, col.n_names);
                t.i32(2, 0);  // PLAIN
                t.end();
                page.push_back(0);
                page += body;
                m.dict_off = (int64_t)f.size;
                f.add_own(std::move(page));

                all_present();
                enc = 8;  // RLE_DICTIONARY
                const int8_t* codes = (const int8_t*)col.data + r0;
                const int bw = col.n_names <= 16 ? 4 : 8;
                const uint64_t groups8 = (uint64_t)(k + 7) / 8;
                lead.push_back((char)bw);
                {
                    TW t2(lead);
                    t2.varint((groups8 << 1) | 1);  // one bit-packed run
                }
                const size_t base = lead.size();
                const size_t nbytes = (size_t)(groups8 * (uint64_t)bw);
                lead.resize(base + nbytes, 0);
                uint8_t* w = (uint8_t*)&lead[base];
                if (bw == 8) memcpy(w, codes, (size_t)k);
                else {
                    int64_t i = 0;
                    for (; i + 1 < k; i += 2) w[i >> 1] = (uint8_t)((codes[i] & 15) | ((codes[i + 1] & 15) << 4));
                    if (i < k) w[i >> 1] = (uint8_t)(codes[i] & 15);
                }
            } else if (col.kind == K_I64) {
                all_present();
                ref = (const int64_t*)col.data + r0;
                ref_bytes = (size_t)k * 8;
            } else if (col.kind == K_I32) {
                all_present();
                ref = (const int32_t*)col.data + r0;
                ref_bytes = (size_t)k * 4;
            } else {  // K_I64_NULLABLE
                const int8_t* pr = col.present + r0;
                const int64_t* v = (const int64_t*)col.data + r0;
                int64_t cnt = 0;
                for (int64_t i = 0; i < k; i++) cnt += pr[i] != 0;
                if (cnt == k) {
                    all_present();
                    ref = v;
                    ref_bytes = (size_t)k * 8;
                } else {
                    const uint64_t groups8 = (uint64_t)(k + 7) / 8;
                    std::string d;
                    {
                        TW t(d);
                        t.varint((groups8 << 1) | 1);  // bit-packed, width 1: an LSB-first bitmap
                    }
                    const size_t base = d.size();
                    d.resize(base + (size_t)groups8, 0);
                    uint8_t* bm = (uint8_t*)&d[base];
                    scratch.emplace_back((size_t)cnt);
                    int64_t* out = scratch.back().data();
                    int64_t w = 0;
                    for (int64_t i = 0; i < k; i++) {
                        if (pr[i]) { bm[i >> 3] |= (uint8_t)(1u << (i & 7)); out[w++] = v[i]; }
                    }
                    put_u32(lead, (uint32_t)d.size());
                    lead += d;
                    ref = out;
                    ref_bytes = (size_t)cnt * 8;
                }
            }

            const size_t body_size = lead.size() + ref_bytes;
            std::string page;
            TW t(page);
            t.i32(1, 0);  // DATA_PAGE
            t.i32(2, (int32_t)body_size);
            t.i32(3, (int32_t)body_size);
            t.begin(5);
            t.i32(1, (int32_t)k);
            t.i32(2, enc);
            t.i32(3, 3);  // definition levels: RLE
            t.i32(4, 3);  // repetition levels: RLE (none present)
            t.end();
            page.push_back(0);
            page += lead;
            m.data_off = (int64_t)f.size;
            f.add_own(std::move(page));
            f.add_ref(ref, ref_bytes);
            m.bytes = (int64_t)(f.size - start);
        }
        groups.push_back(std::move(metas));
        group_rows.push_back(k);
    }

    std::string foot;
    TW t(foot);
    t.i32(1, 2);  // format version 2.x
    t.list(2, 12, (size_t)nc + 1);
    t.el_begin();
    t.str(4, "schema", 6);
    t.i32(5, nc);
    t.el_end();
    for (int c = 0; c < nc; c++) {
        const Col& col = cols[c];
        t.el_begin();
        t.i32(1, col.kind == K_I32 ? 1 : col.kind == K_DICT ? 6 : 2);  // INT32 / BYTE_ARRAY / INT64
        t.i32(3, 1);                                                    // OPTIONAL
        t.str(4, col.name, strlen(col.name));
        if (col.kind == K_DICT) {
            t.i32(6, 0);   // converted type UTF8
            t.begin(10);   // LogicalType
            t.begin(1);    // STRING
            t.end();
            t.end();
        }
        t.el_end();
    }
    t.i64(3, n_rows);
    t.list(4, 12, groups.size());
    for (size_t g = 0; g < groups.size(); g++) {
        t.el_begin();
        t.list(1, 12, (size_t)nc);
        int64_t total = 0;
        for (int c = 0; c < nc; c++) {
            const Col& col = cols[c];
            const ChunkMeta& m = groups[g][(size_t)c];
            total += m.bytes;
            t.el_begin();
            t.i64(2, m.dict_off >= 0 ? m.dict_off : m.data_off);  // file_offset
            t.begin(3);
            t.i32(1, col.kind == K_I32 ? 1 : col.kind == K_DICT ? 6 : 2);
            if (col.kind == K_DICT) { t.list(2, 5, 3); t.el_i32(0); t.el_i32(3); t.el_i32(8); }
            else { t.list(2, 5, 2); t.el_i32(0); t.el_i32(3); }
            t.list(3, 8, 1);
            t.el_str(col.name);
            t.i32(4, 0);  // UNCOMPRESSED
            t.i64(5, m.n);
            t.i64(6, m.bytes);
            t.i64(7, m.bytes);
            t.i64(9, m.data_off);
            if (m.dict_off >= 0) t.i64(11, m.dict_off);
            t.end();
            t.el_end();
        }
        t.i64(2, total);
        t.i64(3, group_rows[g]);
        t.el_end();
    }
    t.list(5, 12, 1);
    t.el_begin();
    t.str(1, "pandas", 6);
    t.str(2, pandas_md, strlen(pandas_md));
    t.el_end();
    t.str(6, "t3native version 1.0.0", 22);
    foot.push_back(0);
    put_u32(foot, (uint32_t)foot.size());
    foot += "PAR1";
    f.add_own(std::move(foot));
}

}  // namespace pqf
