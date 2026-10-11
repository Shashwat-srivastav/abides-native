// Native Track 3 engine: a bit-exact reimplementation of the ABIDES code paths exercised by the
// abides_fork adapter (Kernel + ExchangeAgent/OrderBook + the four ScheduledAgent types +
// SparseMeanRevertingOracle + ScenarioLatencyModel + the message-ledger/STP/scheduled-jump
// patches), emitting the same trace rows and message-ledger rows as abides_fork/trace.py.
//
// Exactness notes (each mirrors a Python behaviour, see the adapter/ABIDES sources):
//  * Event order is the kernel heap's total order (time, sender, recipient, message_id).
//  * Message payloads are value snapshots taken at send time (no ABIDES path mutates a sent order).
//  * RNG streams replicate numpy 1.26 legacy RandomState draw-for-draw (np_random.hpp), including
//    the GLOBAL stream the oracle uses for megashock inter-arrival times.
//  * Python float/int comparisons are exact (mixed_cmp), and Python round() is half-to-even.
#include <algorithm>
#include <atomic>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <sched.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <emmintrin.h>
#include <queue>
#include <stdexcept>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <linux/futex.h>
#include <unistd.h>
#include <string>
#include <unordered_map>
#include <memory>
#include <vector>

#include "../rng/np_random.hpp"

namespace t3 {

using i64 = int64_t;

// ---------------------------------------------------------------- memory
// Switches for measuring on the scoring host, where a page fault and a huge-page request can cost
// something quite different from a development machine. Set in the image's environment.
//   T3_HUGE=0      do not ask for transparent huge pages
//   T3_PREFAULT=0  do not populate output buffers up front; pages are faulted as they are written
static bool env_flag(const char* name, bool dflt) {
    const char* v = getenv(name);
    return v && *v ? atoi(v) != 0 : dflt;
}
static const bool g_use_huge = env_flag("T3_HUGE", true);
static const bool g_use_prefault = env_flag("T3_PREFAULT", true);

// Reserve (virtual only until touched) and ask for transparent huge pages: output buffers are
// large and written once, so first-touch page faults dominate otherwise. madvise is advisory.
template <class T>
static void reserve_huge(std::vector<T>& v, size_t n) {
    v.reserve(n);
    const uintptr_t kHuge = 2u << 20;
    uintptr_t b = (uintptr_t)v.data(), e = b + n * sizeof(T);
    uintptr_t ab = (b + kHuge - 1) & ~(kHuge - 1);
    if (g_use_huge && e > ab + kHuge) madvise((void*)ab, (e - ab) & ~(kHuge - 1), MADV_HUGEPAGE);
}

// Back the reserved capacity with physical pages now (setup phase) instead of taking a page-fault
// trap per 4 KiB during the event loop. MADV_POPULATE_WRITE (Linux 5.14+) does it in one call;
// where unsupported (older kernels, gVisor) fall back to touching one byte per page.
template <class T>
static void prefault(std::vector<T>& v) {
#ifndef MADV_POPULATE_WRITE
#define MADV_POPULATE_WRITE 23
#endif
    if (!g_use_prefault) return;
    const uintptr_t kPage = 4096;
    uintptr_t b = (uintptr_t)v.data(), e = b + v.capacity() * sizeof(T);
    uintptr_t ab = (b + kPage - 1) & ~(kPage - 1), ae = e & ~(kPage - 1);
    if (ae <= ab) return;
    if (madvise((void*)ab, ae - ab, MADV_POPULATE_WRITE) == 0) return;
    for (uintptr_t p = ab; p < ae; p += kPage) *(volatile char*)p = 0;
}

// Append-only output buffer with a raw write cursor (one capacity check per row, no per-field
// vector bookkeeping). Large buffers are 2 MiB-aligned and advised for huge pages.
// Output column: sized once and then fully overwritten, so it is left uninitialised (a
// std::vector would zero every page first and touch the memory twice).
template <class T>
struct Raw {
    T* b = nullptr;
    size_t n = 0;
    Raw() = default;
    Raw(const Raw&) = delete;
    Raw& operator=(const Raw&) = delete;
    ~Raw() { free(b); }
    void resize(size_t k) {
        free(b);
        const size_t kHuge = 2u << 20, want = k * sizeof(T) + 64;
        if (want >= 2 * kHuge) {  // big columns: 2 MiB-aligned and advised for huge pages, like Buf
            const size_t nbytes = (want + kHuge - 1) & ~(kHuge - 1);
            b = (T*)aligned_alloc(kHuge, nbytes);
            if (b && g_use_huge) madvise((void*)b, nbytes, MADV_HUGEPAGE);
        } else {
            b = (T*)malloc(want);
        }
        if (!b) throw std::bad_alloc();
        n = k;
    }
    T* data() { return b; }
    T& operator[](size_t i) { return b[i]; }
    size_t size() const { return n; }
};

template <class T>
struct Buf {
    T *b = nullptr, *p = nullptr, *e = nullptr;
    size_t bytes = 0;
    // For a reader on another thread (the launcher encodes finished rows while the simulation
    // still appends): the current buffer, and outgrown buffers kept alive so that a reader holding
    // an older pointer still sees valid, identical rows.
    std::atomic<T*> pub_b{nullptr};
    bool keep_old = false;
    std::vector<T*> old;
    Buf() = default;
    Buf(const Buf&) = delete;
    Buf& operator=(const Buf&) = delete;
    ~Buf() { free(b); for (T* o : old) free(o); }
    size_t size() const { return (size_t)(p - b); }
    T& operator[](size_t i) { return b[i]; }
    void reserve(size_t n) {
        const size_t kHuge = 2u << 20, kPage = 4096;
        size_t want = n * sizeof(T);
        size_t al = want >= kHuge ? kHuge : kPage;
        size_t nbytes = (want + al - 1) & ~(al - 1);
        if (nbytes <= bytes) return;
        T* nb = (T*)aligned_alloc(al, nbytes);
        if (!nb) throw std::bad_alloc();
        if (al == kHuge && g_use_huge) madvise((void*)nb, nbytes, MADV_HUGEPAGE);
        size_t used = size();
        if (used) memcpy((void*)nb, (void*)b, used * sizeof(T));
        if (keep_old && b) old.push_back(b);
        else free(b);
        b = nb; p = nb + used; e = nb + nbytes / sizeof(T); bytes = nbytes;
        pub_b.store(nb, std::memory_order_release);
    }
    // Pre-fault from another thread while the owner is already writing. Never stores a value: a
    // page the owner has filled must not be touched. If the range is freed meanwhile (a reserve()
    // that outgrew the estimate) the calls fail or populate unrelated memory, both harmless.
    void prefault_async_body(void* base, size_t nbytes) {
        const size_t kStep = (size_t)8 << 20;
        for (size_t off = 0; off < nbytes; off += kStep)
            if (madvise((char*)base + off, std::min(kStep, nbytes - off), MADV_POPULATE_WRITE) != 0) return;
    }
    // Pre-fault the first `frac` of the reservation; the rest is faulted on demand if ever reached.
    void prefault(double frac = 1.0) {
        if (!bytes || !g_use_prefault) return;
        size_t n = (size_t)((double)bytes * frac);
        n = std::min(bytes, (n + 4095) & ~(size_t)4095);
        if (madvise((void*)b, n, MADV_POPULATE_WRITE) == 0) return;
        for (size_t o = 0; o < n; o += 4096) *((volatile char*)b + o) = 0;
    }
    T* next() {
        if (__builtin_expect(p == e, 0)) reserve(std::max<size_t>(4096, 2 * size()));
        return p++;
    }
};

// ---------------------------------------------------------------- python numeric semantics
// cvtsd2si rounds in the current MXCSR mode (nearest, ties-to-even) == (i64)nearbyint(x), inline.
static inline i64 py_round(double x) { return (i64)_mm_cvtsd_si64(_mm_set_sd(x)); }

// Exact comparison of a double with an int64, like Python's float/int comparison.
static inline int mixed_cmp(double a, i64 b) {
    double fl = std::floor(a);
    i64 fi = (i64)fl;  // times are < 2^63, so this is exact for integral doubles
    if (fi < b) return -1;
    if (fi > b) return 1;
    return a > fl ? 1 : 0;
}

// A Python number that is either an int or a float (the oracle's timestamps can be either).
struct PyNum {
    bool is_float;
    i64 i;
    double f;
    static PyNum I(i64 v) { return {false, v, 0.0}; }
    static PyNum F(double v) { return {true, 0, v}; }
    double as_double() const { return is_float ? f : (double)i; }
};
// a - b with Python's int/float promotion.
static inline PyNum py_sub(PyNum a, PyNum b) {
    if (!a.is_float && !b.is_float) return PyNum::I(a.i - b.i);
    return PyNum::F(a.as_double() - b.as_double());
}
// a < b / a <= b / a >= b as the oracle evaluates them. The oracle's timestamps are NUMPY scalars
// (mkt_open is np.int64 from str_to_ns, so every megashock time is np.float64), and numpy 1.26
// compares np.float64 with an int by casting the int to float64 -- NOT Python's exact float/int
// comparison. So any comparison with a float operand is a plain double comparison.
static inline int py_cmp(PyNum a, PyNum b) {
    if (!a.is_float && !b.is_float) return (a.i < b.i) ? -1 : (a.i > b.i ? 1 : 0);
    double x = a.as_double(), y = b.as_double();
    return (x < y) ? -1 : (x > y ? 1 : 0);
}

// ---------------------------------------------------------------- messages
enum MsgType : int8_t {
    M_WAKEUP = 0,
    M_MKT_CLOSE_PRICE_REQ,
    M_MKT_HOURS_REQ,
    M_MKT_HOURS,
    M_QUERY_SPREAD,
    M_QUERY_SPREAD_RESP,
    M_LIMIT_ORDER,
    M_CANCEL_ORDER,
    M_ORDER_ACCEPTED,
    M_ORDER_EXECUTED,
    M_ORDER_CANCELLED,
    M_MKT_CLOSED,
    M_MKT_CLOSE_PRICE,
    M_N_TYPES
};
// Ledger msg_type strings (Python class names; wakeups are logged as AGENT_WAKEUP).
static const char* MSG_NAMES[M_N_TYPES] = {
    "AGENT_WAKEUP",        "MarketClosePriceRequestMsg", "MarketHoursRequestMsg",
    "MarketHoursMsg",      "QuerySpreadMsg",             "QuerySpreadResponseMsg",
    "LimitOrderMsg",       "CancelOrderMsg",             "OrderAcceptedMsg",
    "OrderExecutedMsg",    "OrderCancelledMsg",          "MarketClosedMsg",
    "MarketClosePriceMsg"};
static inline bool msg_has_order(int t) {
    return t == M_LIMIT_ORDER || t == M_CANCEL_ORDER || t == M_ORDER_ACCEPTED ||
           t == M_ORDER_EXECUTED || t == M_ORDER_CANCELLED;
}

enum Side : int8_t { BID = 0, ASK = 1 };

struct OrderSnap {  // value snapshot of a LimitOrder
    i64 order_id;
    i64 limit_price;
    i64 quantity;
    i64 fill_price;  // valid iff has_fill
    int32_t agent_id;
    Side side;
    bool has_fill;
};

// One in-flight message, 56 bytes. Payload fields are overlaid by message type:
//   order messages : order_id / price / quantity / agent_id / side, where price is the FILL price
//                    for OrderExecutedMsg and the limit price otherwise (the only one each reader uses)
//   QuerySpreadResponseMsg : price = best bid, quantity = best ask, flags = F_HAS_BID|F_HAS_ASK|F_CLOSED
struct Msg {
    i64 t_send, t_recv;  // ledger send info (per heap entry; a broadcast has one entry per recipient)
    i64 order_id, price, quantity;
    uint32_t id, causal_parent;  // ids are < 2^32 (guarded in new_msg)
    int32_t agent_id;
    int8_t type;
    Side side;
    uint8_t flags;
};
enum : uint8_t { F_HAS_BID = 1, F_HAS_ASK = 2, F_CLOSED = 4 };

// Kernel heap entry. The reference orders by (time, sender, recipient, message_id); packing the
// last three into one u64 (16 | 16 | 32 bits) preserves that lexicographic order exactly. Keys are
// unique, so the pop sequence is fully determined by the order (heap shape is irrelevant).
// Scenarios exceeding the packing limits throw -> exact reference fallback.
typedef unsigned __int128 u128;
struct HeapEntry {
    // Full sort key in one unsigned 128-bit word: (time with sign bit flipped) << 64 | packed key.
    // Flipping the sign bit makes unsigned order equal signed time order, so a single integer
    // compare reproduces (time, sender, recipient, message_id) exactly, without branches.
    u128 k;
    uint32_t slot;  // index into the message pool
    i64 time() const { return (i64)((uint64_t)(k >> 64) ^ 0x8000000000000000ull); }
    uint64_t key() const { return (uint64_t)k; }
    int32_t sender() const { return (int32_t)(key() >> 48); }
    int32_t recipient() const { return (int32_t)((key() >> 32) & 0xFFFF); }
    i64 msg_id() const { return (i64)(key() & 0xFFFFFFFFu); }
    void set_time(i64 t) { k = ((u128)((uint64_t)t ^ 0x8000000000000000ull) << 64) | (u128)key(); }
    static HeapEntry make(i64 t, uint64_t key, uint32_t slot) {
        return {((u128)((uint64_t)t ^ 0x8000000000000000ull) << 64) | (u128)key, slot};
    }
};
static inline uint64_t heap_key(int32_t sender, int32_t recipient, i64 msg_id) {
    return ((uint64_t)sender << 48) | ((uint64_t)recipient << 32) | (uint64_t)msg_id;
}
static inline bool heap_less(const HeapEntry& a, const HeapEntry& b) { return a.k < b.k; }

// 4-ary min-heap: shallower than binary, and children share cache lines.
struct EventHeap {
    std::vector<HeapEntry> h;
    bool empty() const { return h.empty(); }
    const HeapEntry& top() const { return h[0]; }
    void push(const HeapEntry& e) {
        size_t i = h.size();
        h.push_back(e);
        while (i > 0) {
            size_t p = (i - 1) >> 2;
            if (!heap_less(e, h[p])) break;
            h[i] = h[p];
            i = p;
        }
        h[i] = e;
    }
    void pop() {
        HeapEntry last = h.back();
        h.pop_back();
        if (!h.empty()) sift_down(0, last);
    }
    // Equivalent to pop() then push(e) when e is not smaller than the current top.
    void replace_top(const HeapEntry& e) { sift_down(0, e); }

