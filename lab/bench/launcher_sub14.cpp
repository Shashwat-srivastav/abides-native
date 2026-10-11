// `simulate` without Python: parse the scenario, run the native engine, write trace.parquet /
// message_trace.parquet / events.json. The whole-container time is what is ranked, and interpreter
// start-up plus the numpy/pyarrow imports cost far more than a typical simulation.
//
// The Parquet files are written by a small built-in writer (pq_fast.hpp): the verifier compares
// table contents, not file bytes, and encoding through libarrow cost more than the simulation
// itself. The files read back as the same tables the Python writer (t3native/writer.py) produces.
//
// Anything this program is not certain about (unusual JSON types, values outside the certified
// domain, an empty trace, a latency draw that would round differently under numpy's log) makes it
// exec the Python entry point, which is exact for every input (native engine or ABIDES reference).
#include "engine.cpp"

#include "pq_fast.hpp"
#include "sha256.hpp"

#include <array>
#include <malloc.h>
#include <cerrno>
#include <cfloat>
#include <sys/resource.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/uio.h>

namespace {

struct Fallback : std::runtime_error {
    using std::runtime_error::runtime_error;
};

// ------------------------------------------------------------------ minimal JSON
struct JV {
    enum T { Null, Bool, Num, Str, Arr, Obj } t = Null;
    bool b = false;
    std::string s;  // string value, or the number token
    std::vector<JV> a;
    std::vector<std::pair<std::string, JV>> o;
    const JV* get(const char* k) const {  // last duplicate wins, like Python's dict
        const JV* r = nullptr;
        if (t == Obj)
            for (auto& kv : o)
                if (kv.first == k) r = &kv.second;
        return r;
    }
};

struct Parser {
    const char* p;
    const char* e;
    void ws() { while (p < e && (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')) p++; }
    [[noreturn]] void bad(const char* m) { throw Fallback(std::string("json: ") + m); }
    std::string str() {
        std::string out;
        p++;  // opening quote
        for (;;) {
            if (p >= e) bad("unterminated string");
            unsigned char ch = (unsigned char)*p++;
            if (ch == '"') return out;
            if (ch == '\\') {
                if (p >= e) bad("bad escape");
                char x = *p++;
                switch (x) {
                    case '"': out += '"'; break;
                    case '\\': out += '\\'; break;
                    case '/': out += '/'; break;
                    case 'b': out += '\b'; break;
                    case 'f': out += '\f'; break;
                    case 'n': out += '\n'; break;
                    case 'r': out += '\r'; break;
                    case 't': out += '\t'; break;
                    case 'u': {  // decode to UTF-8, as json.loads does, so keys and values compare correctly
                        auto hex4 = [&]() -> unsigned {
                            if (e - p < 4) bad("bad \\u");
                            unsigned v = 0;
                            for (int i = 0; i < 4; i++) {
                                const char h = *p++;
                                v <<= 4;
                                if (h >= '0' && h <= '9') v |= (unsigned)(h - '0');
                                else if (h >= 'a' && h <= 'f') v |= (unsigned)(h - 'a' + 10);
                                else if (h >= 'A' && h <= 'F') v |= (unsigned)(h - 'A' + 10);
                                else bad("bad \\u");
                            }
                            return v;
                        };
                        unsigned cp = hex4();
                        if (cp >= 0xD800 && cp <= 0xDBFF) {  // high surrogate: needs its partner
                            if (e - p < 6 || p[0] != '\\' || p[1] != 'u') bad("lone surrogate");
                            p += 2;
                            const unsigned lo = hex4();
                            if (lo < 0xDC00 || lo > 0xDFFF) bad("lone surrogate");
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                        } else if (cp >= 0xDC00 && cp <= 0xDFFF) bad("lone surrogate");
                        if (cp < 0x80) out += (char)cp;
                        else if (cp < 0x800) { out += (char)(0xC0 | (cp >> 6)); out += (char)(0x80 | (cp & 0x3F)); }
                        else if (cp < 0x10000) { out += (char)(0xE0 | (cp >> 12)); out += (char)(0x80 | ((cp >> 6) & 0x3F)); out += (char)(0x80 | (cp & 0x3F)); }
                        else { out += (char)(0xF0 | (cp >> 18)); out += (char)(0x80 | ((cp >> 12) & 0x3F)); out += (char)(0x80 | ((cp >> 6) & 0x3F)); out += (char)(0x80 | (cp & 0x3F)); }
                        break;
                    }
                    default: bad("bad escape");
                }
            } else {
                if (ch < 0x20) bad("control character in string");
                out += (char)ch;
            }
        }
    }
    JV value(int depth) {
        if (depth > 64) bad("too deep");
        ws();
        if (p >= e) bad("eof");
        JV v;
        char ch = *p;
        if (ch == '{') {
            v.t = JV::Obj;
            p++;
            ws();
            if (p < e && *p == '}') { p++; return v; }
            for (;;) {
                ws();
                if (p >= e || *p != '"') bad("key");
                std::string k = str();
                ws();
                if (p >= e || *p != ':') bad("colon");
                p++;
                v.o.emplace_back(std::move(k), value(depth + 1));
                ws();
                if (p < e && *p == ',') { p++; continue; }
                if (p < e && *p == '}') { p++; return v; }
                bad("object");
            }
        }
        if (ch == '[') {
            v.t = JV::Arr;
            p++;
            ws();
            if (p < e && *p == ']') { p++; return v; }
            for (;;) {
                v.a.push_back(value(depth + 1));
                ws();
                if (p < e && *p == ',') { p++; continue; }
                if (p < e && *p == ']') { p++; return v; }
                bad("array");
            }
        }
        if (ch == '"') { v.t = JV::Str; v.s = str(); return v; }
        if (e - p >= 4 && !memcmp(p, "true", 4)) { v.t = JV::Bool; v.b = true; p += 4; return v; }
        if (e - p >= 5 && !memcmp(p, "false", 5)) { v.t = JV::Bool; v.b = false; p += 5; return v; }
        if (e - p >= 4 && !memcmp(p, "null", 4)) { p += 4; return v; }
        // number: strict JSON grammar (NaN / Infinity, which Python accepts, go to the fallback)
        const char* q = p;
        if (q < e && *q == '-') q++;
        if (q >= e || *q < '0' || *q > '9') bad("value");
        if (*q == '0') q++;
        else while (q < e && *q >= '0' && *q <= '9') q++;
        if (q < e && *q == '.') {
            q++;
            if (q >= e || *q < '0' || *q > '9') bad("fraction");
            while (q < e && *q >= '0' && *q <= '9') q++;
        }
        if (q < e && (*q == 'e' || *q == 'E')) {
            q++;
            if (q < e && (*q == '+' || *q == '-')) q++;
            if (q >= e || *q < '0' || *q > '9') bad("exponent");
            while (q < e && *q >= '0' && *q <= '9') q++;
        }
        v.t = JV::Num;
        v.s.assign(p, q);
        p = q;
        return v;
    }
};

// Python-semantics accessors. Only the plain cases are handled; everything else is a Fallback.
bool is_int_token(const std::string& s) { return s.find_first_of(".eE") == std::string::npos; }
int64_t as_int(const JV& v) {  // int(x) for a JSON number
    if (v.t != JV::Num) throw Fallback("non-number where int expected");
    if (!is_int_token(v.s)) {
        // json.loads gives a float here and int(float) truncates toward zero. strtod is correctly
        // rounded like Python's float parser; values that int64 cannot hold exactly are left to Python.
        errno = 0;
        char* fend = nullptr;
        const double x = strtod(v.s.c_str(), &fend);
        if (*fend || !(x == x) || x >= 9.0e18 || x <= -9.0e18) throw Fallback("float outside the int64-safe range where int expected");
        return (int64_t)x;
    }
    errno = 0;
    char* end = nullptr;
    long long r = strtoll(v.s.c_str(), &end, 10);
    if (errno || *end) throw Fallback("integer out of int64 range");
    return (int64_t)r;
}
double as_float(const JV& v) {  // float(x) for a JSON number (strtod and Python both round correctly)
    if (v.t != JV::Num) throw Fallback("non-number where float expected");
    char* end = nullptr;
    double r = strtod(v.s.c_str(), &end);
    if (*end || !std::isfinite(r)) throw Fallback("float out of range");
    return r;
}
int64_t get_int(const JV& o, const char* k, int64_t dflt) { const JV* v = o.get(k); return v ? as_int(*v) : dflt; }
double get_float(const JV& o, const char* k, double dflt) { const JV* v = o.get(k); return v ? as_float(*v) : dflt; }
const JV& need(const JV& o, const char* k) {
    const JV* v = o.get(k);
    if (!v) throw Fallback(std::string("missing key ") + k);
    return *v;
}
const JV& need_obj(const JV& o, const char* k) {
    const JV& v = need(o, k);
    if (v.t != JV::Obj) throw Fallback(std::string(k) + " is not an object");
    return v;
}
static const JV kEmptyObj = [] { JV v; v.t = JV::Obj; return v; }();
const JV& params_of(const JV& o) {  // x.get("params", {})
    const JV* v = o.get("params");
    if (!v) return kEmptyObj;
    if (v->t != JV::Obj) throw Fallback("params is not an object");
    return *v;
}

const int64_t DATE_NS = 1612483200000000000LL;
const int64_t MKT_OPEN_OFFSET_NS = 34200000000000LL;
const int64_t ONE_SECOND_NS = 1000000000LL;
const int64_t ORACLE_CLOSE_OFFSET_NS = 57600000000000LL;
const int64_t P60 = 1LL << 60, P61 = 1LL << 61, BIG = 1LL << 52;

int64_t interval_ns(const JV& p) {
    int64_t v;
    if (const JV* r = p.get("rebalance_interval_ns")) {
        v = as_int(*r);
    } else {
        double hz = get_float(p, "arrival_rate_hz", 1.0);
        if (hz > 0) {
            double q = 1e9 / hz;
            if (!(q < 9.0e18)) throw Fallback("interval overflow");
            v = (int64_t)q;  // int() truncation
        } else {
            v = 1000000000LL;
        }
    }
    return v < 1 ? 1 : v;
}

struct Built {
    int64_t ci[15];
    double cf[11];
    std::vector<int64_t> ai;
    std::vector<double> af;
    int64_t seed;
    std::string scenario_id;
};

// native_sim.build_native_config + _check_domain, for plainly-typed scenarios.
Built build(const JV& sc, bool has_seed_override, int64_t seed_override) {
    if (sc.t != JV::Obj) throw Fallback("scenario is not an object");
    Built B;
    const JV& sid = need(sc, "scenario_id");
    if (sid.t != JV::Str) throw Fallback("scenario_id is not a string");
    for (unsigned char ch : sid.s)
        if (ch < 0x20 || ch > 0x7e || ch == '"' || ch == '\\') throw Fallback("scenario_id needs JSON escaping");
    B.scenario_id = sid.s;
    int64_t seed = has_seed_override ? seed_override : as_int(need(sc, "seed"));
    if (seed < 0 || seed > 4294967295LL) throw Fallback("seed outside numpy legacy range");
    B.seed = seed;

    const JV& ex = need_obj(sc, "exchange_config");
    bool proto = false;
    if (const JV* v = ex.get("protocol_enforcement")) {
        if (v->t != JV::Bool) throw Fallback("protocol_enforcement is not a bool");
        proto = v->b;
    }
    int stp_code = 0;
    if (proto) {
        if (const JV* v = ex.get("stp_policy")) {
            if (v->t == JV::Str) { if (!v->s.empty()) stp_code = (v->s == "cancel_oldest") ? 2 : 1; }
            else if (v->t != JV::Null) throw Fallback("stp_policy type");
        }
    }
    int64_t ack_delay = proto ? get_int(ex, "ack_delay_ns", 0) : 0;
    int64_t compute_delay = proto ? get_int(ex, "compute_delay_ns", 0) : 0;

    const JV& op = params_of(need_obj(sc, "oracle_config"));
    int64_t reference_price = get_int(op, "initial_price", 100000);
    int64_t horizon = as_int(need(sc, "horizon_ns"));
    if (horizon > P60 || horizon < -P60) throw Fallback("horizon outside int64-safe range");
    const int64_t mkt_open = DATE_NS + MKT_OPEN_OFFSET_NS;
    const int64_t mkt_close = mkt_open + horizon;
    double kappa_per_s = get_float(op, "kappa", 0.0);
    double kappa = kappa_per_s > 0 ? kappa_per_s / 1e9 : 1.67e-16;
    double rate_per_s = get_float(op, "jump_intensity", 0.0);
    double ms_lambda = rate_per_s > 0 ? rate_per_s / 1e9 : 2.77778e-18;
    double fund_vol = get_float(op, "sigma", 5e-5);
    double ms_mean = get_float(op, "jump_sigma", 0.0);
    if (ms_mean == 0.0) ms_mean = 1000.0;  // `float(x) or 1000.0`
    bool has_sj = false;
    int64_t sj_time = 0, sj_mag = 0;
    if (const JV* sj = op.get("scheduled_jump")) {
        if (sj->t == JV::Obj) {
            if (!sj->o.empty()) {
                int64_t t = as_int(need(*sj, "time_ns"));
                if (t > P60 || t < -P60) throw Fallback("scheduled jump time out of range");
                sj_time = mkt_open + t;
                sj_mag = as_int(need(*sj, "magnitude"));
                has_sj = true;
            }
        } else if (sj->t != JV::Null) {
            throw Fallback("scheduled_jump type");
        }
    }

    const JV* lc = sc.get("latency_config");
    if (!lc || lc->t != JV::Obj || lc->o.empty()) throw Fallback("no latency_config");
    const JV& lp = params_of(*lc);
    std::string model = "deterministic";
    if (const JV* m = lc->get("model")) {
        if (m->t != JV::Str) throw Fallback("latency model type");
        model = m->s;
    }
    int lat_code = model == "log_normal" ? 1 : model == "uniform" ? 2 : model == "pareto" ? 3 : 0;
    double mean_ns = get_float(lp, "mean_ns", 0.0);
    // The reference uses numpy's log here; std::log may differ in the last bits on some CPUs. Runs in
    // which that could matter are detected by the engine (t3_lat_ambiguous) and redone in Python.
    double lat_mu = mean_ns > 0 ? std::log(mean_ns) : 0.0;
    double lsig = get_float(lp, "sigma", 0.0), lmin = get_float(lp, "min_ns", 0.0);
    double lmax = get_float(lp, "max_ns", 1e12), alpha = get_float(lp, "alpha", 1.5);

    const JV& agents = need(sc, "agent_configs");
    if (agents.t != JV::Arr) throw Fallback("agent_configs is not a list");
    for (const JV& ac : agents.a) {
        if (ac.t != JV::Obj) throw Fallback("agent config is not an object");
        const JV& ty = need(ac, "agent_type");
        if (ty.t != JV::Str) throw Fallback("agent_type type");
        int kind = ty.s == "NoiseTrader" ? 1 : ty.s == "MarketMaker" ? 2 : ty.s == "ValueTrader" ? 3 : ty.s == "MomentumTrader" ? 4 : 0;
        if (!kind) throw Fallback("agent type " + ty.s);
        const JV& p = params_of(ac);
        int64_t ri[8] = {kind, interval_ns(p), 0, 0, 0, 0, 0, 0};
        double rf[4] = {0.0, 0.0, 1000.0, 0.0};
        if (kind == 1) {
            rf[0] = get_float(p, "order_size_mean", 10);
            rf[1] = get_float(p, "order_size_std", 2);
            ri[2] = get_int(p, "price_offset_ticks", 5);
            ri[3] = reference_price;
        } else if (kind == 2) {
            ri[4] = std::max<int64_t>(2, get_int(p, "spread_ticks", 2));
            ri[5] = std::max<int64_t>(1, get_int(p, "depth_levels", 3));
            ri[6] = std::max<int64_t>(1, get_int(p, "size_per_level", 10));
            ri[3] = reference_price;
        } else if (kind == 3) {
            rf[0] = get_float(p, "order_size_mean", 25);
            ri[7] = get_int(p, "threshold_ticks", 2);
        } else {
            rf[0] = get_float(p, "order_size_mean", 15);
            ri[7] = get_int(p, "threshold_ticks", 2);
            rf[3] = (double)std::max<int64_t>(1, get_int(p, "lookback", 5));
        }
        // _check_domain, per agent row
        if (ri[1] > P60) throw Fallback("wake interval outside int64-safe range");
        if (std::fabs(rf[0]) > 1e12 || std::fabs(rf[1]) > 1e11 || ri[7] > BIG || ri[7] < -BIG || rf[3] > 1e9)
            throw Fallback("agent parameter outside exact range");
        if (kind == 1 && (rf[1] < 0 || ri[2] < 0 || ri[2] > 2147483646LL)) throw Fallback("noise trader parameter");
        if (kind == 2 && (ri[4] > BIG || ri[5] > 1000000 || ri[6] > BIG)) throw Fallback("market-maker parameter");
        int64_t count = as_int(need(ac, "count"));
        if (count > 60000) throw Fallback("too many agents");
        for (int64_t i = 0; i < count; i++) {
            B.ai.insert(B.ai.end(), ri, ri + 8);
            B.af.insert(B.af.end(), rf, rf + 4);
        }
        if (B.ai.size() / 8 > 60000) throw Fallback("too many agents");
    }

    // _check_domain, scalars
    if (compute_delay < 0) throw Fallback("negative exchange computation delay");
    if (ack_delay > P60 || ack_delay < -P60 || compute_delay > P60) throw Fallback("time value outside int64-safe range");
    if (reference_price > BIG || reference_price < -BIG || sj_mag > BIG || sj_mag < -BIG) throw Fallback("price outside exact range");
    if (model == "log_normal" && lsig < 0) throw Fallback("negative log_normal sigma");
    if (model == "pareto" && !(alpha > 0)) throw Fallback("non-positive pareto alpha");
    if (std::fabs(lmin) > (double)P60 || std::fabs(lmax) > (double)P60 || std::fabs(mean_ns) > (double)P60)
        throw Fallback("latency bound outside int64-safe range");

    int64_t ci[15] = {seed, DATE_NS, mkt_close + ONE_SECOND_NS, mkt_open, mkt_close, 50, ack_delay, compute_delay,
                      stp_code, reference_price, has_sj ? 1 : 0, sj_time, sj_mag, lat_code, DATE_NS + ORACLE_CLOSE_OFFSET_NS};
    double cf[11] = {kappa, fund_vol, ms_lambda, ms_mean, 50000.0, mean_ns, lsig, lmin, lmax, alpha, lat_mu};
    memcpy(B.ci, ci, sizeof ci);
    memcpy(B.cf, cf, sizeof cf);
    return B;
}

// ------------------------------------------------------------------ parquet (pyarrow-identical)
const char* TRACE_MD =
    "{\"index_columns\": [], \"column_indexes\": [], \"columns\": ["
    "{\"name\": \"t_ns\", \"field_name\": \"t_ns\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"agent_id\", \"field_name\": \"agent_id\", \"pandas_type\": \"int32\", \"numpy_type\": \"int32\", \"metadata\": null}, "
    "{\"name\": \"msg_type\", \"field_name\": \"msg_type\", \"pandas_type\": \"unicode\", \"numpy_type\": \"string\", \"metadata\": null}, "
    "{\"name\": \"side\", \"field_name\": \"side\", \"pandas_type\": \"unicode\", \"numpy_type\": \"string\", \"metadata\": null}, "
    "{\"name\": \"price\", \"field_name\": \"price\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"size\", \"field_name\": \"size\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"order_id\", \"field_name\": \"order_id\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}], "
    "\"creator\": {\"library\": \"pyarrow\", \"version\": \"15.0.2\"}, \"pandas_version\": \"1.5.3\"}";
const char* MSG_MD =
    "{\"index_columns\": [], \"column_indexes\": [], \"columns\": ["
    "{\"name\": \"seq\", \"field_name\": \"seq\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"t_recv_ns\", \"field_name\": \"t_recv_ns\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"t_send_ns\", \"field_name\": \"t_send_ns\", \"pandas_type\": \"int64\", \"numpy_type\": \"Int64\", \"metadata\": null}, "
    "{\"name\": \"latency_ns\", \"field_name\": \"latency_ns\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"src_id\", \"field_name\": \"src_id\", \"pandas_type\": \"int32\", \"numpy_type\": \"int32\", \"metadata\": null}, "
    "{\"name\": \"dst_id\", \"field_name\": \"dst_id\", \"pandas_type\": \"int32\", \"numpy_type\": \"int32\", \"metadata\": null}, "
    "{\"name\": \"message_id\", \"field_name\": \"message_id\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"msg_type\", \"field_name\": \"msg_type\", \"pandas_type\": \"unicode\", \"numpy_type\": \"string\", \"metadata\": null}, "
    "{\"name\": \"order_id\", \"field_name\": \"order_id\", \"pandas_type\": \"int64\", \"numpy_type\": \"Int64\", \"metadata\": null}, "
    "{\"name\": \"causal_parent\", \"field_name\": \"causal_parent\", \"pandas_type\": \"int64\", \"numpy_type\": \"Int64\", \"metadata\": null}], "
    "\"creator\": {\"library\": \"pyarrow\", \"version\": \"15.0.2\"}, \"pandas_version\": \"1.5.3\"}";

std::string hex(const unsigned char* d) {
    static const char* H = "0123456789abcdef";
    std::string s(64, '0');
    for (int i = 0; i < 32; i++) { s[2 * i] = H[d[i] >> 4]; s[2 * i + 1] = H[d[i] & 15]; }
    return s;
}

void write_all(const std::string& path, const uint8_t* data, size_t n) {
    int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) throw std::runtime_error("cannot open " + path);
    while (n) {
        ssize_t w = write(fd, data, n);
        if (w < 0) { if (errno == EINTR) continue; close(fd); throw std::runtime_error("write failed: " + path); }
        data += w;
        n -= (size_t)w;
    }
    if (close(fd) != 0) throw std::runtime_error("close failed: " + path);
}

double now_s() { return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count(); }

// Output file for pqf::write_file: every piece is hashed and queued, and each flush() writes the
// queue with one writev. The pieces are only borrowed, so flush() must run before they change.
struct FileSink {
    std::string path;
    int fd = -1;
    sha256::Ctx sha;
    uint64_t size = 0;
    struct iovec iov[64];
    int cnt = 0;
    explicit FileSink(const std::string& p) : path(p) {
        fd = open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) throw std::runtime_error("cannot open " + path);
    }
    FileSink(const FileSink&) = delete;
    FileSink& operator=(const FileSink&) = delete;
    ~FileSink() { if (fd >= 0) close(fd); }
    void put(const char* p, size_t n) {
        if (!n) return;
        if (cnt == 64) flush();
        sha.update((const uint8_t*)p, n);
        iov[cnt].iov_base = (void*)p;
        iov[cnt].iov_len = n;
        cnt++;
        size += n;
    }
    void flush() {
        int i = 0;
        while (i < cnt) {
            ssize_t w = writev(fd, iov + i, cnt - i);
            if (w < 0) { if (errno == EINTR) continue; throw std::runtime_error("write failed: " + path); }
            size_t left = (size_t)w;
            while (i < cnt && left >= iov[i].iov_len) left -= iov[i++].iov_len;
            if (i < cnt) { iov[i].iov_base = (char*)iov[i].iov_base + left; iov[i].iov_len -= left; }
        }
        cnt = 0;
    }
    // Closes the file and returns the sha256 of everything written, as hex.
    std::string finish() {
        flush();
        int rc = close(fd);
        fd = -1;
        if (rc != 0) throw std::runtime_error("close failed: " + path);
        unsigned char md[32];
        sha.final(md);
        return hex(md);
    }
};

std::string py_float(double x) {  // shortest repr that round-trips, like Python's float repr
    char b[40];
    for (int prec = 1; prec <= 17; prec++) {
        snprintf(b, sizeof b, "%.*g", prec, x);
        if (strtod(b, nullptr) == x) break;
    }
    std::string s = b;
    if (s.find_first_of(".en") == std::string::npos) s += ".0";  // 2 -> 2.0 ("inf"/"nan" untouched)
    return s;
}

void mkdirs(const std::string& dir) {
    if (dir.empty()) return;
    std::string cur;
    for (size_t i = 0; i <= dir.size(); i++) {
        if (i == dir.size() || dir[i] == '/') {
            if (!cur.empty()) mkdir(cur.c_str(), 0777);
        }
        if (i < dir.size()) cur += dir[i];
    }
}

[[noreturn]] void exec_python(int argc, char** argv, const char* module, const char* why) {
    fprintf(stderr, "t3launch: using the Python path (%s)\n", why);
    fflush(stderr);
    std::vector<char*> a;
    static char py[] = "python", m[] = "-m";
    a.push_back(py);
    a.push_back(m);
    a.push_back(const_cast<char*>(module));
    for (int i = 1; i < argc; i++) a.push_back(argv[i]);
    a.push_back(nullptr);
    execvp("python", a.data());
    perror("t3launch: exec python");
    _exit(127);
}

std::string read_file(const std::string& path) {
    std::string text;
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) throw Fallback("cannot read " + path);
    char buf[1 << 16];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) text.append(buf, n);
    fclose(f);
    return text;
}

