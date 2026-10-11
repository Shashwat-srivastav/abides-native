// Minimal Parquet writer for the two fixed output tables (no Arrow, no compression).
//
// The verifier reads the files with pandas/pyarrow and compares the table contents; it checks the
// file's sha256 only against the value we declare in events.json. So the file does not have to be
// byte-identical to pyarrow's -- it has to be a valid Parquet file that reads back as the same
// table (same column names, order, types, nulls, values and the same "pandas" metadata, which is
// what restores the nullable Int64 dtypes).
//
// Layout: row groups of at most 2^12 rows, one data page (V1) per column chunk, every column
// OPTIONAL like pyarrow writes them. Integer columns are DELTA_BINARY_PACKED (far smaller than
// plain on these tables, so there is less to hash and write); string columns are dictionary
// pages + bit-packed indices.
#pragma once
#include <cstdint>
#include <cstring>
#include <atomic>
#include <algorithm>
#include <functional>
#include <memory>
#include <string>
#include <thread>
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
    // Optional: encode rows [r0, r0 + k) of this column (levels + values) into `body` directly,
    // instead of reading `data`. The physical type still comes from `kind`.
    std::function<void(int64_t r0, int64_t k, std::string& body)> custom;
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

// DELTA_BINARY_PACKED: blocks of 128 deltas in 4 miniblocks of 32 (the layout parquet-cpp itself
// writes). Deltas wrap in the column's own width, as the format requires. `get(i)` yields value i,
// so a column can be encoded straight from the engine's records without materialising it.
template <class T, class U, class G>
inline void delta_pack_fn(std::string& out, G&& get, int64_t n) {
    T prev = n ? (T)get((int64_t)0) : (T)0;
    {
        TW t(out);
        t.varint(128);
        t.varint(4);
        t.varint((uint64_t)n);
        t.varint(TW::zz((int64_t)prev));
    }
    const size_t base = out.size();
    const size_t nblocks = n > 1 ? (size_t)((n - 1 + 127) / 128) : 0;
    // Worst-case room, left uninitialised: a plain resize() would zero (and page in) about 8 bytes
    // per value of which the packed data then uses a fraction. +16: the packer stores 8 bytes at a time.
    out.__resize_and_overwrite(base + nblocks * (10 + 4 + 128 * sizeof(T)) + 16, [&](char* buf, size_t) -> size_t {
        uint8_t* p = (uint8_t*)buf + base;
        U d[128];
        for (int64_t i = 1; i < n;) {
            const int cnt = (int)(n - i < 128 ? n - i : 128);
            T mn = 0;
            for (int j = 0; j < cnt; j++) {
                const T cur = (T)get(i + j);
                const T x = (T)((U)cur - (U)prev);
                prev = cur;
                d[j] = (U)x;
                if (j == 0 || x < mn) mn = x;
            }
            for (uint64_t z = TW::zz((int64_t)mn);;) {
                if (z >= 0x80) { *p++ = (uint8_t)(z | 0x80); z >>= 7; }
                else { *p++ = (uint8_t)z; break; }
            }
            const int nmb = (cnt + 31) / 32;
            uint8_t w[4] = {0, 0, 0, 0};
            for (int k = 0; k < nmb; k++) {
                const int e = cnt < (k + 1) * 32 ? cnt : (k + 1) * 32;
                U mx = 0;
                for (int j = k * 32; j < e; j++) { d[j] = (U)(d[j] - (U)mn); mx |= d[j]; }
                w[k] = mx ? (uint8_t)(64 - __builtin_clzll((uint64_t)mx)) : 0;
            }
            for (int j = cnt; j < nmb * 32; j++) d[j] = 0;
            memcpy(p, w, 4);
            p += 4;
            for (int k = 0; k < nmb; k++) {
                const int bw = w[k];
                if (!bw) continue;
                if (bw <= 56) {  // at most 7 pending bits + 56 new ones fit one 64-bit word
                    uint64_t acc = 0;
                    int bits = 0;
                    for (int j = k * 32; j < k * 32 + 32; j++) {
                        acc |= (uint64_t)d[j] << bits;
                        bits += bw;
                        memcpy(p, &acc, 8);
                        const int nb = bits >> 3;
                        p += nb;
                        acc >>= nb * 8;
                        bits &= 7;
                    }
                    continue;  // 32 * bw bits is a whole number of bytes: nothing pending
                }
                unsigned __int128 acc = 0;
                int bits = 0;
                for (int j = k * 32; j < k * 32 + 32; j++) {
                    acc |= (unsigned __int128)d[j] << bits;
                    bits += bw;
                    if (bits >= 64) {
                        const uint64_t lo = (uint64_t)acc;
                        memcpy(p, &lo, 8);
                        p += 8;
                        acc >>= 64;
                        bits -= 64;
                    }
                }
                if (bits) {  // 32 * bw is a multiple of 32, so exactly 4 bytes remain
                    const uint32_t lo = (uint32_t)acc;
                    memcpy(p, &lo, 4);
                    p += 4;
                }
            }
            i += cnt;
        }
        return (size_t)(p - (uint8_t*)buf);
    });
}