   private:
    void sift_down(size_t i, const HeapEntry& e) {
        const size_t n = h.size();
        for (;;) {
            size_t c = 4 * i + 1;
            if (c >= n) break;
            size_t best = c;
            if (c + 4 <= n) {  // full fan-out: tournament on index arithmetic, so no branch depends on the keys
                const size_t b01 = c + (size_t)(h[c + 1].k < h[c].k);
                const size_t b23 = c + 2 + (size_t)(h[c + 3].k < h[c + 2].k);
                best = b01 + ((b23 - b01) & (size_t)0 - (size_t)(h[b23].k < h[b01].k));
            } else {
                for (size_t k = c + 1; k < n; k++)
                    if (heap_less(h[k], h[best])) best = k;
            }
            if (!heap_less(h[best], e)) break;
            h[i] = h[best];
            i = best;
        }
        h[i] = e;
    }
};

// ---------------------------------------------------------------- outputs
// 32 bytes, two rows per cache line. Sizes and order ids are stored in 32 bits; a value that does
// not fit stops the run (row_fits), which sends the scenario to the exact fallback path.
struct OrderRow {  // one trace row: an order-lifecycle event, or a quote (kind 5)
    i64 t;
    i64 price;
    int32_t size;
    int32_t order_id;  // -1 on a quote row
    int32_t owner;     // logging agent (== order agent_id for our flows); 0 on a quote row
    int8_t kind;       // 0 SUBMITTED, 1 ACCEPTED, 2 CANCELLED, 3 EXECUTED, 4 final fill, 5 QUOTE
    Side side;
};
static inline void row_fits(i64 size, i64 order_id) {
    if (__builtin_expect((uint64_t)size > 0x7fffffffull || (uint64_t)(order_id + 1) > 0x7fffffffull, 0))
        throw std::runtime_error("trace value exceeds 32 bits");
}
// One delivered message, in delivery order (row index == deliver_seq). Fields that do not apply to
// the message type hold stale values and are masked when the columns are built in t3_finish.
struct LedgerRec {
    i64 t_recv, t_send, order_id;
    uint32_t message_id, causal;
    uint16_t src, dst;
    int8_t type;
};

// ---------------------------------------------------------------- order book
struct BookOrder {
    OrderSnap o;
    int32_t prev, next;  // intrusive FIFO within a price level
};
struct Level {
    i64 price;
    i64 total_qty;  // visible quantity (no hidden orders in these flows)
    int32_t head, tail;
};

struct Engine;

struct SideBook {
    // Levels ordered best-first (bids: descending price; asks: ascending).
    std::vector<Level> levels;  // levels[0] is the best; stored reversed for cheap front ops
    // We store levels in reverse (best at the back) so that removing the best level is pop_back.
    bool is_bid;
    bool empty() const { return levels.empty(); }
    Level& best() { return levels.back(); }
    // better(a, b): price a is strictly better than b for this side
    bool better(i64 a, i64 b) const { return is_bid ? a > b : a < b; }
};

// ---------------------------------------------------------------- agents
enum AgentKind : int8_t { A_EXCHANGE = 0, A_NOISE, A_MM, A_VALUE, A_MOMENTUM };

static constexpr uint32_t NONE = 0xFFFFFFFFu;

// Grow-on-demand dense map keyed by order_id (order ids are global and sequential from 0).
struct DenseIndex {
    std::vector<uint32_t> v;
    uint32_t get(i64 id) const { return (size_t)id < v.size() ? v[(size_t)id] : NONE; }
    void set(i64 id, uint32_t x) {
        if ((size_t)id >= v.size()) v.resize(std::max<size_t>((size_t)id + 1, v.size() * 2 + 1024), NONE);
        v[(size_t)id] = x;
    }
};

struct OwnOrders {  // insertion-ordered dict order_id -> quantity (+ side/price for cancels)
    struct E { i64 order_id, limit_price, quantity; Side side; bool alive; };
    std::vector<E> v;
    DenseIndex* idx = nullptr;  // engine-wide: order ids are unique across agents
    size_t alive = 0;
    void put(const OrderSnap& o) {
        idx->set(o.order_id, (uint32_t)v.size());
        v.push_back({o.order_id, o.limit_price, o.quantity, o.side, true});
        alive++;
    }
    E* find(i64 id) {
        uint32_t p = idx->get(id);
        return p == NONE ? nullptr : &v[p];
    }
    void erase(i64 id) {
        uint32_t p = idx->get(id);
        v[p].alive = false;
        idx->set(id, NONE);
        alive--;
        if (v.size() > 64 && alive * 4 < v.size()) compact();
    }
    void compact() {
        std::vector<E> nv;
        nv.reserve(alive * 2 + 8);
        for (auto& e : v)
            if (e.alive) { idx->set(e.order_id, (uint32_t)nv.size()); nv.push_back(e); }
        v.swap(nv);
    }
};

// The fields every dispatch reads come first and fit in two cache lines; the generator state
// (about 2.5 KB) is last, so it does not sit between them.
struct Agent {
    AgentKind kind;
    int32_t id;
    i64 interval_ns;
    // trading-agent state
    bool first_wake = true, has_mkt_hours = false, mkt_closed = false;
    bool awaiting_spread = false;
    i64 current_time = 0;
    bool kb_has_bid = false, kb_has_ask = false;  // known_bids/known_asks non-empty
    i64 kb_bid = 0, kb_ask = 0;
    OwnOrders orders;
    // params
    double order_size_mean = 0, order_size_std = 0;
    i64 price_offset_ticks = 0, reference_price = 0;
    i64 spread_ticks = 0, depth_levels = 0, size_per_level = 0;
    i64 threshold_ticks = 0;
    double sigma_n = 1000.0;
    i64 lookback = 0;
    std::vector<double> mid_history;
    nprand::NpRandomState rs;
};

// ---------------------------------------------------------------- engine
struct Config {
    i64 seed;
    i64 start_time, stop_time, mkt_open, mkt_close;
    i64 oracle_close;  // SparseMeanRevertingOracle.mkt_close = date + 16:00 (NOT the scenario close)
    i64 default_computation_delay;
    // exchange
    i64 pipeline_delay, exch_computation_delay;
    int stp_policy;  // 0 none, 1 cancel_newest(any non-oldest), 2 cancel_oldest
    // oracle
    i64 r_bar;
    double kappa, fund_vol, megashock_lambda_a, megashock_mean, megashock_var;
    bool has_sched_jump;
    i64 sched_jump_time, sched_jump_mag;
    // latency
    int lat_model;  // 0 deterministic/other, 1 log_normal, 2 uniform, 3 pareto
    double lat_mean_ns, lat_sigma, lat_min_ns, lat_max_ns, lat_alpha, lat_mu;
};

static std::atomic<bool> g_lat_ambiguous{false};

struct Engine {
    Config c;
    nprand::NpRandomState global_rs, oracle_rs, latency_rs;
    std::vector<Agent> agents;
    std::vector<i64> agent_current_times, agent_comp_delays;
    // Two event queues with one total order: wakeups (one pending per agent, far in the future) and
    // in-flight messages (a handful, near in time). The next event is the smaller of the two tops,
    // so the pop sequence is exactly that of the reference's single heap, but near-term message
    // traffic never sifts through the wakeup population.
    EventHeap wheap, mheap;
    EventHeap* hole = nullptr;  // heap whose top is the event being dispatched (not yet removed)
    // Blocked events. The reference pops an event whose recipient is still busy and re-pushes it at
    // the recipient's busy-until time with unchanged (sender, recipient, message_id) keys -- again
    // and again while the recipient keeps working through a burst. Equivalent formulation: a
    // blocked event's effective time IS busy_until[recipient] (which only moves when that agent
    // dispatches), so all blocked events of one agent share one time and are ordered by key alone.
    // They wait in a per-agent min-heap on the 64-bit key; the event loop takes the minimum of the
    // two main heaps and every blocked queue's (busy_until, smallest key). Same total order, but
    // each event is moved once instead of once per busy period.
    struct BEntry { uint64_t key; uint32_t slot; };
    struct BGreater { bool operator()(const BEntry& a, const BEntry& b) const { return a.key > b.key; } };
    std::vector<std::vector<BEntry>> bq;  // per agent
    std::vector<int32_t> blk;             // agents with a non-empty blocked queue
    void block(int32_t r, uint64_t key, uint32_t slot) {
        auto& q = bq[r];
        if (q.empty()) blk.push_back(r);
        q.push_back({key, slot});
        std::push_heap(q.begin(), q.end(), BGreater());
    }
    std::vector<Msg> pool;
    std::vector<uint32_t> free_slots;
    i64 next_msg_id = 1;
    i64 next_order_id = 0;
    i64 current_time = 0;
    i64 current_causal = 0;
    bool has_causal = false;
    i64 deliver_seq = 0;
    // books
    SideBook bids{{}, true}, asks{{}, false};
    std::vector<BookOrder> bo;
    std::vector<int32_t> bo_free;
    DenseIndex bo_index;  // order_id -> book slot
    // oracle state
    PyNum r_t = PyNum::I(0);
    i64 r_v = 0;
    PyNum mst = PyNum::F(0);
    double msv = 0;
    bool jump_consumed = false;
    bool dbg_oracle = getenv("T3_ORACLE_DUMP") != nullptr;  // debug: one line per OU step on stderr
    // outputs
    // The trace in its final order (trace.py semantics), built while the simulation runs.
    // Every handler logs at the kernel's dispatch time, which never decreases, so rows arrive in
    // nondecreasing time. All rows of one timestamp form a bucket: its quote rows come first (at
    // most one per side, holding the last value logged at that time, in order of first
    // appearance), then its order rows sorted stably by (order_id, owner). A bucket is closed by
    // the first row of a later time, so `trace` always holds the finished trace up to the open
    // bucket and nothing has to be merged or sorted after the run. (Dispatch times can go backwards
    // only with a negative latency; such a run is put right by repair_trace() when it ends.)
    Buf<OrderRow> trace;
    i64 bk_t = INT64_MIN;   // time of the open bucket
    size_t bk_start = 0;    // index of its first order row
    int bk_nq = 0;          // quote sides seen at this time ...
    int8_t bk_side[2] = {0, 0};  // ... in order of first appearance
    bool bk_has[2] = {false, false};
    i64 bk_qp[2] = {0, 0}, bk_qs[2] = {0, 0};  // last price / size logged per side
    bool trace_bad = false;  // a row arrived with an earlier time: the buckets are not the final order
    // Rows below these counts are final and may be read by another thread while the run goes on
    // (trace rows keep only `kind` open: a fill becomes a final fill, kind 4, when the run ends).
    alignas(64) std::atomic<size_t> trace_closed{0};
    alignas(64) std::atomic<size_t> lrec_done{0};
    alignas(64) char pad_after_counts = 0;
    DenseIndex last_fill;    // order_id -> index of its latest EXECUTED row (final fill, kind 4)