// A profile-generating build must flush its counters itself: the launcher leaves through _exit.
#ifdef T3_PGO_GEN
extern "C" void __gcov_dump(void);
static void leave(int rc) { __gcov_dump(); _exit(rc); }
#else
static void leave(int rc) { _exit(rc); }
#endif

struct Events {
    std::string scenario_id, sha_trace, sha_msg;
    int64_t seed = 0, n = 0, m = 0;
    double wall = 0;
    long long peak = 0;
    bool ledger = true;  // false: the card did not require message_trace.parquet and none was written
};

std::string events_json(const Events& ev, bool pretty) {
    double eps = ev.wall > 0 ? (double)ev.n / ev.wall : 0.0;
    std::vector<std::array<std::string, 2>> f = {
        {"scenario_id", "\"" + ev.scenario_id + "\""},
        {"seed", std::to_string(ev.seed)},
        {"n_events", std::to_string(ev.n)},
        {"wall_clock_sec", py_float(ev.wall)},
        {"events_per_sec", py_float(eps)},
        {"trace_sha256", "\"" + ev.sha_trace + "\""},
        {"n_messages", std::to_string(ev.m)},
        {"message_trace_sha256", "\"" + ev.sha_msg + "\""},
        {"peak_memory_bytes", std::to_string(ev.peak)},
        {"gpu_seconds", "0.0"},
    };
    if (!ev.ledger) f.erase(f.begin() + 6, f.begin() + 8);
    const int nf = (int)f.size();
    std::string s = pretty ? "{\n" : "{";
    for (int i = 0; i < nf; i++) {
        if (pretty) s += "  \"" + f[i][0] + "\": " + f[i][1] + (i < nf - 1 ? ",\n" : "\n");
        else s += "\"" + f[i][0] + "\": " + f[i][1] + (i < nf - 1 ? ", " : "");
    }
    s += "}\n";
    return s;
}

