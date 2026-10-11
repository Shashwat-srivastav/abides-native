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
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <deque>
#include <queue>
#include <stdexcept>
#include <sys/mman.h>
#include <string>
#include <unordered_map>
#include <vector>

#include "../rng/np_random.hpp"

namespace t3 {

using i64 = int64_t;

// ---------------------------------------------------------------- memory
// Reserve (virtual only until touched) and ask for transparent huge pages: output buffers are
// large and written once, so first-touch page faults dominate otherwise. madvise is advisory.
template <class T>
static void reserve_huge(std::vector<T>& v, size_t n) {
    v.reserve(n);
    const uintptr_t kHuge = 2u << 20;
    uintptr_t b = (uintptr_t)v.data(), e = b + n * sizeof(T);
    uintptr_t ab = (b + kHuge - 1) & ~(kHuge - 1);
    if (e > ab + kHuge) madvise((void*)ab, (e - ab) & ~(kHuge - 1), MADV_HUGEPAGE);
}

// Back the reserved capacity with physical pages now (setup phase) instead of taking a page-fault
// trap per 4 KiB during the event loop. MADV_POPULATE_WRITE (Linux 5.14+) does it in one call;
// where unsupported (older kernels, gVisor) fall back to touching one byte per page.
template <class T>
static void prefault(std::vector<T>& v) {
#ifndef MADV_POPULATE_WRITE
#define MADV_POPULATE_WRITE 23
#endif
    const uintptr_t kPage = 4096;
    uintptr_t b = (uintptr_t)v.data(), e = b + v.capacity() * sizeof(T);
    uintptr_t ab = (b + kPage - 1) & ~(kPage - 1), ae = e & ~(kPage - 1);
    if (ae <= ab) return;
    if (madvise((void*)ab, ae - ab, MADV_POPULATE_WRITE) == 0) return;
    for (uintptr_t p = ab; p < ae; p += kPage) *(volatile char*)p = 0;
}

// ---------------------------------------------------------------- python numeric semantics
static inline i64 py_round(double x) { return (i64)std::nearbyint(x); }  // FE_TONEAREST = half-even

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

struct Msg {
    int8_t type;
    i64 id;
    OrderSnap order;  // order-carrying messages
    // QuerySpreadResponseMsg payload (depth-1 L2 data)
    i64 bid_p, bid_q, ask_p, ask_q;
    bool has_bid, has_ask, mkt_closed;
    // ledger send info (per heap entry; a broadcast message has one entry per recipient)
    i64 t_send, t_recv;
    i64 causal_parent;
    bool has_causal;
};

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
            if (c + 4 <= n) {  // full fan-out: branch-free tournament
                size_t b01 = h[c + 1].k < h[c].k ? c + 1 : c;
                size_t b23 = h[c + 3].k < h[c + 2].k ? c + 3 : c + 2;
                best = h[b23].k < h[b01].k ? b23 : b01;
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
struct OrderRow {  // an order-lifecycle log row (trace.py order_df before final sort)
    i64 t;
    int32_t owner;    // logging agent (== order agent_id for our flows)
    uint32_t lseq;    // per-owner log sequence (tie-break of the stable time sort)
    int8_t kind;      // 0 SUBMITTED, 1 ACCEPTED, 2 CANCELLED, 3 EXECUTED(partial), 4 EXECUTED(final)
    Side side;
    i64 price, size, order_id;
};
struct QuoteLog {
    i64 t;
    Side side;
    i64 price, size;
};
struct LedgerRow {
    i64 seq, t_recv, t_send, latency, message_id, order_id, causal_parent;
    int32_t src, dst;
    int8_t msg_type;
    bool has_send, has_order, has_causal;
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

struct Agent {
    AgentKind kind;
    int32_t id;
    nprand::NpRandomState rs;
    i64 interval_ns;
    // trading-agent state
    bool first_wake = true, has_mkt_hours = false, mkt_closed = false;
    bool awaiting_spread = false;
    i64 current_time = 0;
    bool kb_has_bid = false, kb_has_ask = false;  // known_bids/known_asks non-empty
    i64 kb_bid = 0, kb_ask = 0;
    OwnOrders orders;
    uint32_t lseq = 0;
    // params
    double order_size_mean = 0, order_size_std = 0;
    i64 price_offset_ticks = 0, reference_price = 0;
    i64 spread_ticks = 0, depth_levels = 0, size_per_level = 0;
    i64 threshold_ticks = 0;
    double sigma_n = 1000.0;
    i64 lookback = 0;
    std::vector<double> mid_history;
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

struct Engine {
    Config c;
    nprand::NpRandomState global_rs, oracle_rs, latency_rs;
    std::vector<Agent> agents;
    std::vector<i64> agent_current_times, agent_comp_delays;
    EventHeap heap;
    std::deque<Msg> pool;
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
    std::vector<OrderRow> order_rows;
    DenseIndex last_exec_row;  // order_id -> row of its latest ORDER_EXECUTED
    std::vector<i64> exec_order_ids;  // order ids that have at least one execution
    DenseIndex own_pos;  // OwnOrders position index shared by all agents
    std::vector<QuoteLog> quote_log;
    struct LedgerSoA {
        std::vector<i64> seq, t_recv, t_send, latency, message_id, order_id, causal;
        std::vector<int32_t> src, dst;
        std::vector<int8_t> msg_type, has_send, has_order, has_causal;
        void reserve(size_t n) {
            for (auto* v : {&seq, &t_recv, &t_send, &latency, &message_id, &order_id, &causal}) reserve_huge(*v, n);
            reserve_huge(src, n); reserve_huge(dst, n);
            for (auto* v : {&msg_type, &has_send, &has_order, &has_causal}) reserve_huge(*v, n);
        }
        void prefault() {
            for (auto* v : {&seq, &t_recv, &t_send, &latency, &message_id, &order_id, &causal}) t3::prefault(*v);
            t3::prefault(src); t3::prefault(dst);
            for (auto* v : {&msg_type, &has_send, &has_order, &has_causal}) t3::prefault(*v);
        }
    } ledger;
    // final trace columns (owned by the engine until t3_free)
    std::vector<i64> tr_t, tr_price, tr_size, tr_order_id;
    std::vector<int32_t> tr_agent;
    std::vector<int8_t> tr_msg, tr_side;
    std::vector<int32_t> s_tr_msg_off, s_tr_side_off, s_l_msg_off;
    std::vector<char> s_tr_msg, s_tr_side, s_l_msg;
    int32_t exchange_id = 0;
    size_t est_wakeups = 0;

    // --------------------------------------------------------- messaging
    uint32_t new_msg(int8_t type) {
        uint32_t s;
        if (!free_slots.empty()) { s = free_slots.back(); free_slots.pop_back(); }
        else { s = (uint32_t)pool.size(); pool.emplace_back(); }
        Msg& m = pool[s];
        m.type = type;
        if (next_msg_id > 0xFFFFFFFFll) throw std::runtime_error("message id exceeds heap key packing");
        m.id = next_msg_id++;
        return s;
    }
    i64 draw_latency(int32_t sender, int32_t recipient) {
        if (sender == recipient) return 0;
        double value;
        switch (c.lat_model) {
            case 1: value = latency_rs.lognormal(c.lat_mu, c.lat_sigma); break;
            case 2: value = latency_rs.uniform(c.lat_min_ns, c.lat_max_ns); break;
            case 3: {
                double base = c.lat_min_ns > 0 ? c.lat_min_ns : 1.0;
                value = base * (1.0 + latency_rs.pareto(c.lat_alpha));
                break;
            }
            default: value = c.lat_mean_ns;
        }
        double lo = c.lat_min_ns, hi = c.lat_max_ns;
        return py_round(value > hi ? hi : (value < lo ? lo : value));
    }
    // Kernel.send_message; `slot` may be shared by several recipients (broadcast) only if the
    // caller copies it per recipient (we copy, since ledger send info is per delivery).
    void send(int32_t sender, int32_t recipient, uint32_t slot, i64 delay = 0) {
        i64 sent_time = current_time + agent_comp_delays[sender] + delay;
        i64 latency = draw_latency(sender, recipient);
        i64 deliver_at = sent_time + latency;
        Msg& m = pool[slot];
        m.t_send = sent_time;
        m.t_recv = deliver_at;
        m.causal_parent = current_causal;
        m.has_causal = has_causal;
        heap.push(HeapEntry::make(deliver_at, heap_key(sender, recipient, m.id), slot));
    }
    void set_wakeup(int32_t agent, i64 t) {
        uint32_t s = new_msg(M_WAKEUP);
        heap.push(HeapEntry::make(t, heap_key(agent, agent, pool[s].id), s));
    }

    // --------------------------------------------------------- logging (trace inputs)
    void log_order(Agent& a, int8_t kind, const OrderSnap& o) {
        i64 price = (kind >= 3) ? o.fill_price : o.limit_price;
        order_rows.push_back({a.current_time, a.id, a.lseq++, kind, o.side, price, o.quantity, o.order_id});
        if (kind == 3) {
            uint32_t row = (uint32_t)order_rows.size() - 1;
            if (last_exec_row.get(o.order_id) == NONE) exec_order_ids.push_back(o.order_id);
            last_exec_row.set(o.order_id, row);
        }
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
    void send_order_msg(int8_t type, int32_t recipient, const OrderSnap& o) {
        uint32_t s = new_msg(type);
        pool[s].order = o;
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
        Agent& ex = agents[exchange_id];
        if (!bids.levels.empty()) quote_log.push_back({ex.current_time, BID, bids.best().price, bids.best().total_qty});
        if (!asks.levels.empty()) quote_log.push_back({ex.current_time, ASK, asks.best().price, asks.best().total_qty});
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
        pool[s].order = o;
        send(a.id, exchange_id, s);
        log_order(a, 0, o);
    }
    void cancel_all_orders(Agent& a) {
        // iterate a snapshot of alive entries in insertion order (dict is not mutated here)
        for (size_t i = 0; i < a.orders.v.size(); i++) {
            auto& e = a.orders.v[i];
            if (!e.alive) continue;
            uint32_t s = new_msg(M_CANCEL_ORDER);
            pool[s].order = OrderSnap{e.order_id, e.limit_price, e.quantity, 0, a.id, e.side, false};
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
                log_order(a, 3, m.order);
                auto* e = a.orders.find(m.order.order_id);
                if (e) {
                    if (m.order.quantity >= e->quantity) a.orders.erase(m.order.order_id);
                    else e->quantity -= m.order.quantity;
                }
                break;
            }
            case M_ORDER_ACCEPTED: log_order(a, 1, m.order); break;
            case M_ORDER_CANCELLED: {
                log_order(a, 2, m.order);
                if (a.orders.find(m.order.order_id)) a.orders.erase(m.order.order_id);
                break;
            }
            case M_QUERY_SPREAD_RESP: {
                if (m.mkt_closed) a.mkt_closed = true;
                a.kb_has_bid = m.has_bid; a.kb_bid = m.bid_p;
                a.kb_has_ask = m.has_ask; a.kb_ask = m.ask_p;
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
            i64 id = pool[base].id;
            for (size_t i = 0; i < close_price_subs.size(); i++) {
                uint32_t s = base;
                if (i > 0) {
                    if (!free_slots.empty()) { s = free_slots.back(); free_slots.pop_back(); }
                    else { s = (uint32_t)pool.size(); pool.emplace_back(); }
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
                r.has_bid = !bids.levels.empty();
                r.has_ask = !asks.levels.empty();
                r.bid_p = r.has_bid ? bids.best().price : 0;
                r.bid_q = r.has_bid ? bids.best().total_qty : 0;
                r.ask_p = r.has_ask ? asks.best().price : 0;
                r.ask_q = r.has_ask ? asks.best().total_qty : 0;
                r.mkt_closed = t > c.mkt_close;
                exch_send(sender, s);
                break;
            }
            case M_LIMIT_ORDER: handle_limit_order(m.order); break;
            case M_CANCEL_ORDER: {
                OrderSnap removed;
                if (cancel_in_book(m.order.side, m.order.limit_price, m.order.order_id, removed))
                    send_order_msg(M_ORDER_CANCELLED, m.order.agent_id, removed);
                break;
            }
            default: break;
        }
    }

    // --------------------------------------------------------- kernel
    void ledger_deliver(const HeapEntry& e, const Msg& m) {
        auto& L = ledger;
        L.seq.push_back(deliver_seq++);
        L.message_id.push_back(e.msg_id());
        L.src.push_back(e.sender());
        L.dst.push_back(e.recipient());
        L.msg_type.push_back(m.type);
        if (m.type == M_WAKEUP) {
            L.t_recv.push_back(current_time); L.t_send.push_back(0); L.has_send.push_back(0);
            L.latency.push_back(0); L.has_order.push_back(0); L.order_id.push_back(0);
            L.has_causal.push_back(0); L.causal.push_back(0);
        } else {
            bool ho = msg_has_order(m.type);
            L.t_recv.push_back(m.t_recv); L.t_send.push_back(m.t_send); L.has_send.push_back(1);
            L.latency.push_back(m.t_recv - m.t_send); L.has_order.push_back(ho);
            L.order_id.push_back(ho ? m.order.order_id : 0);
            L.has_causal.push_back(m.has_causal); L.causal.push_back(m.causal_parent);
        }
    }
    void run() {
        // Kernel.initialize: kernel_initializing (exchange wakes at close), then kernel_starting.
        set_wakeup(exchange_id, c.mkt_close);
        for (auto& a : agents) set_wakeup(a.id, c.start_time);
        current_time = c.start_time;
        while (!heap.empty() && current_time && current_time <= c.stop_time) {
            HeapEntry e = heap.top();
            current_time = e.time();
            int32_t r = e.recipient();
            Msg& m = pool[e.slot];
            if (agent_current_times[r] > current_time) {
                // Requeue at the agent's busy-until time (strictly later than this top).
                e.set_time(agent_current_times[r]);
                heap.replace_top(e);
                continue;
            }
            heap.pop();
            agent_current_times[r] = current_time;
            if (m.type == M_WAKEUP) {
                current_causal = m.id; has_causal = true;
                ledger_deliver(e, m);
                Agent& a = agents[r];
                if (a.kind == A_EXCHANGE) exchange_wakeup(a, current_time);
                else trader_wakeup(a, current_time);
                agent_current_times[r] += agent_comp_delays[r];
            } else {
                agent_current_times[r] += agent_comp_delays[r];
                current_causal = m.id; has_causal = true;
                ledger_deliver(e, m);
                Agent& a = agents[r];  // pool is a deque: `m` stays valid while handlers add messages
                if (a.kind == A_EXCHANGE) exchange_receive(a, current_time, e.sender(), m);
                else trader_receive(a, current_time, m);
            }
            free_slots.push_back(e.slot);
        }
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
    reserve_huge(E->order_rows, L * 3 / 4);
    reserve_huge(E->quote_log, L / 2);
    E->ledger.reserve(L);
    prefault(E->order_rows);
    prefault(E->quote_log);
    E->ledger.prefault();

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
    } catch (...) {
        return -1;
    }
}

void t3_destroy(void* handle) { delete static_cast<Engine*>(handle); }

static T3Result* t3_finish_impl(Engine* E) {
    auto _tp1 = std::chrono::steady_clock::now();
    // -------------------------------------------------- trace assembly (trace.py semantics)
    auto& rows = E->order_rows;
    for (i64 id : E->exec_order_ids) rows[E->last_exec_row.get(id)].kind = 4;
    // order_df: stable sort by t over (owner, lseq) concatenation, then stable by (t, order_id)
    std::vector<uint32_t> ord(rows.size());
    for (uint32_t i = 0; i < ord.size(); i++) ord[i] = i;
    // Rows are appended in nondecreasing t (agents log at the kernel's dispatch time), so the
    // full (t, order_id, owner, lseq) order only needs sorting within equal-t runs.
    auto key_less = [&](uint32_t x, uint32_t y) {
        const OrderRow &a = rows[x], &b = rows[y];
        if (a.order_id != b.order_id) return a.order_id < b.order_id;
        if (a.owner != b.owner) return a.owner < b.owner;
        return a.lseq < b.lseq;
    };
    bool monotone = true;
    for (size_t i = 1; i < rows.size() && monotone; i++) monotone = rows[i].t >= rows[i - 1].t;
    if (monotone) {
        for (size_t i = 0; i < ord.size();) {
            size_t j = i + 1;
            while (j < ord.size() && rows[j].t == rows[i].t) j++;
            if (j - i > 1) std::sort(ord.begin() + i, ord.begin() + j, key_less);
            i = j;
        }
    } else {  // safety net: never observed, but keep the exact semantics regardless
        std::sort(ord.begin(), ord.end(), [&](uint32_t x, uint32_t y) {
            if (rows[x].t != rows[y].t) return rows[x].t < rows[y].t;
            return key_less(x, y);
        });
    }
    // quotes: one row per (t, side), value of the last log, in first-appearance order
    struct Q { int64_t t; int8_t side; int64_t price, size; };
    std::vector<Q> quotes;
    {
        auto& ql = E->quote_log;
        for (size_t i = 1; i < ql.size(); i++)
            if (ql[i].t < ql[i - 1].t) throw std::runtime_error("non-monotone quote log");
        size_t i = 0;
        while (i < ql.size()) {
            size_t j = i;
            int first[2] = {-1, -1};
            int order_seen = 0;
            int64_t lp[2] = {0, 0}, ls[2] = {0, 0};
            int seq[2];
            while (j < ql.size() && ql[j].t == ql[i].t) {
                int s = ql[j].side;
                if (first[s] < 0) { first[s] = order_seen; seq[order_seen++] = s; }
                lp[s] = ql[j].price; ls[s] = ql[j].size;
                j++;
            }
            for (int k = 0; k < order_seen; k++) quotes.push_back({ql[i].t, (int8_t)seq[k], lp[seq[k]], ls[seq[k]]});
            i = j;
        }
    }
    T3Result* R = new T3Result();
    size_t n = ord.size() + quotes.size();
    R->n_trace = (int64_t)n;
    E->tr_t.resize(n); E->tr_price.resize(n); E->tr_size.resize(n); E->tr_order_id.resize(n);
    E->tr_agent.resize(n); E->tr_msg.resize(n); E->tr_side.resize(n);
    R->t_ns = E->tr_t.data(); R->price = E->tr_price.data(); R->size = E->tr_size.data();
    R->order_id = E->tr_order_id.data(); R->agent_id = E->tr_agent.data(); R->msg_type = E->tr_msg.data();
    R->side = E->tr_side.data();
    size_t oi = 0, qi = 0, w = 0;
    while (oi < ord.size() || qi < quotes.size()) {
        bool take_q = qi < quotes.size() && (oi >= ord.size() || quotes[qi].t <= rows[ord[oi]].t);
        if (take_q) {
            auto& q = quotes[qi++];
            R->t_ns[w] = q.t; R->agent_id[w] = 0; R->msg_type[w] = 5; R->side[w] = q.side;
            R->price[w] = q.price; R->size[w] = q.size; R->order_id[w] = -1;
        } else {
            auto& r = rows[ord[oi++]];
            R->t_ns[w] = r.t; R->agent_id[w] = r.owner; R->msg_type[w] = r.kind; R->side[w] = r.side;
            R->price[w] = r.price; R->size[w] = r.size; R->order_id[w] = r.order_id;
        }
        w++;
    }
    // ledger (already in delivery-seq order)
    auto& L = E->ledger;
    size_t m = L.seq.size();
    R->n_ledger = (int64_t)m;
    R->l_seq = L.seq.data(); R->l_t_recv = L.t_recv.data(); R->l_t_send = L.t_send.data();
    R->l_latency = L.latency.data(); R->l_message_id = L.message_id.data(); R->l_order_id = L.order_id.data();
    R->l_causal = L.causal.data(); R->l_src = L.src.data(); R->l_dst = L.dst.data();
    R->l_msg_type = L.msg_type.data(); R->l_has_send = L.has_send.data(); R->l_has_order = L.has_order.data();
    R->l_has_causal = L.has_causal.data();
    auto _tp2 = std::chrono::steady_clock::now();
    if (getenv("T3_PHASES")) fprintf(stderr, "W=%zu quotes=%zu run=%.4f assemble=%.4f rows=%zu ledger=%zu\n", E->est_wakeups, E->quote_log.size(), 0.0, std::chrono::duration<double>(_tp2-_tp1).count(), rows.size(), m);
    build_utf8(E->tr_msg.data(), n, TRACE_NAMES, 6, E->s_tr_msg_off, E->s_tr_msg);
    build_utf8(E->tr_side.data(), n, SIDE_NAMES, 2, E->s_tr_side_off, E->s_tr_side);
    build_utf8(L.msg_type.data(), m, MSG_NAMES, M_N_TYPES, E->s_l_msg_off, E->s_l_msg);
    R->tr_msg_off = E->s_tr_msg_off.data(); R->tr_msg_data = E->s_tr_msg.data();
    R->tr_msg_bytes = E->s_tr_msg_off[n];
    R->tr_side_off = E->s_tr_side_off.data(); R->tr_side_data = E->s_tr_side.data();
    R->tr_side_bytes = E->s_tr_side_off[n];
    R->l_msg_off = E->s_l_msg_off.data(); R->l_msg_data = E->s_l_msg.data();
    R->l_msg_bytes = E->s_l_msg_off[m];
    R->owner = E;
    return R;
}

T3Result* t3_finish(void* handle) {
    try {
        return t3_finish_impl(static_cast<Engine*>(handle));
    } catch (...) {
        return nullptr;
    }
}

const char* t3_msg_name(int t) { return (t >= 0 && t < M_N_TYPES) ? MSG_NAMES[t] : "?"; }

void t3_free(T3Result* R) {
    delete static_cast<Engine*>(R->owner);
    delete R;
}

}  // extern "C"