    void close_bucket() {
        size_t k = trace.size() - bk_start;
        OrderRow* b = trace.b + bk_start;
        if (k > 1) {
            auto less = [](const OrderRow& x, const OrderRow& y) {
                return x.order_id != y.order_id ? x.order_id < y.order_id : x.owner < y.owner;
            };
            if (k <= 32) {  // short and usually already in order: stable insertion sort
                for (size_t i = 1; i < k; i++) {
                    if (!less(b[i], b[i - 1])) continue;
                    const OrderRow x = b[i];
                    size_t j = i;
                    do { b[j] = b[j - 1]; j--; } while (j > 0 && less(x, b[j - 1]));
                    b[j] = x;
                }
            } else {
                std::stable_sort(b, b + k, less);
            }
        }
        if (bk_nq) {
            for (int i = 0; i < bk_nq; i++) trace.next();  // room for the quote rows (may move the buffer)
            b = trace.b + bk_start;
            if (k) memmove((void*)(b + bk_nq), (void*)b, k * sizeof(OrderRow));
            for (int i = 0; i < bk_nq; i++) {
                const int sd = bk_side[i];
                row_fits(bk_qs[sd], -1);
                b[i] = OrderRow{bk_t, bk_qp[sd], (int32_t)bk_qs[sd], -1, 0, 5, (Side)sd};
            }
            b += bk_nq;
            bk_has[0] = bk_has[1] = false;
        }
        const size_t base = (size_t)(b - trace.b);
        for (size_t i = 0; i < k; i++)
            if (b[i].kind == 3) last_fill.set(b[i].order_id, (uint32_t)(base + i));
        bk_nq = 0;
    }
    void trace_at(i64 t) {
        if (t == bk_t) return;
        if (t < bk_t) trace_bad = true;
        close_bucket();
        bk_t = t;
        bk_start = trace.size();
        trace_closed.store(bk_start, std::memory_order_release);
    }
    // Rows did not arrive in time order, so the buckets are not the trace. Rebuild it by the full
    // rule (trace.py): the quote rows of one time that were logged consecutively are one group (one
    // row per side, last value, in order of first appearance); the order rows are sorted stably by
    // (t, order_id, owner); a quote row precedes the order rows of its time. The bucket array still
    // holds everything needed: quote rows in logging order, and order rows in an order that agrees
    // with the logging order wherever (t, order_id, owner) are equal.
    void repair_trace() {
        std::vector<OrderRow> q, o;
        for (const OrderRow* r = trace.b; r != trace.p; r++) (r->kind == 5 ? q : o).push_back(*r);
        std::vector<OrderRow> q2;
        q2.reserve(q.size());
        for (size_t i = 0; i < q.size();) {
            size_t j = i;
            int n_sides = 0;
            int8_t seq[2] = {0, 0};
            bool has[2] = {false, false};
            OrderRow last[2];
            while (j < q.size() && q[j].t == q[i].t) {
                const int sd = (int)q[j].side;
                if (!has[sd]) { has[sd] = true; seq[n_sides++] = (int8_t)sd; }
                last[sd] = q[j];
                j++;
            }
            for (int k = 0; k < n_sides; k++) q2.push_back(last[seq[k]]);
            i = j;
        }
        for (size_t i = 1; i < q2.size(); i++)
            if (q2[i].t < q2[i - 1].t) throw std::runtime_error("non-monotone quote log");
        std::stable_sort(o.begin(), o.end(), [](const OrderRow& x, const OrderRow& y) {
            if (x.t != y.t) return x.t < y.t;
            return x.order_id != y.order_id ? x.order_id < y.order_id : x.owner < y.owner;
        });
        OrderRow* w = trace.b;  // q2.size() + o.size() never exceeds the rows already there
        size_t oi = 0, qi = 0;
        while (oi < o.size() || qi < q2.size()) {
            if (qi < q2.size() && (oi >= o.size() || q2[qi].t <= o[oi].t)) *w++ = q2[qi++];
            else *w++ = o[oi++];
        }
        trace.p = w;
        std::fill(last_fill.v.begin(), last_fill.v.end(), NONE);
        for (size_t i = 0; i < trace.size(); i++)
            if (trace.b[i].kind == 3) last_fill.set(trace.b[i].order_id, (uint32_t)i);
    }
    // After the last event: close the open bucket and mark each order's final fill.
    void finish_trace_rows() {
        close_bucket();
        if (trace_bad) repair_trace();
        bk_t = INT64_MIN;
        bk_start = trace.size();
        if (trace.size() >= (size_t)NONE) throw std::runtime_error("too many trace rows");
        for (uint32_t p : last_fill.v)
            if (p != NONE) trace.b[p].kind = 4;
    }
    DenseIndex own_pos;  // OwnOrders position index shared by all agents
    Buf<LedgerRec> lrec;
    // The unit's card says no message ledger is scored: delivery records go to one scratch record.
    bool skip_ledger = false;
    LedgerRec ledger_scratch;
    struct LedgerSoA {  // ledger columns, built from lrec in t3_finish
        Raw<i64> seq, t_recv, t_send, latency, message_id, order_id, causal;
        Raw<int32_t> src, dst;
        Raw<int8_t> msg_type, has_send, has_order, has_causal;
    } ledger;
    // final trace columns (owned by the engine until t3_free)
    Raw<i64> tr_t, tr_price, tr_size, tr_order_id;
    Raw<int32_t> tr_agent;
    Raw<int8_t> tr_msg, tr_side;
    std::vector<int32_t> s_tr_msg_off, s_tr_side_off, s_l_msg_off;
    std::vector<char> s_tr_msg, s_tr_side, s_l_msg;
    int32_t exchange_id = 0;
    size_t est_wakeups = 0;