long long peak_rss_bytes() {
    struct rusage ru;
    getrusage(RUSAGE_SELF, &ru);
    return (long long)ru.ru_maxrss * 1024;
}

// One scenario end to end: parse, simulate, write the three output files. Throws Fallback when the
// Python path must take over. `threads` > 1 lets the two files (and their columns) encode in parallel.
Events run_one(const std::string& config, const std::string& out, bool has_seed, int64_t seed, bool parallel_io) {
    const bool phases = getenv("T3_PHASES") != nullptr;
    const double T0 = now_s();
    std::string text = read_file(config);
    if (text.size() >= 3 && (unsigned char)text[0] == 0xEF) throw Fallback("BOM");
    Parser ps{text.data(), text.data() + text.size()};
    JV sc = ps.value(0);
    ps.ws();
    if (ps.p != ps.e) throw Fallback("trailing data");
    Built B = build(sc, has_seed, seed);

    const double T1 = now_s();
    void* h = t3_create(B.ci, B.cf, (int32_t)(B.ai.size() / 8), B.ai.data(), B.af.data());
    if (!h) throw Fallback("engine rejected the scenario");
    const double T2 = now_s();
    int rc = t3_simulate(h);
    const double T3 = now_s();
    if (rc != 0) { t3_destroy(h); throw Fallback("engine failed during simulation"); }
    if (B.ci[13] == 1 && t3_lat_ambiguous()) { t3_destroy(h); throw Fallback("latency rounding sensitive to the log implementation"); }
    // Output: the trace and the ledger are independent, so each is assembled, encoded, hashed and
    // written on its own thread (one after the other inside a batch worker).
    Engine* E = static_cast<Engine*>(h);
    // Tuning switches for A/B measurement (defaults are the shipped behaviour).
    auto knob = [](const char* name, int dflt) { const char* v = getenv(name); return v ? atoi(v) : dflt; };
    g_trace_threads = parallel_io ? knob("T3_TRACE_THREADS", 1) : 1;
    // At most four threads are busy during output, which is what the container's CPU quota covers:
    // two per file, or four on the trace when no ledger is written.
    const int ledger_enc_threads = parallel_io ? knob("T3_LEDGER_ENC_THREADS", 2) : 1;
    const int trace_enc_threads = parallel_io ? knob("T3_TRACE_ENC_THREADS", static_cast<Engine*>(h)->skip_ledger ? 4 : 2) : 1;
    T3Result RS{};
    T3Result* R = &RS;
    // A single run exits right after its outputs are complete, so freeing the engine's buffers
    // there would only add time; a batch worker must release them before its next market.
    struct Free { void* h; ~Free() { if (h) t3_destroy(h); } } guard{parallel_io ? nullptr : h};
    size_t slash = out.find_last_of('/');
    std::string dir = slash == std::string::npos ? "" : out.substr(0, slash);
    mkdirs(dir);
    std::string pre = dir.empty() ? std::string() : dir + "/";

    uint64_t trace_bytes = 0, ledger_bytes = 0;
    Events ev;
    std::string err1, err2;
    double tt[2][3] = {{0, 0, 0}, {0, 0, 0}};
    auto do_trace = [&] {
        try {
            const double a = now_s();
            // The engine leaves the trace in its final order (Engine::trace); the columns are
            // encoded straight from those rows.
            const OrderRow* rows = E->trace.b;
            R->n_trace = (int64_t)E->trace.size();
            if (R->n_trace == 0) { err1 = "empty"; return; }
            const double b = now_s();
            using Body = std::string;
            auto i64col = [rows](auto get) {
                return [rows, get](int64_t r0, int64_t k, Body& body) {
                    const OrderRow* x = rows + r0;
                    pqf::put_ints<int64_t, uint64_t>(body, [x, get](int64_t i) -> int64_t { return (int64_t)get(x[i]); }, k);
                };
            };
            auto codecol = [rows](auto get, int n_names) {
                return [rows, get, n_names](int64_t r0, int64_t k, Body& body) {
                    const OrderRow* x = rows + r0;
                    pqf::put_codes(body, [x, get](int64_t i) -> int { return (int)get(x[i]); }, k, n_names);
                };
            };
            pqf::Col tc[7] = {
                {"t_ns", pqf::K_I64, nullptr},
                {"agent_id", pqf::K_I32, nullptr},
                {"msg_type", pqf::K_DICT, nullptr, nullptr, TRACE_NAMES, 6},
                {"side", pqf::K_DICT, nullptr, nullptr, SIDE_NAMES, 2},
                {"price", pqf::K_I64, nullptr},
                {"size", pqf::K_I64, nullptr},
                {"order_id", pqf::K_I64, nullptr}};
            tc[0].custom = i64col([](const OrderRow& r) { return r.t; });
            tc[1].custom = [rows](int64_t r0, int64_t k, Body& body) {
                const OrderRow* x = rows + r0;
                pqf::put_ints<int32_t, uint32_t>(body, [x](int64_t i) -> int32_t { return x[i].owner; }, k);
            };
            tc[2].custom = codecol([](const OrderRow& r) { return r.kind; }, 6);
            tc[3].custom = codecol([](const OrderRow& r) { return r.side; }, 2);
            tc[4].custom = i64col([](const OrderRow& r) { return r.price; });
            tc[5].custom = i64col([](const OrderRow& r) { return r.size; });
            tc[6].custom = i64col([](const OrderRow& r) { return r.order_id; });
            FileSink sink(out);
            pqf::write_file(sink, tc, 7, R->n_trace, TRACE_MD, trace_enc_threads);
            ev.sha_trace = sink.finish();
            trace_bytes = sink.size;
            tt[0][0] = b - a; tt[0][1] = now_s() - b;
        } catch (std::exception& e) { err1 = std::string("trace: ") + e.what(); }
    };
    auto do_msg = [&] {
        try {
            const double a = now_s();
            // The ledger columns are encoded straight from the engine's delivery records (the same
            // values finish_ledger() would put into column arrays; see there for the masking rules).
            const LedgerRec* rec = E->lrec.b;
            R->n_ledger = (int64_t)E->lrec.size();
            const double b = now_s();
            using Body = std::string;
            pqf::Col mc[10] = {
                {"seq", pqf::K_I64, nullptr},
                {"t_recv_ns", pqf::K_I64, nullptr},
                {"t_send_ns", pqf::K_I64_NULLABLE, nullptr},
                {"latency_ns", pqf::K_I64, nullptr},
                {"src_id", pqf::K_I32, nullptr},
                {"dst_id", pqf::K_I32, nullptr},
                {"message_id", pqf::K_I64, nullptr},
                {"msg_type", pqf::K_DICT, nullptr, nullptr, MSG_NAMES, M_N_TYPES},
                {"order_id", pqf::K_I64_NULLABLE, nullptr},
                {"causal_parent", pqf::K_I64_NULLABLE, nullptr}};
            mc[0].custom = [](int64_t r0, int64_t k, Body& body) {
                pqf::put_ints<int64_t, uint64_t>(body, [r0](int64_t i) { return r0 + i; }, k);
            };
            mc[1].custom = [rec](int64_t r0, int64_t k, Body& body) {
                const LedgerRec* x = rec + r0;
                pqf::put_ints<int64_t, uint64_t>(body, [x](int64_t i) { return x[i].t_recv; }, k);
            };
            mc[2].custom = [rec](int64_t r0, int64_t k, Body& body) {
                const LedgerRec* x = rec + r0;
                pqf::put_nullable_i64(body, [x](int64_t i) { return x[i].type != M_WAKEUP; }, [x](int64_t i) { return x[i].t_send; }, k);
            };
            mc[3].custom = [rec](int64_t r0, int64_t k, Body& body) {
                const LedgerRec* x = rec + r0;
                pqf::put_ints<int64_t, uint64_t>(body, [x](int64_t i) { return x[i].type == M_WAKEUP ? (int64_t)0 : x[i].t_recv - x[i].t_send; }, k);
            };
            mc[4].custom = [rec](int64_t r0, int64_t k, Body& body) {
                const LedgerRec* x = rec + r0;
                pqf::put_ints<int32_t, uint32_t>(body, [x](int64_t i) { return (int32_t)x[i].src; }, k);
            };
            mc[5].custom = [rec](int64_t r0, int64_t k, Body& body) {
                const LedgerRec* x = rec + r0;
                pqf::put_ints<int32_t, uint32_t>(body, [x](int64_t i) { return (int32_t)x[i].dst; }, k);
            };
            mc[6].custom = [rec](int64_t r0, int64_t k, Body& body) {
                const LedgerRec* x = rec + r0;
                pqf::put_ints<int64_t, uint64_t>(body, [x](int64_t i) { return (int64_t)x[i].message_id; }, k);
            };
            mc[7].custom = [rec](int64_t r0, int64_t k, Body& body) {
                const LedgerRec* x = rec + r0;
                pqf::put_codes(body, [x](int64_t i) { return (int)x[i].type; }, k, M_N_TYPES);
            };
            mc[8].custom = [rec](int64_t r0, int64_t k, Body& body) {
                const LedgerRec* x = rec + r0;
                pqf::put_nullable_i64(body, [x](int64_t i) { return msg_has_order(x[i].type); }, [x](int64_t i) { return x[i].order_id; }, k);
            };
            mc[9].custom = [rec](int64_t r0, int64_t k, Body& body) {
                const LedgerRec* x = rec + r0;
                pqf::put_nullable_i64(body, [x](int64_t i) { return x[i].type != M_WAKEUP; }, [x](int64_t i) { return (int64_t)x[i].causal; }, k);
            };
            FileSink sink(pre + "message_trace.parquet");
            pqf::write_file(sink, mc, 10, R->n_ledger, MSG_MD, ledger_enc_threads);
            ev.sha_msg = sink.finish();
            ledger_bytes = sink.size;
            tt[1][0] = b - a; tt[1][1] = now_s() - b;
        } catch (std::exception& e) { err2 = std::string("ledger: ") + e.what(); }
    };
    const bool skip_ledger = E->skip_ledger;
    ev.ledger = !skip_ledger;
    if (skip_ledger) {
        do_trace();
    } else if (parallel_io) {
        std::thread tw(do_msg);
        do_trace();
        tw.join();
    } else {
        do_trace();
        do_msg();
    }
    if (err1 == "empty") throw Fallback("empty trace");
    const int64_t n = R->n_trace, m = R->n_ledger;
    // The organizers cap outputs at 256 MiB per file and in total; the Python path compresses harder.
    // (Checked after writing: the Python path rewrites both files.)
    if (trace_bytes + ledger_bytes > (uint64_t)240 * 1024 * 1024) throw Fallback("outputs too large for the built-in writer");
    if (!err1.empty() || !err2.empty()) throw Fallback("parquet writing failed: " + err1 + " " + err2);

    ev.scenario_id = B.scenario_id;
    ev.seed = B.seed;
    ev.n = n;
    ev.m = m;
    ev.wall = T3 - T2;  // the event loop, the same scope the reference adapter times
    ev.peak = peak_rss_bytes();
    std::string pretty = events_json(ev, true);
    write_all(pre + "events.json", (const uint8_t*)pretty.data(), pretty.size());
    if (phases) {
        struct rusage ru;
        getrusage(RUSAGE_SELF, &ru);
        fprintf(stderr, "res: minflt=%ld majflt=%ld utime=%.1f stime=%.1f ms maxrss=%ld MB | reserved rows: trace=%zu ledger=%zu | used: trace=%zu ledger=%zu\n",
                ru.ru_minflt, ru.ru_majflt, ru.ru_utime.tv_sec * 1e3 + ru.ru_utime.tv_usec / 1e3,
                ru.ru_stime.tv_sec * 1e3 + ru.ru_stime.tv_usec / 1e3, ru.ru_maxrss / 1024,
                (size_t)(E->trace.e - E->trace.b), (size_t)(E->lrec.e - E->lrec.b), E->trace.size(), E->lrec.size());
    }
    if (phases)
        fprintf(stderr, "parse=%.1f create=%.1f sim=%.1f out=%.1f ms | trace finish=%.1f build=%.1f emit=%.1f | ledger finish=%.1f build=%.1f emit=%.1f\n",
                (T1 - T0) * 1e3, (T2 - T1) * 1e3, (T3 - T2) * 1e3, (now_s() - T3) * 1e3, tt[0][0] * 1e3, tt[0][1] * 1e3, tt[0][2] * 1e3,
                tt[1][0] * 1e3, tt[1][1] * 1e3, tt[1][2] * 1e3);
    if (parallel_io) {
        // A single run is finished here. Leaving now skips freeing the encoded files, the trace
        // index and the scenario tree, which the kernel reclaims faster on its own.
        std::string line = events_json(ev, false);
        fwrite(line.data(), 1, line.size(), stdout);
        fflush(stdout);
        leave(0);
    }
    return ev;
}