// Definition levels of a column without nulls: one RLE run of k ones, bit width 1.
inline void put_all_present(std::string& lead, int64_t k) {
    std::string d;
    TW t(d);
    t.varint((uint64_t)k << 1);
    d.push_back(1);
    put_u32(lead, (uint32_t)d.size());
    lead += d;
}

// A non-null integer column: levels + delta-packed values.
template <class T, class U, class G>
inline void put_ints(std::string& lead, G&& get, int64_t k) {
    put_all_present(lead, k);
    delta_pack_fn<T, U>(lead, get, k);
}

// A nullable int64 column: `present(i)` says whether row i has a value, `get(i)` yields it.
template <class P, class G>
inline void put_nullable_i64(std::string& lead, P&& present, G&& get, int64_t k) {
    const uint64_t groups8 = (uint64_t)(k + 7) / 8;
    std::string d;
    {
        TW t(d);
        t.varint((groups8 << 1) | 1);  // bit-packed, width 1: an LSB-first bitmap
    }
    const size_t base = d.size();
    d.resize(base + (size_t)groups8, 0);
    uint8_t* bm = (uint8_t*)&d[base];
    // Scratch for the present values, kept per thread: a fresh block per call would be mapped,
    // faulted in and unmapped again for every column chunk.
    static thread_local std::unique_ptr<int64_t[]> tmp;
    static thread_local int64_t tmp_cap = 0;
    if (tmp_cap < k) { tmp.reset(new int64_t[(size_t)k]); tmp_cap = k; }
    int64_t cnt = 0;
    for (int64_t i = 0; i < k; i++) {
        if (present(i)) { bm[i >> 3] |= (uint8_t)(1u << (i & 7)); tmp[(size_t)cnt++] = (int64_t)get(i); }
    }
    if (cnt == k) put_all_present(lead, k);
    else {
        put_u32(lead, (uint32_t)d.size());
        lead += d;
    }
    const int64_t* v = tmp.get();
    delta_pack_fn<int64_t, uint64_t>(lead, [v](int64_t i) { return v[i]; }, cnt);
}

// Dictionary indices of a string column: levels, bit width, one bit-packed run. `code(i)` is the
// dictionary index of row i.
template <class G>
inline void put_codes(std::string& lead, G&& code, int64_t k, int n_names) {
    put_all_present(lead, k);
    const int bw = n_names <= 16 ? 4 : 8;
    const uint64_t groups8 = (uint64_t)(k + 7) / 8;
    lead.push_back((char)bw);
    {
        TW t2(lead);
        t2.varint((groups8 << 1) | 1);
    }
    const size_t base = lead.size();
    lead.resize(base + (size_t)(groups8 * (uint64_t)bw), 0);
    uint8_t* w = (uint8_t*)&lead[base];
    if (bw == 8) {
        for (int64_t i = 0; i < k; i++) w[i] = (uint8_t)code(i);
    } else {
        int64_t i = 0;
        for (; i + 1 < k; i += 2) w[i >> 1] = (uint8_t)((code(i) & 15) | ((code(i + 1) & 15) << 4));
        if (i < k) w[i >> 1] = (uint8_t)(code(i) & 15);
    }
}

struct ChunkMeta {
    int64_t n = 0, bytes = 0, data_off = 0, dict_off = -1;
};