    // --------------------------------------------------------- messaging
    uint32_t new_slot() {
        if (!free_slots.empty()) { uint32_t s = free_slots.back(); free_slots.pop_back(); return s; }
        pool.emplace_back();
        return (uint32_t)pool.size() - 1;
    }
    // References into `pool` are only valid until the next new_msg/new_slot.
    uint32_t new_msg(int8_t type) {
        uint32_t s = new_slot();
        Msg& m = pool[s];
        m.type = type;
        if (__builtin_expect(next_msg_id > 0xFFFFFFFFll, 0)) throw std::runtime_error("message id exceeds heap key packing");
        m.id = (uint32_t)next_msg_id++;
        return s;
    }
    void heap_push(EventHeap& H, const HeapEntry& e) {
        if (hole == &H) { H.replace_top(e); hole = nullptr; }  // reuse the dispatched event's place
        else H.push(e);
    }
    // One latency draw from `rs` (ScenarioLatencyModel.get_latency for sender != recipient).
    static i64 latency_from(const Config& c, nprand::NpRandomState& rs) {
        double value;
        switch (c.lat_model) {
            case 1: value = rs.lognormal(c.lat_mu, c.lat_sigma); break;
            case 2: value = rs.uniform(c.lat_min_ns, c.lat_max_ns); break;
            case 3: {
                double base = c.lat_min_ns > 0 ? c.lat_min_ns : 1.0;
                value = base * (1.0 + rs.pareto(c.lat_alpha));
                break;
            }
            default: value = c.lat_mean_ns;
        }
        double lo = c.lat_min_ns, hi = c.lat_max_ns;
        const i64 r = py_round(value > hi ? hi : (value < lo ? lo : value));
        if (c.lat_model == 1) {
            // Would this draw round differently if lat_mu were a few ulps off? (Only the no-Python
            // launcher needs this: it derives lat_mu with libm's log, the reference with numpy's,
            // and the two may differ in the last bits on some CPUs. A flagged run is redone through
            // the Python path, so an unflagged result is exact for either log.)
            const double tol = std::fabs(value) * 6e-14 + 1e-300;  // > 16 ulp of lat_mu, relative
            const bool inside = value <= hi && value >= lo;  // not clamped: the rounding can flip
            const double d = std::fabs(value - (double)r);
            if (__builtin_expect((inside && 0.5 - d < tol) || std::fabs(value - hi) < tol || std::fabs(value - lo) < tol, 0))
                g_lat_ambiguous.store(true, std::memory_order_relaxed);
        }
        return r;
    }

    // Latency feed. Every send is between two different agents and draws exactly one latency from a
    // stream nothing else reads, so the k-th latency depends only on k. A helper thread computes the
    // same stream with the same code from a copy of the generator, running ahead of the event loop
    // during the timed run; the loop takes value k from a ring instead of computing it. Drawing
    // ahead is unobservable (the generator has no other consumer).
    // The helper starts producing as soon as the engine exists, so the ring is normally full before
    // the first event. Start-up is still wait-free: the loop draws inline (counting its draws, and
    // publishing the count so the helper's window follows it) until the helper has passed it, then
    // switches to the ring at its own draw index. A helper that is late (a slow thread start on a
    // cold machine) is picked up whenever it does get ahead; one that never runs leaves the loop
    // inline for the whole run.
    struct Feed {
        static constexpr uint32_t CAP = 1u << 13, MASK = CAP - 1, CHUNK = 64;
        alignas(64) std::atomic<uint32_t> tail{0};  // values produced (helper)
        alignas(64) std::atomic<uint32_t> head{0};  // values consumed (event loop, published lazily)
        alignas(64) std::atomic<int> go{1};         // 1 produce, 2 stop
        // 1 while the helper sleeps because the ring is full. It does not spin: a spinning thread
        // that shares a physical core with the event loop slows the loop, and it uses CPU quota
        // for nothing. The event loop wakes it once half the ring has been consumed.
        alignas(64) std::atomic<uint32_t> parked{0};
        std::thread th;
        static long futex(std::atomic<uint32_t>* w, int op, uint32_t val) {
            return syscall(SYS_futex, (uint32_t*)w, op, val, nullptr, nullptr, 0);
        }
        void wake() {
            parked.store(0, std::memory_order_release);
            futex(&parked, FUTEX_WAKE_PRIVATE, 1);
        }
        Config c;
        nprand::NpRandomState rs;
        i64 buf[CAP];
        void body() {
            uint32_t t = 0;
            while (go.load(std::memory_order_acquire) == 1) {
                uint32_t h = head.load(std::memory_order_acquire);
                if (CAP - (t - h) < CHUNK) {
                    // Full. Announce the sleep, look again (the loop may have consumed or asked to
                    // stop in between), then sleep until the loop clears `parked`.
                    parked.store(1, std::memory_order_seq_cst);
                    h = head.load(std::memory_order_seq_cst);
                    if (CAP - (t - h) >= CHUNK || go.load(std::memory_order_seq_cst) != 1) {
                        parked.store(0, std::memory_order_release);
                        continue;
                    }
                    futex(&parked, FUTEX_WAIT_PRIVATE, 1);
                    continue;
                }
                for (uint32_t i = 0; i < CHUNK; i++) buf[(t + i) & MASK] = latency_from(c, rs);
                t += CHUNK;
                tail.store(t, std::memory_order_release);
            }
        }
        void stop() {
            go.store(2, std::memory_order_seq_cst);
            wake();
        }
    };
    Feed* feed = nullptr;
    int feed_mode = 0;  // 0 inline, 1 inline while the helper catches up, 2 from the ring
    uint32_t f_head = 0, f_tail = 0;
    void feed_wait() {
        unsigned spins = 0;
        uint32_t t;
        feed->head.store(f_head, std::memory_order_seq_cst);
        while ((t = feed->tail.load(std::memory_order_acquire)) == f_head) {
            if (feed->parked.load(std::memory_order_seq_cst)) feed->wake();
            if (++spins < 4000) _mm_pause(); else { spins = 0; sched_yield(); }
        }
        f_tail = t;
    }
    i64 next_latency() {
        if (__builtin_expect(feed_mode == 2, 1)) {
            if (__builtin_expect(f_head == f_tail, 0)) feed_wait();
            i64 v = feed->buf[f_head & Feed::MASK];
            if ((++f_head & 63) == 0) {
                feed->head.store(f_head, std::memory_order_seq_cst);
                // Half of the ring is used up: time to wake a sleeping helper. (It only sleeps when
                // the ring is full, so this check, made every 64 draws, cannot come too late.)
                if (__builtin_expect(f_tail - f_head <= Feed::CAP / 2, 0)) {
                    f_tail = feed->tail.load(std::memory_order_acquire);
                    if (f_tail - f_head <= Feed::CAP / 2 && feed->parked.load(std::memory_order_seq_cst)) feed->wake();
                }
            }
            return v;
        }
        i64 v = latency_from(c, latency_rs);
        if (feed_mode == 1) {
            ++f_head;  // inline draws so far == index of the next value
            uint32_t t = feed->tail.load(std::memory_order_acquire);
            if (t > f_head) {
                f_tail = t;
                feed->head.store(f_head, std::memory_order_release);
                feed_mode = 2;
            } else if ((f_head & 63) == 0) {
                feed->head.store(f_head, std::memory_order_release);  // values below are not needed
            }
        }
        return v;
    }
    void feed_shutdown() {
        if (!feed) return;
        feed->stop();
        if (feed->th.joinable()) feed->th.join();
        delete feed;
        feed = nullptr;
        if (feed_mode) feed_mode = 0;
    }
    std::vector<std::thread> pf;  // asynchronous pre-fault helpers (launcher, single run)
    ~Engine() {
        feed_shutdown();
        for (auto& t : pf) if (t.joinable()) t.join();
    }
    // Kernel.send_message; `slot` may be shared by several recipients (broadcast) only if the
    // caller copies it per recipient (we copy, since ledger send info is per delivery).
    void send(int32_t sender, int32_t recipient, uint32_t slot, i64 delay = 0) {
        i64 sent_time = current_time + agent_comp_delays[sender] + delay;
        i64 latency = (sender == recipient) ? 0 : next_latency();
        i64 deliver_at = sent_time + latency;
        Msg& m = pool[slot];
        m.t_send = sent_time;
        m.t_recv = deliver_at;
        m.causal_parent = (uint32_t)current_causal;  // sends only happen inside a dispatch
        // If the recipient is busy past the delivery time, the reference would pop this event at
        // deliver_at (no effect other than current_time, which stays <= stop_time) and requeue it;
        // the recipient cannot dispatch before its busy-until time, so it is blocked for certain.
        // (The sender is the dispatching agent and never the recipient, so busy-until is final.)
        if (agent_current_times[recipient] > deliver_at && deliver_at <= c.stop_time)
            block(recipient, heap_key(sender, recipient, m.id), slot);
        else
            heap_push(mheap, HeapEntry::make(deliver_at, heap_key(sender, recipient, m.id), slot));
    }
    void set_wakeup(int32_t agent, i64 t) {
        uint32_t s = new_msg(M_WAKEUP);
        heap_push(wheap, HeapEntry::make(t, heap_key(agent, agent, pool[s].id), s));
    }

    // --------------------------------------------------------- logging (trace inputs)
    void log_order(Agent& a, int8_t kind, Side side, i64 price, i64 qty, i64 order_id) {
        trace_at(a.current_time);
        row_fits(qty, order_id);
        *trace.next() = OrderRow{a.current_time, price, (int32_t)qty, (int32_t)order_id, a.id, kind, side};
    }