// True only when the unit's card (card.toml beside the scenario) says, under [scoring.params],
// `requires_message_ledger = false`. The organizers' README tells submissions not to write
// message_trace.parquet on such units, and the scorer does not open it there. Anything else (no
// card, no key, another value, an unreadable file) means the ledger is written.
bool card_skips_ledger(const std::string& config) {
    size_t slash = config.find_last_of('/');
    std::string path = (slash == std::string::npos ? std::string() : config.substr(0, slash + 1)) + "card.toml";
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return false;
    std::string text;
    char buf[1 << 14];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && text.size() < (1u << 20)) text.append(buf, n);
    fclose(f);
    bool in_params = false, found = false, value = true;
    size_t i = 0;
    while (i < text.size()) {
        size_t j = text.find('\n', i);
        if (j == std::string::npos) j = text.size();
        std::string line = text.substr(i, j - i);
        i = j + 1;
        size_t a = line.find_first_not_of(" \t\r");
        if (a == std::string::npos) continue;
        size_t b = line.find_last_not_of(" \t\r");
        line = line.substr(a, b - a + 1);
        if (line[0] == '[') { in_params = line == "[scoring.params]"; continue; }
        if (!in_params || line.compare(0, 23, "requires_message_ledger") != 0) continue;
        size_t eq = line.find_first_not_of(" \t", 23);
        if (eq == std::string::npos || line[eq] != '=') return false;
        size_t v = line.find_first_not_of(" \t", eq + 1);
        std::string val = v == std::string::npos ? std::string() : line.substr(v);
        if (found) return false;  // a repeated key: do not guess
        found = true;
        if (val == "false") value = false;
        else return false;
    }
    return found && !value;
}