// Writes a file one row group at a time, front to back, through `sink`:
//   sink.put(p, n)   appends n bytes; the memory stays valid until the next sink.flush()
//   sink.flush()     the bytes handed over so far must be consumed before it returns
// add_group() only needs the rows of its own group, so a helper thread can encode, hash and write
// finished rows while the simulation is still producing later ones. Columns named in `deferred`
// (bit c = column c) are left out by add_group() and written by finish() for all groups at once,
// after their values have become final: Parquet locates every column chunk by its own offset, so
// the chunks of one row group need not be adjacent. The bytes depend only on the rows and on the
// fixed group size, never on timing.
template <class Sink>
class Stream {
public:
    static constexpr int64_t kGroupRows = 1 << 12;
    Stream(Sink& sink_, const Col* cols_, int nc_, const char* pandas_md_, uint32_t deferred_ = 0)
        : sink(sink_), cols(cols_), nc(nc_), pandas_md(pandas_md_), deferred(deferred_), parts((size_t)nc_) {
        static const char kMagic[4] = {'P', 'A', 'R', '1'};
        put(kMagic, 4);
    }
    // Rows [r0, r0 + k) become the next row group. Groups must be added in row order.
    void add_group(int64_t r0, int64_t k) {
        std::vector<ChunkMeta> metas((size_t)nc);
        for (int ci = 0; ci < nc; ci++) {
            if (deferred >> ci & 1) continue;
            Part& part = parts[(size_t)ci];
            encode(ci, r0, k, part);
            ChunkMeta& m = metas[(size_t)ci];
            const uint64_t start = off;
            m.n = k;
            if (!part.dict.empty()) {
                m.dict_off = (int64_t)off;
                put(part.dict.data(), part.dict.size());
            }
            m.data_off = (int64_t)off;
            put(part.head.data(), part.head.size());
            put(part.body.data(), part.body.size());
            m.bytes = (int64_t)(off - start);
        }
        groups.push_back(std::move(metas));
        group_r0.push_back(r0);
        group_rows.push_back(k);
        n_rows += k;
        sink.flush();
    }
    // Writes the deferred columns and the footer.
    void finish() {
        std::string tail;
        Part part;
        for (size_t g = 0; g < groups.size(); g++) {
            for (int ci = 0; ci < nc; ci++) {
                if (!(deferred >> ci & 1)) continue;
                encode(ci, group_r0[g], group_rows[g], part);
                ChunkMeta& m = groups[g][(size_t)ci];
                const uint64_t start = off + tail.size();
                m.n = group_rows[g];
                if (!part.dict.empty()) {
                    m.dict_off = (int64_t)(off + tail.size());
                    tail += part.dict;
                }
                m.data_off = (int64_t)(off + tail.size());
                tail += part.head;
                tail += part.body;
                m.bytes = (int64_t)(off + tail.size() - start);
            }
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
                else { t.list(2, 5, 2); t.el_i32(5); t.el_i32(3); }
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
        tail += foot;
        put(tail.data(), tail.size());
        sink.flush();
    }

private:
    struct Part {
        std::string dict;  // dictionary page (header + body), string columns only
        std::string head;  // data page header
        std::string body;  // data page body: definition levels + encoded values
    };
    void put(const char* p, size_t n) { sink.put(p, n); off += n; }
    void encode(int ci, int64_t r0, int64_t k, Part& part) {
        const Col& col = cols[ci];
        part.dict.clear();
        part.head.clear();
        part.body.clear();
        int enc = 5;  // DELTA_BINARY_PACKED
        std::string& lead = part.body;
        if (col.kind == K_DICT) {
            std::string body;
            for (int i = 0; i < col.n_names; i++) {
                put_u32(body, (uint32_t)strlen(col.names[i]));
                body += col.names[i];
            }
            TW t(part.dict);
            t.i32(1, 2);  // DICTIONARY_PAGE
            t.i32(2, (int32_t)body.size());
            t.i32(3, (int32_t)body.size());
            t.begin(7);
            t.i32(1, col.n_names);
            t.i32(2, 0);  // PLAIN
            t.end();
            part.dict.push_back(0);
            part.dict += body;
            enc = 8;  // RLE_DICTIONARY
        }
        if (col.custom) {  // the caller encodes rows [r0, r0 + k) of this column itself
            col.custom(r0, k, lead);
        } else if (col.kind == K_DICT) {
            const int8_t* codes = (const int8_t*)col.data + r0;
            put_codes(lead, [codes](int64_t i) { return (int)codes[i]; }, k, col.n_names);
        } else if (col.kind == K_I64) {
            const int64_t* v = (const int64_t*)col.data + r0;
            put_ints<int64_t, uint64_t>(lead, [v](int64_t i) { return v[i]; }, k);
        } else if (col.kind == K_I32) {
            const int32_t* v = (const int32_t*)col.data + r0;
            put_ints<int32_t, uint32_t>(lead, [v](int64_t i) { return v[i]; }, k);
        } else {  // K_I64_NULLABLE
            const int8_t* pr = col.present + r0;
            const int64_t* v = (const int64_t*)col.data + r0;
            put_nullable_i64(lead, [pr](int64_t i) { return pr[i] != 0; }, [v](int64_t i) { return v[i]; }, k);
        }
        TW t(part.head);
        t.i32(1, 0);  // DATA_PAGE
        t.i32(2, (int32_t)part.body.size());
        t.i32(3, (int32_t)part.body.size());
        t.begin(5);
        t.i32(1, (int32_t)k);
        t.i32(2, enc);
        t.i32(3, 3);  // definition levels: RLE
        t.i32(4, 3);  // repetition levels: RLE (none present)
        t.end();
        part.head.push_back(0);
    }

    Sink& sink;
    const Col* cols;
    int nc;
    const char* pandas_md;
    uint32_t deferred;
    std::vector<Part> parts;  // reused for every group
    std::vector<std::vector<ChunkMeta>> groups;
    std::vector<int64_t> group_r0, group_rows;
    int64_t n_rows = 0;
    uint64_t off = 0;
};

}  // namespace pqf