    // --------------------------------------------------------- order book
    SideBook& book_for(Side s) { return s == BID ? bids : asks; }
    SideBook& opp_book(Side s) { return s == BID ? asks : bids; }
    int32_t bo_alloc(const OrderSnap& o) {
        int32_t k;
        if (!bo_free.empty()) { k = bo_free.back(); bo_free.pop_back(); }
        else { k = (int32_t)bo.size(); bo.emplace_back(); }
        bo[k].o = o;
        bo[k].prev = bo[k].next = -1;
        return k;
    }
    // price-level lookup: levels are stored worst-first (best at back)
    // returns index in levels vector, or -1
    int find_level(SideBook& b, i64 price) {
        // binary search on reversed ordering
        auto& L = b.levels;
        int lo = 0, hi = (int)L.size() - 1;
        while (lo <= hi) {
            int mid = (lo + hi) >> 1;
            if (L[mid].price == price) return mid;
            // worst-first: for bids ascending price; for asks descending price
            bool mid_worse = b.is_bid ? L[mid].price < price : L[mid].price > price;
            if (mid_worse) lo = mid + 1; else hi = mid - 1;
        }
        return -1;
    }
    void level_append(Level& lv, int32_t k) {
        bo[k].prev = lv.tail;
        bo[k].next = -1;
        if (lv.tail >= 0) bo[lv.tail].next = k; else lv.head = k;
        lv.tail = k;
        lv.total_qty += bo[k].o.quantity;
    }
    void level_unlink(Level& lv, int32_t k) {
        BookOrder& x = bo[k];
        if (x.prev >= 0) bo[x.prev].next = x.next; else lv.head = x.next;
        if (x.next >= 0) bo[x.next].prev = x.prev; else lv.tail = x.prev;
        lv.total_qty -= x.o.quantity;
    }
    void enter_order(const OrderSnap& o) {
        SideBook& b = book_for(o.side);
        int32_t k = bo_alloc(o);
        bo_index.set(o.order_id, (uint32_t)k);
        auto& L = b.levels;
        // find insertion point in worst-first vector: first index whose price is not worse
        int lo = 0, hi = (int)L.size();
        while (lo < hi) {
            int mid = (lo + hi) >> 1;
            bool mid_worse = b.is_bid ? L[mid].price < o.limit_price : L[mid].price > o.limit_price;
            if (mid_worse) lo = mid + 1; else hi = mid;
        }
        if (lo < (int)L.size() && L[lo].price == o.limit_price) {
            level_append(L[lo], k);
        } else {
            Level lv{o.limit_price, 0, -1, -1};
            L.insert(L.begin() + lo, lv);
            level_append(L[lo], k);
        }
    }
    // OrderBook.cancel_order: returns true and fills `out` if removed
    bool cancel_in_book(Side side, i64 price, i64 order_id, OrderSnap& out) {
        SideBook& b = book_for(side);
        if (b.levels.empty()) return false;
        int li = find_level(b, price);
        if (li < 0) return false;
        uint32_t kk = bo_index.get(order_id);
        if (kk == NONE) return false;
        int32_t k = (int32_t)kk;
        if (bo[k].o.side != side || bo[k].o.limit_price != price) return false;
        Level& lv = b.levels[li];
        level_unlink(lv, k);
        out = bo[k].o;
        bo_index.set(order_id, NONE);
        bo_free.push_back(k);
        if (lv.head < 0) b.levels.erase(b.levels.begin() + li);
        return true;
    }
    void exch_send(int32_t recipient, uint32_t slot) {
        int8_t t = pool[slot].type;
        i64 delay = (t == M_ORDER_ACCEPTED || t == M_ORDER_CANCELLED || t == M_ORDER_EXECUTED) ? c.pipeline_delay : 0;
        send(exchange_id, recipient, slot, delay);
    }
    void put_order(uint32_t s, const OrderSnap& o, i64 price) {
        Msg& m = pool[s];
        m.order_id = o.order_id; m.price = price; m.quantity = o.quantity;
        m.agent_id = o.agent_id; m.side = o.side;
    }
    void send_order_msg(int8_t type, int32_t recipient, const OrderSnap& o) {
        uint32_t s = new_msg(type);
        put_order(s, o, type == M_ORDER_EXECUTED ? o.fill_price : o.limit_price);
        exch_send(recipient, s);
    }
    // OrderBook.execute_order for a LimitOrder `order` against the opposite book.
    // Returns true if a match happened (order.quantity reduced).
    bool execute_order(OrderSnap& order) {
        SideBook& b = opp_book(order.side);
        if (b.levels.empty()) return false;
        Level& lv = b.best();
        bool match = order.side == BID ? order.limit_price >= lv.price : order.limit_price <= lv.price;
        if (!match) return false;
        int32_t k = lv.head;
        OrderSnap matched;
        if (order.quantity >= bo[k].o.quantity) {
            matched = bo[k].o;
            level_unlink(lv, k);
            bo_index.set(matched.order_id, NONE);
            bo_free.push_back(k);
            if (lv.head < 0) b.levels.pop_back();
        } else {
            matched = bo[k].o;
            matched.quantity = order.quantity;
            bo[k].o.quantity -= matched.quantity;
            lv.total_qty -= matched.quantity;
        }
        matched.fill_price = matched.limit_price;
        matched.has_fill = true;
        OrderSnap filled = order;
        filled.quantity = matched.quantity;
        filled.fill_price = matched.fill_price;
        filled.has_fill = true;
        order.quantity -= filled.quantity;
        send_order_msg(M_ORDER_EXECUTED, matched.agent_id, matched);
        send_order_msg(M_ORDER_EXECUTED, order.agent_id, filled);
        return true;
    }
    void handle_limit_order(OrderSnap order) {
        if (order.quantity <= 0) return;      // discarded (warning in ABIDES)
        if (order.limit_price < 0) return;    // discarded
        for (;;) {
            if (c.stp_policy) {
                SideBook& opp = opp_book(order.side);
                if (!opp.levels.empty()) {
                    Level& lv = opp.best();
                    bool match = order.side == BID ? order.limit_price >= lv.price : order.limit_price <= lv.price;
                    if (match) {
                        OrderSnap& resting = bo[lv.head].o;
                        if (resting.agent_id == order.agent_id) {
                            if (c.stp_policy == 2) {
                                OrderSnap removed;
                                if (cancel_in_book(resting.side, resting.limit_price, resting.order_id, removed)) {
                                    send_order_msg(M_ORDER_CANCELLED, removed.agent_id, removed);
                                    continue;
                                }
                            } else {
                                send_order_msg(M_ORDER_CANCELLED, order.agent_id, order);
                                break;
                            }
                        }
                    }
                }
            }
            if (execute_order(order)) {
                if (order.quantity <= 0) break;
            } else {
                enter_order(order);
                send_order_msg(M_ORDER_ACCEPTED, order.agent_id, order);
                break;
            }
        }
        // Best bid / ask after this order (the bid is logged before the ask).
        const bool hb = !bids.levels.empty(), ha = !asks.levels.empty();
        if (hb || ha) {
            trace_at(agents[exchange_id].current_time);
            if (hb) {
                if (!bk_has[0]) { bk_has[0] = true; bk_side[bk_nq++] = 0; }
                bk_qp[0] = bids.best().price; bk_qs[0] = bids.best().total_qty;
            }
            if (ha) {
                if (!bk_has[1]) { bk_has[1] = true; bk_side[bk_nq++] = 1; }
                bk_qp[1] = asks.best().price; bk_qs[1] = asks.best().total_qty;
            }
        }
    }

    // --------------------------------------------------------- oracle
    // compute_fundamental_at_timestamp(ts, v_adj, pt, pv)
    i64 compute_fundamental(PyNum ts, double v_adj, bool v_adj_is_float, PyNum pt, i64 pv) {
        PyNum d = py_sub(ts, pt);
        double dd = d.as_double();
        double mu = (double)c.r_bar;
        double gamma = c.kappa, theta = c.fund_vol;
        double loc = mu + (double)(pv - c.r_bar) * std::exp(-gamma * dd);
        double scale = std::sqrt(std::pow(theta, 2.0) / (2 * gamma) * (1 - std::exp(-2 * gamma * dd)));
        double v = oracle_rs.normal(loc, scale);
        (void)v_adj_is_float;
        v += v_adj;
        if (!(0 < v)) v = 0;  // max(0, v): returns 0 unless v > 0 (NaN stays... not reachable)
        i64 vi = py_round(v);
        if (c.has_sched_jump && !jump_consumed && py_cmp(ts, PyNum::I(c.sched_jump_time)) >= 0) {
            vi = std::max<i64>(0, vi + c.sched_jump_mag);
            jump_consumed = true;
        }
        r_t = ts;
        r_v = vi;
        if (dbg_oracle) {
            if (ts.is_float) fprintf(stderr, "F f %.17g %.17g %lld\n", ts.f, v_adj, (long long)vi);
            else fprintf(stderr, "F i %lld %.17g %lld\n", (long long)ts.i, v_adj, (long long)vi);
        }
        return vi;
    }
    void draw_megashock_value() {
        double v = oracle_rs.normal(c.megashock_mean, std::sqrt(c.megashock_var));
        msv = (oracle_rs.randint(0, 2) == 0) ? v : -v;
    }
    i64 advance_fundamental(i64 current) {
        PyNum pt = r_t;
        i64 pv = r_v;
        if (py_cmp(PyNum::I(current), pt) <= 0) return pv;
        PyNum m = mst;
        double mv = msv;
        while (py_cmp(m, PyNum::I(current)) < 0) {
            i64 v = compute_fundamental(m, mv, true, pt, pv);
            pt = m;
            pv = v;
            double e = global_rs.exponential(1.0 / c.megashock_lambda_a);
            i64 ei = (i64)e;  // int() truncation
            m = py_add_int(pt, ei);
            draw_megashock_value();
            mv = msv;
            mst = m;
        }
        return compute_fundamental(PyNum::I(current), 0.0, false, pt, pv);
    }
    static PyNum py_add_int(PyNum a, i64 b) {
        if (!a.is_float) return PyNum::I(a.i + b);
        return PyNum::F(a.f + (double)b);
    }
    i64 observe_price(i64 t, Agent& a) {
        // The oracle was built with oracle_close (16:00), not the exchange close: agents that act on a
        // spread response arriving after the scenario close still advance the OU to their own time.
        i64 r = (t >= c.oracle_close) ? advance_fundamental(c.oracle_close - 1) : advance_fundamental(t);
        if (a.sigma_n == 0) return r;
        return py_round(a.rs.normal((double)r, std::sqrt(a.sigma_n)));
    }