bool simple_name(const std::string& s) {
    for (unsigned char ch : s)
        if (ch < 0x20 || ch > 0x7e || ch == '"' || ch == '\\') return false;
    return true;
}

}  // namespace

static int main_single(int argc, char** argv) {
    std::string config, out;
    bool has_seed = false;
    int64_t seed = 0;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto val = [&](const char* name) -> std::string {
            if (a == name) { if (i + 1 >= argc) throw Fallback("missing argument value"); return argv[++i]; }
            return a.substr(strlen(name) + 1);
        };
        if (a == "simulate" && i == 1) continue;
        if (a == "--config" || a.rfind("--config=", 0) == 0) config = val("--config");
        else if (a == "--out" || a.rfind("--out=", 0) == 0) out = val("--out");
        else if (a == "--seed" || a.rfind("--seed=", 0) == 0) {
            JV v;
            v.t = JV::Num;
            v.s = val("--seed");
            if (v.s.empty() || v.s.find_first_not_of("0123456789") != std::string::npos) throw Fallback("seed argument");
            seed = as_int(v);
            has_seed = true;
        } else throw Fallback("unrecognised argument");
    }
    if (config.empty() || out.empty()) throw Fallback("missing --config/--out");
    {   // T3_ASYNC_PF=1: populate the output buffers from spare CPUs while the simulation runs.
        // Off by default: the A/B on our machine showed no gain (lab/bench).
        const char* v = getenv("T3_ASYNC_PF");
        g_async_prefault = v && atoi(v) != 0;
    }
    {   // T3_LEDGER=1 writes the ledger regardless of the card (for comparison runs).
        const char* v = getenv("T3_LEDGER");
        g_skip_ledger = !(v && atoi(v) != 0) && card_skips_ledger(config);
    }
    run_one(config, out, has_seed, seed, true);  // prints the events line and exits on success
    return 0;
}