    // --------------------------------------------------------- agent behaviour
    void place_limit_order(Agent& a, i64 qty, Side side, i64 price) {
        OrderSnap o{next_order_id++, price, qty, 0, a.id, side, false};
        if (qty <= 0) return;  // create_limit_order returns None (quantity is always >= 1 here)
        a.orders.put(o);
        uint32_t s = new_msg(M_LIMIT_ORDER);
        put_order(s, o, price);
        send(a.id, exchange_id, s);
        log_order(a, 0, side, price, qty, o.order_id);
    }
    void cancel_all_orders(Agent& a) {
        // iterate a snapshot of alive entries in insertion order (dict is not mutated here)
        for (size_t i = 0; i < a.orders.v.size(); i++) {
            auto& e = a.orders.v[i];
            if (!e.alive) continue;
            uint32_t s = new_msg(M_CANCEL_ORDER);
            put_order(s, OrderSnap{e.order_id, e.limit_price, e.quantity, 0, a.id, e.side, false}, e.limit_price);
            send(a.id, exchange_id, s);
        }
    }
    void act(Agent& a) {
        bool hb = a.kb_has_bid && a.kb_bid != 0, ha = a.kb_has_ask && a.kb_ask != 0;  // Python truthiness
        i64 bid = a.kb_bid, ask = a.kb_ask;
        switch (a.kind) {
            case A_NOISE: {
                double n = a.rs.normal(a.order_size_mean, a.order_size_std);
                i64 size = std::max<i64>(1, py_round(n));
                bool buy = a.rs.randint(0, 2) != 0;
                i64 offset = a.rs.randint(0, a.price_offset_ticks + 1);
                if (buy) {
                    i64 anchor = ha ? ask : (hb ? bid : a.reference_price);
                    place_limit_order(a, size, BID, anchor + offset);
                } else {
                    i64 anchor = hb ? bid : (ha ? ask : a.reference_price);
                    place_limit_order(a, size, ASK, anchor - offset);
                }
                break;
            }
            case A_MM: {
                i64 mid = (hb && ha) ? floor_div(bid + ask, 2) : a.reference_price;
                cancel_all_orders(a);
                i64 half = a.spread_ticks / 2;
                for (i64 lvl = 0; lvl < a.depth_levels; lvl++) {
                    place_limit_order(a, a.size_per_level, BID, mid - half - lvl);
                    place_limit_order(a, a.size_per_level, ASK, mid + half + lvl);
                }
                break;
            }
            case A_VALUE: {
                double mid;
                if (hb && ha) mid = (double)(bid + ask) / 2.0;
                else if (hb) mid = (double)bid;
                else if (ha) mid = (double)ask;
                else return;
                i64 fundamental = observe_price(a.current_time, a);
                i64 size = std::max<i64>(1, py_round(a.order_size_mean));
                if (mid < (double)(fundamental - a.threshold_ticks) && ha)
                    place_limit_order(a, size, BID, ask);
                else if (mid > (double)(fundamental + a.threshold_ticks) && hb)
                    place_limit_order(a, size, ASK, bid);
                break;
            }
            case A_MOMENTUM: {
                double mid;
                if (hb && ha) mid = (double)(bid + ask) / 2.0;
                else if (hb) mid = (double)bid;
                else if (ha) mid = (double)ask;
                else return;
                auto& h = a.mid_history;
                h.push_back(mid);
                if ((i64)h.size() > a.lookback + 1) h.erase(h.begin());
                if ((i64)h.size() <= a.lookback) return;
                double past = h[0];
                i64 size = std::max<i64>(1, py_round(a.order_size_mean));
                if (mid > past + (double)a.threshold_ticks && ha)
                    place_limit_order(a, size, BID, ask);
                else if (mid < past - (double)a.threshold_ticks && hb)
                    place_limit_order(a, size, ASK, bid);
                break;
            }
            default: break;
        }
    }
    static i64 floor_div(i64 a, i64 b) {
        i64 q = a / b;
        if ((a % b != 0) && ((a < 0) != (b < 0))) q--;
        return q;
    }

    void trader_wakeup(Agent& a, i64 t) {
        a.current_time = t;
        if (a.first_wake) {
            a.first_wake = false;
            uint32_t s = new_msg(M_MKT_CLOSE_PRICE_REQ);
            send(a.id, exchange_id, s);
        }
        if (!a.has_mkt_hours) {
            uint32_t s = new_msg(M_MKT_HOURS_REQ);
            send(a.id, exchange_id, s);
        }
        // ScheduledAgent.wakeup
        if (!a.has_mkt_hours || a.mkt_closed) return;
        set_wakeup(a.id, t + a.interval_ns);
        uint32_t s = new_msg(M_QUERY_SPREAD);
        send(a.id, exchange_id, s);
        a.awaiting_spread = true;
    }
    void trader_receive(Agent& a, i64 t, const Msg& m) {
        a.current_time = t;
        bool had = a.has_mkt_hours;
        switch (m.type) {
            case M_MKT_HOURS: a.has_mkt_hours = true; break;
            case M_MKT_CLOSED: a.mkt_closed = true; break;
            case M_ORDER_EXECUTED: {
                log_order(a, 3, m.side, m.price, m.quantity, m.order_id);
                auto* e = a.orders.find(m.order_id);
                if (e) {
                    if (m.quantity >= e->quantity) a.orders.erase(m.order_id);
                    else e->quantity -= m.quantity;
                }
                break;
            }
            case M_ORDER_ACCEPTED: log_order(a, 1, m.side, m.price, m.quantity, m.order_id); break;
            case M_ORDER_CANCELLED: {
                log_order(a, 2, m.side, m.price, m.quantity, m.order_id);
                if (a.orders.find(m.order_id)) a.orders.erase(m.order_id);
                break;
            }
            case M_QUERY_SPREAD_RESP: {
                if (m.flags & F_CLOSED) a.mkt_closed = true;
                a.kb_has_bid = (m.flags & F_HAS_BID) != 0; a.kb_bid = m.price;
                a.kb_has_ask = (m.flags & F_HAS_ASK) != 0; a.kb_ask = m.quantity;
                break;
            }
            default: break;  // MarketClosePriceMsg: last_trade only (not observable)
        }
        if (a.has_mkt_hours && !had) set_wakeup(a.id, c.mkt_open + 0);
        // ScheduledAgent.receive_message
        if (a.awaiting_spread && m.type == M_QUERY_SPREAD_RESP) {
            if (!a.mkt_closed) act(a);
            a.awaiting_spread = false;
        }
    }

    std::vector<int32_t> close_price_subs;
    void exchange_wakeup(Agent& ex, i64 t) {
        ex.current_time = t;
        if (t >= c.mkt_close) {
            // One MarketClosePriceMsg object (one message_id) delivered to every subscriber.
            uint32_t base = new_msg(M_MKT_CLOSE_PRICE);
            uint32_t id = pool[base].id;
            for (size_t i = 0; i < close_price_subs.size(); i++) {
                uint32_t s = base;
                if (i > 0) {
                    s = new_slot();
                    pool[s].type = M_MKT_CLOSE_PRICE;
                    pool[s].id = id;
                }
                send(exchange_id, close_price_subs[i], s);
            }
            if (close_price_subs.empty()) free_slots.push_back(base);
        }
    }
    void exchange_receive(Agent& ex, i64 t, int32_t sender, const Msg& m) {
        ex.current_time = t;
        agent_comp_delays[exchange_id] = c.exch_computation_delay;
        bool is_order_msg = m.type == M_LIMIT_ORDER || m.type == M_CANCEL_ORDER;
        bool is_query = m.type == M_QUERY_SPREAD;
        if (t > c.mkt_close) {
            if (is_order_msg || !is_query) {
                uint32_t s = new_msg(M_MKT_CLOSED);
                exch_send(sender, s);
                return;
            }
        }
        switch (m.type) {
            case M_MKT_HOURS_REQ: {
                agent_comp_delays[exchange_id] = 0;
                uint32_t s = new_msg(M_MKT_HOURS);
                exch_send(sender, s);
                break;
            }
            case M_MKT_CLOSE_PRICE_REQ: close_price_subs.push_back(sender); break;
            case M_QUERY_SPREAD: {
                uint32_t s = new_msg(M_QUERY_SPREAD_RESP);
                Msg& r = pool[s];
                bool hb = !bids.levels.empty(), ha = !asks.levels.empty();
                r.price = hb ? bids.best().price : 0;     // best bid
                r.quantity = ha ? asks.best().price : 0;  // best ask
                r.flags = (hb ? F_HAS_BID : 0) | (ha ? F_HAS_ASK : 0) | (t > c.mkt_close ? F_CLOSED : 0);
                exch_send(sender, s);
                break;
            }
            case M_LIMIT_ORDER:
                handle_limit_order(OrderSnap{m.order_id, m.price, m.quantity, 0, m.agent_id, m.side, false});
                break;
            case M_CANCEL_ORDER: {
                OrderSnap removed;
                if (cancel_in_book(m.side, m.price, m.order_id, removed))
                    send_order_msg(M_ORDER_CANCELLED, m.agent_id, removed);
                break;
            }
            default: break;
        }
    }