static int main_batch(int argc, char** argv) {
    std::string batch_dir, out_dir;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto val = [&](const char* name) -> std::string {
            if (a == name) { if (i + 1 >= argc) throw Fallback("missing argument value"); return argv[++i]; }
            return a.substr(strlen(name) + 1);
        };
        if (a == "simulate-batch" && i == 1) continue;
        if (a == "--batch-dir" || a.rfind("--batch-dir=", 0) == 0) batch_dir = val("--batch-dir");
        else if (a == "--out-dir" || a.rfind("--out-dir=", 0) == 0) out_dir = val("--out-dir");
        else throw Fallback("unrecognised argument");
    }
    if (batch_dir.empty() || out_dir.empty()) throw Fallback("missing --batch-dir/--out-dir");
    while (batch_dir.size() > 1 && batch_dir.back() == '/') batch_dir.pop_back();
    while (out_dir.size() > 1 && out_dir.back() == '/') out_dir.pop_back();

    // sorted(batch_dir.glob("*.json")): names compared as plain strings
    std::vector<std::string> stems;
    {
        DIR* d = opendir(batch_dir.c_str());
        if (!d) throw Fallback("cannot list batch dir");
        while (dirent* e = readdir(d)) {
            std::string nm = e->d_name;
            if (nm.size() < 5 || nm.compare(nm.size() - 5, 5, ".json") != 0) continue;
            if (nm[0] == '.') { closedir(d); throw Fallback("hidden sub-scenario file"); }
            struct stat st;
            if (stat((batch_dir + "/" + nm).c_str(), &st) != 0 || !S_ISREG(st.st_mode)) { closedir(d); throw Fallback("odd batch entry"); }
            if (!simple_name(nm)) { closedir(d); throw Fallback("sub name needs escaping"); }
            stems.push_back(nm.substr(0, nm.size() - 5));
        }
        closedir(d);
    }
    if (stems.empty()) throw Fallback("no sub-scenarios");
    {   // Python sorts the full file names (stem + ".json")
        std::vector<std::string> names;
        for (auto& s : stems) names.push_back(s + ".json");
        std::sort(names.begin(), names.end());
        for (size_t i = 0; i < names.size(); i++) stems[i] = names[i].substr(0, names[i].size() - 5);
    }

    const double t0 = now_s();
    const size_t n = stems.size();
    std::vector<Events> evs(n);
    std::vector<std::string> errs(n);
    size_t workers = std::min<size_t>(n, 4);
    if (const char* w = getenv("T3_BATCH_WORKERS")) workers = std::max<size_t>(1, std::min<size_t>(n, (size_t)atoi(w)));
    if (workers > 1) setenv("T3_LAT_THREAD", "0", 1);  // every CPU already runs a market
    // Largest inputs first (longest-processing-time-first on a shared queue).
    std::vector<size_t> order(n);
    for (size_t i = 0; i < n; i++) order[i] = i;
    std::atomic<size_t> next{0};
    auto work = [&] {
        for (;;) {
            size_t k = next.fetch_add(1);
            if (k >= n) return;
            size_t i = order[k];
            try {
                evs[i] = run_one(batch_dir + "/" + stems[i] + ".json", out_dir + "/" + stems[i] + "/trace.parquet", false, 0, false);
            } catch (std::exception& e) {
                errs[i] = e.what()[0] ? e.what() : "error";
            }
        }
    };
    std::vector<std::thread> pool;
    for (size_t w = 1; w < workers; w++) pool.emplace_back(work);
    work();
    for (auto& t : pool) t.join();
    for (size_t i = 0; i < n; i++)
        if (!errs[i].empty()) throw Fallback(stems[i] + ": " + errs[i]);
    const double wall = now_s() - t0;  // the whole batch (parse, simulate, write), never flattering

    long long total = 0, peak = peak_rss_bytes();
    for (auto& e : evs) total += e.n;
    double eps = wall > 0 ? (double)total / wall : 0.0;
    std::string pretty = "{\n  \"n_scenarios\": " + std::to_string(n) + ",\n  \"total_events\": " + std::to_string(total) +
                         ",\n  \"wall_clock_sec\": " + py_float(wall) + ",\n  \"events_per_sec\": " + py_float(eps) +
                         ",\n  \"peak_memory_bytes\": " + std::to_string(peak) + ",\n  \"gpu_seconds\": 0.0,\n  \"per_scenario\": [\n";
    std::string line = "{\"n_scenarios\": " + std::to_string(n) + ", \"total_events\": " + std::to_string(total) +
                       ", \"wall_clock_sec\": " + py_float(wall) + ", \"events_per_sec\": " + py_float(eps) +
                       ", \"peak_memory_bytes\": " + std::to_string(peak) + ", \"gpu_seconds\": 0.0, \"per_scenario\": [";
    for (size_t i = 0; i < n; i++) {
        pretty += "    {\n      \"sub\": \"" + stems[i] + "\",\n      \"n_events\": " + std::to_string(evs[i].n) +
                  ",\n      \"trace_sha256\": \"" + evs[i].sha_trace + "\"\n    }" + (i + 1 < n ? ",\n" : "\n");
        line += "{\"sub\": \"" + stems[i] + "\", \"n_events\": " + std::to_string(evs[i].n) + ", \"trace_sha256\": \"" +
                evs[i].sha_trace + "\"}" + (i + 1 < n ? ", " : "");
    }
    pretty += "  ]\n}\n";
    line += "]}\n";
    mkdirs(out_dir);
    mkdir(out_dir.c_str(), 0777);
    write_all(out_dir + "/batch_events.json", (const uint8_t*)pretty.data(), pretty.size());
    fwrite(line.data(), 1, line.size(), stdout);
    fflush(stdout);
    return 0;
}

int main(int argc, char** argv) {
    // Keep freed blocks in the heap: the process lives for a fraction of a second, and giving
    // megabyte-sized buffers back to the kernel only to map and fault them in again costs more
    // than the memory is worth. (32 MiB is the largest mmap threshold glibc accepts.)
    mallopt(M_MMAP_THRESHOLD, 32 << 20);
    mallopt(M_TRIM_THRESHOLD, 1 << 30);
    const char* base = strrchr(argv[0], '/');
    base = base ? base + 1 : argv[0];
    const bool batch = strstr(base, "batch") != nullptr || (argc > 1 && !strcmp(argv[1], "simulate-batch"));
    const char* module = batch ? "t3native.batch" : "t3native.cli";
    try {
        if (const char* f = getenv("T3_FORCE_REFERENCE")) if (!strcmp(f, "1")) throw Fallback("reference path forced");
        if (const char* f = getenv("T3_NO_LAUNCHER")) if (!strcmp(f, "1")) throw Fallback("launcher disabled");
        g_want_utf8 = false;  // string columns are written from the codes
        int rc = batch ? main_batch(argc, argv) : main_single(argc, argv);
        leave(rc);  // outputs are complete: skip teardown of large buffers and library destructors
    } catch (std::exception& e) {
        exec_python(argc, argv, module, e.what());
    }
}