    // --------------------------------------------------------- kernel
#ifdef T3_STATS
    long st_iter = 0, st_m = 0, st_msz = 0, st_wsz = 0, st_req = 0;
#endif
    void run() {
        // Kernel.initialize: kernel_initializing (exchange wakes at close), then kernel_starting.
        set_wakeup(exchange_id, c.mkt_close);
        for (auto& a : agents) set_wakeup(a.id, c.start_time);
        current_time = c.start_time;
        if (feed) feed_mode = 1;
        const u128 kNoEvent = ~(u128)0;
        for (;;) {
            // Next event = minimum over the message heap, the wakeup heap and the blocked queues.
            u128 best = kNoEvent;
            EventHeap* H = nullptr;
            if (!mheap.empty()) { best = mheap.top().k; H = &mheap; }
            if (!wheap.empty() && wheap.top().k < best) { best = wheap.top().k; H = &wheap; }
            int bi = -1;
            for (size_t i = 0; i < blk.size(); i++) {
                const int32_t br = blk[i];
                const u128 k = HeapEntry::make(agent_current_times[br], bq[br].front().key, 0).k;
                if (k < best) { best = k; bi = (int)i; }
            }
            if (best == kNoEvent || !current_time || current_time > c.stop_time) break;
            HeapEntry e;
            int32_t r;
            if (bi >= 0) {
                // A blocked event becomes due exactly at its recipient's busy-until time.
                r = blk[bi];
                auto& q = bq[r];
                e = HeapEntry::make(agent_current_times[r], q.front().key, q.front().slot);
                std::pop_heap(q.begin(), q.end(), BGreater());
                q.pop_back();
                if (q.empty()) { blk[bi] = blk.back(); blk.pop_back(); }
                current_time = e.time();
                hole = nullptr;
            } else {
                e = H->top();
#ifdef T3_STATS
                st_iter++; st_m += (H == &mheap); st_msz += mheap.h.size(); st_wsz += wheap.h.size();
#endif
                current_time = e.time();
                r = e.recipient();
                if (agent_current_times[r] > current_time) {
#ifdef T3_STATS
                    st_req++;
#endif
                    H->pop();
                    block(r, e.key(), e.slot);
                    continue;
                }
                hole = H;
            }
            // A heap event stays at the top of its heap as a "hole": the first event the handler
            // schedules into that heap takes its place (one sift instead of pop + push); otherwise
            // it is popped below.
            const Msg m = pool[e.slot];  // by value: the slot is recycled and the pool may grow
            free_slots.push_back(e.slot);
            const bool is_wakeup = m.type == M_WAKEUP;
            current_causal = m.id; has_causal = true;
            LedgerRec* L = skip_ledger ? &ledger_scratch : lrec.next();
            L->t_recv = is_wakeup ? current_time : m.t_recv;
            L->t_send = m.t_send;
            L->order_id = m.order_id;
            L->message_id = m.id;
            L->causal = m.causal_parent;
            L->src = (uint16_t)e.sender();
            L->dst = (uint16_t)r;
            L->type = m.type;
            if (!skip_ledger) lrec_done.store((size_t)(L - lrec.b) + 1, std::memory_order_release);
            Agent& a = agents[r];
            if (is_wakeup) {
                agent_current_times[r] = current_time;
                if (a.kind == A_EXCHANGE) exchange_wakeup(a, current_time);
                else trader_wakeup(a, current_time);
                agent_current_times[r] += agent_comp_delays[r];
            } else {
                agent_current_times[r] = current_time + agent_comp_delays[r];
                if (a.kind == A_EXCHANGE) exchange_receive(a, current_time, e.sender(), m);
                else trader_receive(a, current_time, m);
            }
            if (hole) { hole->pop(); hole = nullptr; }
        }
        if (feed) feed->stop();
        finish_trace_rows();
    }
};

}  // namespace t3

// ======================================================================= C API (ctypes)
using namespace t3;

extern "C" {

struct T3Result {
    // trace
    int64_t n_trace;
    int64_t *t_ns, *price, *size, *order_id;
    int32_t* agent_id;
    int8_t *msg_type, *side;  // msg_type: 0 SUB 1 ACC 2 CAN 3 PARTIAL 4 FILLED 5 QUOTE; side 0 BID 1 ASK
    // ledger
    int64_t n_ledger;
    int64_t *l_seq, *l_t_recv, *l_t_send, *l_latency, *l_message_id, *l_order_id, *l_causal;
    int32_t *l_src, *l_dst;
    int8_t *l_msg_type, *l_has_send, *l_has_order, *l_has_causal;
    double sim_seconds;
    void* owner;  // Engine* holding the buffers above
    // Arrow utf8 buffers (int32 offsets[n+1] + bytes) for the string columns
    int32_t *tr_msg_off, *tr_side_off, *l_msg_off;
    char *tr_msg_data, *tr_side_data, *l_msg_data;
    int64_t tr_msg_bytes, tr_side_bytes, l_msg_bytes;
};

static const char* TRACE_NAMES[6] = {"ORDER_SUBMITTED", "ORDER_ACCEPTED", "ORDER_CANCELLED",
                                     "PARTIAL_FILL",    "ORDER_FILLED",   "QUOTE_UPDATE"};
static const char* SIDE_NAMES[2] = {"BID", "ASK"};

// The launcher writes the string columns from the codes and clears this.
static bool g_want_utf8 = true;
// Threads finish_ledger may use to fill the columns (the launcher raises it for a single run).
static int g_ledger_threads = 1;
// Trace assembly threads (the launcher raises it for a single run).
static int g_trace_threads = 1;
// Populate the output buffers from helper threads while the simulation runs (launcher, single run).
static bool g_async_prefault = false;
// The launcher sets this when the unit's card declares that no message ledger is required.
static bool g_skip_ledger = false;

// Build Arrow utf8 (offsets, data) for names[codes].
static void build_utf8(const int8_t* codes, size_t n, const char* const* names, int n_names,
                       std::vector<int32_t>& off, std::vector<char>& data) {
    int32_t len[32];
    for (int k = 0; k < n_names; k++) len[k] = (int32_t)strlen(names[k]);
    off.resize(n + 1);
    off[0] = 0;
    for (size_t i = 0; i < n; i++) off[i + 1] = off[i] + len[codes[i]];
    data.resize((size_t)off[n] + 1);
    char* w = data.data();
    for (size_t i = 0; i < n; i++) { memcpy(w, names[codes[i]], len[codes[i]]); w += len[codes[i]]; }
}

// cfg_i / cfg_f: scalar config (layout documented in native_sim.py).
// agents_i: n_agents x 8 int64 [kind, interval_ns, price_offset_ticks, reference_price,
//            spread_ticks, depth_levels, size_per_level, threshold_ticks]; plus lookback in [7]? see py
// agents_f: n_agents x 4 double [order_size_mean, order_size_std, sigma_n, lookback(as double)]
// C API mirrors the reference adapter's phases so that timing scopes match:
//   t3_create   == build_config (config parsing, RNG seeding chain, agent construction) -- untimed
//   t3_simulate == abides.run   (the event loop)                                      -- timed
//   t3_finish   == extract_trace / extract_message_trace (output assembly)             -- untimed
// No C++ exception ever crosses the ctypes boundary: failures return nullptr / -1 so Python
// falls back to the exact reference path.
// CPUs this process can use concurrently: min(affinity mask, cgroup quota). T3_LAT_THREAD=0/1 overrides.
static double usable_cpus() {
    if (const char* e = getenv("T3_LAT_THREAD")) return atoi(e) ? 64.0 : 0.0;
    cpu_set_t set;
    double n = 1.0;
    if (sched_getaffinity(0, sizeof set, &set) == 0) n = (double)CPU_COUNT(&set);
    if (FILE* f = fopen("/sys/fs/cgroup/cpu.max", "r")) {  // cgroup v2: "<quota|max> <period>"
        char q[32];
        double period = 0;
        if (fscanf(f, "%31s %lf", q, &period) == 2 && strcmp(q, "max") != 0 && period > 0) n = std::min(n, atof(q) / period);
        fclose(f);
    } else if (FILE* g = fopen("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", "r")) {  // cgroup v1
        double quota = -1, period = 0;
        if (fscanf(g, "%lf", &quota) != 1) quota = -1;
        fclose(g);
        if (FILE* h = fopen("/sys/fs/cgroup/cpu/cpu.cfs_period_us", "r")) {
            if (fscanf(h, "%lf", &period) != 1) period = 0;
            fclose(h);
        }
        if (quota > 0 && period > 0) n = std::min(n, quota / period);
    }
    return n;
}

static Engine* t3_create_impl(const int64_t* ci, const double* cf, int32_t n_agents, const int64_t* ai, const double* af) {
    Engine* E = new Engine();
    Config& c = E->c;
    c.seed = ci[0]; c.start_time = ci[1]; c.stop_time = ci[2]; c.mkt_open = ci[3]; c.mkt_close = ci[4];
    c.default_computation_delay = ci[5]; c.pipeline_delay = ci[6]; c.exch_computation_delay = ci[7];
    c.stp_policy = (int)ci[8]; c.r_bar = ci[9]; c.has_sched_jump = ci[10] != 0; c.sched_jump_time = ci[11];
    c.sched_jump_mag = ci[12]; c.lat_model = (int)ci[13]; c.oracle_close = ci[14];
    c.kappa = cf[0]; c.fund_vol = cf[1]; c.megashock_lambda_a = cf[2]; c.megashock_mean = cf[3];
    c.megashock_var = cf[4]; c.lat_mean_ns = cf[5]; c.lat_sigma = cf[6]; c.lat_min_ns = cf[7];
    c.lat_max_ns = cf[8]; c.lat_alpha = cf[9]; c.lat_mu = cf[10];

    // build_config seeding chain: np.random.seed(seed); oracle RS; oracle ctor global/oracle draws;
    // exchange RS; each agent RS; latency RS; kernel RS.
    E->global_rs.seed((uint32_t)c.seed);
    E->oracle_rs.seed((uint32_t)E->global_rs.randint_u64(0, 4294967296ULL));
    double ms_delta = E->global_rs.exponential(1.0 / c.megashock_lambda_a);
    E->mst = PyNum::F((double)c.mkt_open + ms_delta);
    E->draw_megashock_value();
    E->r_t = PyNum::I(c.mkt_open);
    E->r_v = c.r_bar;

    if (n_agents + 1 > 0xFFFF) throw std::runtime_error("too many agents for heap key packing");
    E->agents.resize(n_agents + 1);
    for (int32_t i = 0; i <= n_agents; i++) {
        Agent& a = E->agents[i];
        a.id = i;
        a.orders.idx = &E->own_pos;
        a.rs.seed((uint32_t)E->global_rs.randint_u64(0, 4294967296ULL));
        if (i == 0) { a.kind = A_EXCHANGE; continue; }
        const int64_t* p = ai + (size_t)(i - 1) * 8;
        const double* q = af + (size_t)(i - 1) * 4;
        a.kind = (AgentKind)p[0];
        a.interval_ns = p[1];
        a.price_offset_ticks = p[2];
        a.reference_price = p[3];
        a.spread_ticks = p[4];
        a.depth_levels = p[5];
        a.size_per_level = p[6];
        a.threshold_ticks = p[7];
        a.order_size_mean = q[0];
        a.order_size_std = q[1];
        a.sigma_n = q[2];
        a.lookback = (int64_t)q[3];
    }
    E->latency_rs.seed((uint32_t)E->global_rs.randint_u64(0, 4294967296ULL));
    (void)E->global_rs.randint_u64(0, 4294967296ULL);  // kernel RS (unused by the kernel)

    E->agent_current_times.assign(n_agents + 1, c.start_time);
    E->agent_comp_delays.assign(n_agents + 1, c.default_computation_delay);
    // Size output buffers from the schedule: wakeups per agent x ledger rows per wakeup by kind
    // (a market maker re-quotes 2*depth orders and cancels them every wakeup). Measured on the
    // public configs; under-estimates only mean ordinary vector growth (never a correctness issue).
    double wakeups = 0, est_ledger = 0;
    for (int32_t i = 1; i <= n_agents; i++) {
        const Agent& a = E->agents[i];
        double w = (double)(c.stop_time - c.mkt_open) / (double)std::max<int64_t>(1, a.interval_ns) + 3;
        wakeups += w;
        est_ledger += w * (a.kind == A_MM ? 4.0 + 7.0 * (double)a.depth_levels : (a.kind == A_NOISE ? 8.0 : 7.0));
    }
    size_t W = (size_t)std::min(wakeups, 5e7);
    E->est_wakeups = W;
    size_t L = (size_t)std::min(est_ledger * 1.3, 4e8) + 1024;
    E->trace.keep_old = E->lrec.keep_old = true;
    E->trace.reserve(L + L / 4);  // order rows plus up to two quote rows per handled order
    E->skip_ledger = g_skip_ledger;
    E->lrec.reserve(E->skip_ledger ? 1 : L);
    if (g_async_prefault && E->lrec.bytes >= 4096 && madvise((void*)E->lrec.b, 4096, MADV_POPULATE_WRITE) == 0) {
        // The output buffers are populated by helper threads while the simulation starts.
        // (Without MADV_POPULATE_WRITE the only way to pre-fault is to store, which must finish first.)
        E->pf.emplace_back([E] { E->trace.prefault_async_body(E->trace.b, E->trace.bytes); });
        E->pf.emplace_back([E] { E->lrec.prefault_async_body(E->lrec.b, E->lrec.bytes); });
    } else {
        // The reservations are deliberately generous (a too-small buffer means a copy mid-run), so
        // only the part the public scenarios actually fill, plus a margin, is populated up front.
        E->trace.prefault(0.5);
        if (!E->skip_ledger) E->lrec.prefault(0.74);
    }
    E->pool.reserve(4096);
    E->free_slots.reserve(4096);
    E->wheap.h.reserve((size_t)n_agents + 64);
    E->mheap.h.reserve(1024);
    E->bq.resize((size_t)n_agents + 1);
    // Helper thread for the latency stream: only for the models with a costly draw, and only when
    // this process may really run two threads at once (affinity mask and cgroup CPU quota).
    if ((c.lat_model == 1 || c.lat_model == 3) && usable_cpus() >= 2.0) {
        try {
            Engine::Feed* F = new Engine::Feed();
            F->c = c;
            F->rs = E->latency_rs;
            E->feed = F;
            F->th = std::thread([F] { F->body(); });
        } catch (...) {
            delete E->feed;
            E->feed = nullptr;
        }
    }
    E->blk.reserve((size_t)n_agents + 1);

    return E;
}

void* t3_create(const int64_t* ci, const double* cf, int32_t n_agents, const int64_t* ai, const double* af) {
    try {
        return t3_create_impl(ci, cf, n_agents, ai, af);
    } catch (...) {
        return nullptr;
    }
}

int t3_simulate(void* handle) {
    try {
        static_cast<Engine*>(handle)->run();
        return 0;
    } catch (std::exception& e) {
        if (getenv("T3_PHASES")) fprintf(stderr, "engine: %s\n", e.what());
        return -1;
    } catch (...) {
        return -1;
    }
}

void t3_destroy(void* handle) { delete static_cast<Engine*>(handle); }

// ---------------------------------------------------------------- trace columns
// Trace columns for the Python path (the launcher encodes straight from Engine::trace).
static void finish_trace(Engine* E, T3Result* R) {
    const OrderRow* rows = E->trace.b;
    const size_t n = E->trace.size();
    R->n_trace = (int64_t)n;
    E->tr_t.resize(n); E->tr_price.resize(n); E->tr_size.resize(n); E->tr_order_id.resize(n);
    E->tr_agent.resize(n); E->tr_msg.resize(n); E->tr_side.resize(n);
    R->t_ns = E->tr_t.data(); R->price = E->tr_price.data(); R->size = E->tr_size.data();
    R->order_id = E->tr_order_id.data(); R->agent_id = E->tr_agent.data(); R->msg_type = E->tr_msg.data();
    R->side = E->tr_side.data();
    for (size_t w = 0; w < n; w++) {
        const OrderRow& r = rows[w];
        R->t_ns[w] = r.t; R->agent_id[w] = r.owner; R->msg_type[w] = r.kind; R->side[w] = r.side;
        R->price[w] = r.price; R->size[w] = r.size; R->order_id[w] = r.order_id;
    }
    if (g_want_utf8) {
        build_utf8(E->tr_msg.data(), n, TRACE_NAMES, 6, E->s_tr_msg_off, E->s_tr_msg);
        build_utf8(E->tr_side.data(), n, SIDE_NAMES, 2, E->s_tr_side_off, E->s_tr_side);
        R->tr_msg_off = E->s_tr_msg_off.data(); R->tr_msg_data = E->s_tr_msg.data();
        R->tr_msg_bytes = E->s_tr_msg_off[n];
        R->tr_side_off = E->s_tr_side_off.data(); R->tr_side_data = E->s_tr_side.data();
        R->tr_side_bytes = E->s_tr_side_off[n];
    }
}

// Ledger columns from the delivery records (already in delivery-seq order).
static void finish_ledger(Engine* E, T3Result* R) {
    auto& L = E->ledger;
    size_t m = E->lrec.size();
    {
        for (auto* v : {&L.seq, &L.t_recv, &L.t_send, &L.latency, &L.message_id, &L.order_id, &L.causal}) v->resize(m);
        L.src.resize(m); L.dst.resize(m);
        for (auto* v : {&L.msg_type, &L.has_send, &L.has_order, &L.has_causal}) v->resize(m);
        const LedgerRec* rec = E->lrec.b;
        auto fill = [&](size_t lo, size_t hi) {
          for (size_t i = lo; i < hi; i++) {
            const LedgerRec& x = rec[i];
            const bool w = x.type == M_WAKEUP, ho = msg_has_order(x.type);
            L.seq[i] = (i64)i;
            L.message_id[i] = x.message_id;
            L.src[i] = x.src;
            L.dst[i] = x.dst;
            L.msg_type[i] = x.type;
            L.t_recv[i] = x.t_recv;
            L.t_send[i] = w ? 0 : x.t_send;
            L.has_send[i] = !w;
            L.latency[i] = w ? 0 : x.t_recv - x.t_send;
            L.has_order[i] = ho;
            L.order_id[i] = ho ? x.order_id : 0;
            L.has_causal[i] = !w;  // every non-wakeup message is sent from inside a dispatch
            L.causal[i] = w ? 0 : (i64)x.causal;
        }
        };
        const size_t nt = m >= (size_t)1 << 16 ? (size_t)(g_ledger_threads > 1 ? g_ledger_threads : 1) : 1;
        std::vector<std::thread> pool;
        for (size_t t = 1; t < nt; t++) pool.emplace_back(fill, m * t / nt, m * (t + 1) / nt);
        fill(0, m / nt);
        for (auto& th : pool) th.join();
    }
    R->n_ledger = (int64_t)m;
    R->l_seq = L.seq.data(); R->l_t_recv = L.t_recv.data(); R->l_t_send = L.t_send.data();
    R->l_latency = L.latency.data(); R->l_message_id = L.message_id.data(); R->l_order_id = L.order_id.data();
    R->l_causal = L.causal.data(); R->l_src = L.src.data(); R->l_dst = L.dst.data();
    R->l_msg_type = L.msg_type.data(); R->l_has_send = L.has_send.data(); R->l_has_order = L.has_order.data();
    R->l_has_causal = L.has_causal.data();
    if (g_want_utf8) {
        build_utf8(L.msg_type.data(), m, MSG_NAMES, M_N_TYPES, E->s_l_msg_off, E->s_l_msg);
        R->l_msg_off = E->s_l_msg_off.data(); R->l_msg_data = E->s_l_msg.data();
        R->l_msg_bytes = E->s_l_msg_off[m];
    }
}

static T3Result* t3_finish_impl(Engine* E) {
    std::unique_ptr<T3Result> R(new T3Result());
    finish_trace(E, R.get());
    finish_ledger(E, R.get());
    R->owner = E;
    return R.release();
}

T3Result* t3_finish(void* handle) {
    try {
        return t3_finish_impl(static_cast<Engine*>(handle));
    } catch (...) {
        return nullptr;
    }
}

int t3_lat_ambiguous() { return g_lat_ambiguous.load() ? 1 : 0; }

const char* t3_msg_name(int t) { return (t >= 0 && t < M_N_TYPES) ? MSG_NAMES[t] : "?"; }

void t3_free(T3Result* R) {
    delete static_cast<Engine*>(R->owner);
    delete R;
}

}  // extern "C"
