# Engine review: simulation-thread time per event

Read-only review of `native/engine/engine.cpp` (line numbers refer to the file as of 11 Oct),
`launcher.cpp`, `pq_fast.hpp`, `np_random.hpp`. Nothing was compiled or run (no compiler outside
Docker on this machine, Docker was off limits). **Every saving below is an estimate from code
reading plus the supplied profile**, not a measurement. The only measured inputs of my own are row
counts read from the reference Parquet files of four units.

## 0. Bottom line

- Low-risk, local changes (items A1-A6): about **15-20% of simulation-thread time** on the large
  units (nominal sum 20-27%; I discount it because the estimates overlap).
- With two medium-risk items (B1 noise-trader draws on the latency helper, B2 hot-state layout /
  prefetch, B3 AVX2 clones): nominal 28-36%, realistically **20-28%**.
- **30-50% needs a structural change: taking the passive receipts (OrderAccepted / OrderExecuted /
  OrderCancelled delivered to traders) out of the kernel queue** (item C1). They are 37.6% of all
  events on `gb-mega` and 47.7% on `deep-book`, they create no events and draw nothing, and today
  each costs a pool slot, a heap push, a heap pop and a full dispatch. C1 alone is worth an
  estimated 20-28%; with A1-A6 the total is an estimated 38-45%. It is a 12-20 hour change with a
  real risk, and its first version only covers units that write no ledger.

## 1. Where the ~450 instructions per event go

Event mix, counted from the reference ledgers (`units/<unit>/message_trace.parquet`):

| Unit | events | wakeup | QuerySpread | Response | LimitOrder | Cancel | Accepted | Executed | Cancelled |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gb-mega | 1,420,862 | 220,634 | 220,344 | 220,344 | 224,207 | 1,019 | 112,470 | 420,280 | 988 |
| gb-pop-horizon | 892,129 | 138,722 | 138,520 | 138,520 | 140,287 | 555 | 71,643 | 262,944 | 538 |
| deep-book | 269,644 | 4,305 | 4,281 | 4,281 | 64,259 | 63,950 | 64,010 | 584 | 63,930 |

Trace of gb-mega: 1,168,360 rows in 888,177 distinct timestamps (so about 76% of buckets hold a
single row); 410,415 quote rows (two per handled limit order).

Scenario facts that matter (gb-mega, and all 65 public units, from a survey of the scenario files):
`protocol_enforcement` is absent, so exchange computation delay and pipeline delay are 0 and STP is
off; every unit has `min_ns >= 100`; no unit has more than 4 distinct wake intervals. All 100 noise
traders of gb-mega wake at the same nanosecond every 50 ms, which is why the message heap holds
~105 entries: it is a burst of ~650 events every 50 ms of simulated time, then nothing.

Hand count of instructions on the commonest paths (my estimate, +-25%; the weighted mean comes to
~350 against the measured ~450, so scale each by ~1.3):

| Event | share | path | est. instr |
|---|---:|---|---:|
| W wakeup at trader | 15.5% | loop top 25, prologue 30, pool copy + free 20, ledger scratch 15, `set_wakeup` (slot, id, `replace_top` on the 145-entry wakeup heap ~90), QuerySpread `new_msg` 15 + `send` 45 + sift-up 30 | ~290 |
| Q query at exchange | 15.5% | common 90, `exchange_receive` 30, `new_msg` 15, `send` 50, `replace_top` 90 | ~275 |
| R response at trader | 15.5% | common 90, `trader_receive` 25, `act` (generator ~90), `place_limit_order` (`OwnOrders::put` 25, msg 25, send 50, `replace_top` 90, trace row + bucket 50) | ~440 |
| L limit order at exchange | 15.8% | common 90, book 80, 2.38 sends on average (each `new_msg` + `put_order` + `send` + heap ~110), quotes + bucket 50 | ~570 |
| P passive receipt at trader | 37.6% | common 90, receive + row 50, bucket close 35, `OwnOrders` find/erase 25, pop without replacement (full `sift_down`) 90 | ~300 |

Passive receipts are therefore about 32% of the instructions directly, and their send side inside
L is another ~12%: **~44% of the simulation thread is spent moving passive receipts through the
kernel queue.**

Avoidable work found on those paths:

1. `set_wakeup` (805-808): a pool slot is taken, written and later copied back for a message that
   carries nothing, and the wakeup heap is sifted to the bottom (the new key is later than almost
   every pending one). `set_wakeup` alone is 3.7% of process cycles = 8% of the simulation thread.
2. Ledger record (1318-1327): ten stores into `ledger_scratch` on every event when the ledger is
   skipped.
3. `free_slots` (498, 659, 1315): `std::vector` push/pop with capacity checks on every message.
4. `OwnOrders` (393-421): `put` on every order (1056), `find`/`erase` on every fill (1167-1171,
   1177), `compact()` with a malloc every ~48 erases. **Only the market maker ever reads it**
   (`cancel_all_orders`, 1062). 97% of gb-mega's orders belong to other agent kinds.
5. Trace bucket (541-584, 811-815): `close_bucket` is called (out of line) for every timestamp,
   888K times on gb-mega, though 76% of buckets hold one row and need nothing but the `last_fill`
   update. 2.6% of process cycles = 5.6% of the simulation thread.
6. Double dispatch (1329-1338): an unpredictable branch on `a.kind` (exchange or trader alternate
   in random order inside a burst) followed by an unpredictable jump on `m.type`. The message type
   already implies the recipient kind.
7. Pop without replacement (298-302): `sift_down(0, last)` compares `last` at every level although
   it almost always ends at the bottom; the loop exit is one unpredictable branch per pop.
8. Blocked queues (487-496, 1276-1291): `std::push_heap`/`pop_heap` per blocked event although
   keys nearly always arrive in increasing order (see A6). 115K of deep-book's 270K events.
9. `HeapEntry` is 32 bytes of which 12 are padding (261-276); the heap is in L1 at these sizes, so
   shrinking it to 16 bytes buys little (rejected, section 5).
10. Per-agent generator: 2.5 KB of state per agent, ~110 cycles per `act` (3% of process cycles).
11. Branch misses: 4.9M over 1.42M events. My attribution for the simulation thread (estimate):
    dispatch ~0.7-1.0 per event, sift exit ~0.5, `act` buy/sell and rejection loops ~1 per R,
    `execute`/`enter_order` (binary search over levels, 866) ~1-2 per L.

## 2. Ranked changes

Saving = share of simulation-thread cycles on gb-mega, estimated as (cycles of the removed code in
the supplied profile) or (instructions removed x count / 640M). "sim" = simulation thread
(46% of process cycles in the supplied profile, 366M cycles, 258 per event).

### A. Low risk (do these first, one build)

**A1. Wakeups in monotone FIFOs instead of the wakeup heap; no pool slot for a wakeup.**
Where: `set_wakeup` 805-808, `wheap` 477, loop top 1271-1281, wakeup dispatch 1314-1333, `block`
491. Saving 7-9% (`set_wakeup` 3.7% of process = 8% of sim, plus the wakeup share of `sift_down`
and of the pool copy, minus ~25 instructions that remain).
Design: one ring per distinct `interval_ns` (first 4 distinct values; other agents use the heap).
`set_wakeup` appends to the agent's ring **iff the new key is greater than the ring's last key**,
otherwise it pushes to `wheap`, which stays as the catch-all (exchange close wakeup, the
`mkt_open` wakeups, anything out of order). The loop keeps the earliest wakeup (`wk`, `wk_src`)
cached and recomputes it only when a wakeup is pushed or popped.
Exactness: every container is sorted (rings by the push-time check, the heap by construction), the
next wakeup is the minimum of their heads, keys are unique, so the pop sequence is that of one
heap. Nothing depends on the argument that keys do arrive in order; that only decides how often
the fast path is taken. (They do: agents with equal interval are dispatched in increasing
(time, agent), so their next keys (time + interval, agent) are pushed in increasing order.)
Sketch in section 3.1.

**A2. `OwnOrders` only for market makers.** Where: 1056, 1167-1171, 1177. Saving ~3%
(put ~30 instr x 217K, find/erase ~35 x 420K, compaction; ~26M of 640M instructions).
`if (a.kind == A_MM) a.orders.put(o);` and the same guard around the two lookups in
`trader_receive`. Exactness: for other kinds the container is write-only state: its only reader is
`cancel_all_orders`, called only from the `A_MM` case of `act`; `own_pos` is keyed by order id, so
market-maker entries are untouched. 15 minutes.

**A3. Trace: inline fast path for one-row buckets.** Where: `trace_at` 577-584, `log_order`
811-815, quote logging 977-988, `close_bucket` 541-576. Saving 3-4% (two thirds of
`close_bucket`'s 5.6%, plus the call).
A bucket needs `close_bucket` only if it got a second order row or a quote (`bk_slow`). For a lone
order row its final index is its append index, so `last_fill` can be set when it is logged.
Exactness: for a slow bucket `close_bucket` runs unchanged and re-sets `last_fill` for every fill
row of the bucket after moving them, overwriting the early value with the final index; for a fast
bucket nothing moves. `repair_trace` rebuilds the index wholesale as before. Sketch in 3.2.
Optional second step (+1%): write a quote row in place when it is the first row of its bucket and
update it in place afterwards, so quote-only buckets (205K on gb-mega) skip `close_bucket` too.

**A4. Dispatch diet.** Where: 1314-1339, 658-671, 788-804. Saving 4-6% on no-ledger units, 2-4%
elsewhere.
- `if (!skip_ledger) { ...record... }` instead of writing a scratch record (~12 instr/event).
- Intrusive free list: a free slot stores the next free index in its own `t_send`; `free_head`
  replaces the vector (~8 instr/event).
- One `switch (m.type)` at top level, with the exchange cases and the trader cases as its arms
  (the type determines the recipient kind in every flow of this engine; keep the `a.kind` test as
  an assert-style fallback). Removes one of the two unpredictable branches per event.
- `__attribute__((always_inline))` on `send` and `new_msg` (they show as separate symbols in the
  profile, so they are calls today).
Exactness: no change of any computed value; the free list changes which slot index a message
occupies, and slot indices are not part of any key or output.

**A5. Bottom-up pop.** Where: `EventHeap::pop` 298-302. Saving 1-2%. Move the hole from the root
to a leaf by the 4-way tournament without comparing against `last`, then sift `last` up from
there. Any valid heap gives the same pop order because keys are unique.

**A6. Blocked queue as an append-mostly sorted vector.** Where: 487-496, 1284-1291. Saving ~0.6%
on gb-mega, **6-7% on deep-book-like units** (115K of 270K events take this path). Entries blocked
at send time arrive in increasing key order (same sender, increasing message id); so
`if (q.empty() || key > q.back().key) push_back; else insert in order`, pop from a head index.
Exact: it is still a priority queue on the same keys.

### B. Medium risk

**B1. Noise-trader draws computed by the latency helper in its idle time.** Where: `act`
1076-1080, `Feed::body` 725-738. Saving 5-6% (agent generator is 3% of process cycles = 6.5% of
sim; the noise traders are 220K of the ~235K draws). No extra thread: the helper is busy only
~25-35% of the time (45 ns per latency draw x 0.85 draws per event against 120-170 ns per event)
and spins on `_mm_pause` otherwise.
Protocol: for every `A_NOISE` agent the helper owns the generator (moved at `t3_create`) and fills
a 32-entry ring of `{i64 size; int32 offset; bool buy}` with exactly the three calls of 1077-1080
(`normal`, `randint(0,2)`, `randint(0, ticks+1)`), topping the rings up round-robin whenever the
latency ring is full. `act` takes the next triple; if the ring is empty it waits like `feed_wait`.
`trader_wakeup` prefetches the agent's next triple (the response arrives two events later).
Without a helper (`usable_cpus() < 2`) the engine draws inline as now.
Exactness: a noise trader's generator has one consumer and one call pattern, with no conditional
draw (verified: `observe_price` is only reached from `A_VALUE`), so triple i is a function of
(seed, i, parameters) alone; drawing ahead is unobservable. Value traders (one conditional
`normal` per act, 15K per run) and the oracle stream (megashock draws interleave depending on the
run) are not worth moving.
Risk: a second shared structure; the helper's slack shrinks as the simulation thread gets faster
(still about 2x after everything else here).

**B2. Hot agent state and prefetch.** Saving 2-5%, low confidence (no measurement possible here).
145 agents x (2-5 hot lines + generator lines) is 20-45 KB, about the size of L1 (32 KB on Zen 2,
48 KB on the Xeon), and an agent is touched again only ~100-200 events later. Two cheap probes:
`__builtin_prefetch(&agents[recipient])` in `send`, or at loop top prefetch the recipients of the
four children of the heap root. If that pays, move the per-dispatch fields into a 64-byte
`AgentHot` array. No value changes.

**B3. `target_clones("arch=x86-64-v3","default")` on `Engine::run` and the encoder kernels.**
The binary is built for baseline x86-64 (`sub/Dockerfile` line 36: no `-march`). Saving 1-4% of
sim (estimate), possibly more in the delta encoder. `-ffp-contract=off` still applies, so no FMA
is formed and no floating-point result changes; integer code only gets BMI/AVX encodings. Needs
the full table check on both paths.

**B4. Passive receipt carried inside the heap entry (no pool slot), no-ledger units only.**
`HeapEntry` has 12 bytes of padding plus the 4-byte slot: enough for order id (32 bits), quantity
(32 bits) and price with type/side in its top bits. Saving 4-5%. Superseded by C1; listed as the
fallback if C1 is not attempted.

### C. Structural

**C1. Lazy passive receipts ("inbox per trader").** Saving 20-28% on top of A (estimate: ~44% of
sim instructions are attributable to passive receipts today, ~11% remain). Effort 12-20 h plus the
full validation suite. First version for no-ledger units only (the six `gb_*` units, which carry
the largest event counts).

Why it is possible. A passive receipt at trader r does exactly three things: writes one trace row
at its dispatch time, updates r's own-order book (read only by a market maker's next `act`), and
makes r busy for its computation delay. It sends nothing, draws nothing, allocates no id (its own
id is allocated at send, as now). So its position in the global order matters only (i) relative to
r's other events and (ii) for where its row lands in the trace. Its dispatch time is
`max(deliver_at, busy[r])` and r's events are served in the order (dispatch time, sender, id).

Design (details and code in 3.3):
- `send_order_msg` to a trader draws the latency and takes the message id as now, then appends a
  32-byte record to `inb[r]` instead of touching the pool and the heap.
- Before any kernel event for trader r is dispatched at (T, key K), `flush_trader(r, T, K)`
  serves r's receipts that precede (T, K) in r's order. If r is then busy past T the event is
  blocked exactly as today.
- Rows of served receipts go to a small sorted scratch (`pscr`). At a *cut* (a kernel event whose
  time T is later than the open bucket and than every scratch row, taken every ~48 scratch rows)
  every trader's receipts due before T are served, the open bucket is closed, and the scratch is
  merged into the tail of the trace. The trace stays in final order behind the cut, so the
  launcher, `trace_closed` and the encoders are untouched.
- When the next kernel event is past `stop_time` (or the queue is empty), receipts due up to
  `stop_time` are served, a last cut is made, the rest are re-queued through the classic path and
  the classic loop finishes. The delicate "first event past the stop time is still dispatched"
  rule is thereby decided by the existing code.

Exactness argument.
1. *Safety of serving a receipt p of trader r at kernel time T when due(p) <= T.* Any message not
   yet sent is sent by a kernel event at time >= T with total delay >= 0, so its delivery time is
   >= T >= due(p) and its id is larger: it cannot precede p. Requires `pipeline_delay >= 0`,
   `lat_min_ns >= 0` and `lat_max_ns >= 0`; otherwise the engine runs the classic loop.
2. *Order within a trader.* `flush_trader` picks, among r's pending receipts, the one the kernel
   would dispatch next: if some have `deliver_at <= busy[r]` they all become due at `busy[r]` and
   the smallest id goes first (same sender); otherwise the smallest (deliver_at, id). It stops at
   the first one that does not precede (T, K). This is the reference rule restricted to r, and
   busy[r] changes only when r dispatches.
3. *Other agents cannot tell.* A receipt changes no state outside r, and every later event of r is
   preceded by a flush.
4. *`agent_current_times[r]` may be stale (too early) between flushes.* It is read by the blocked
   check in `send` (a later true value can only block more, and the event is re-checked when
   popped) and by the blocked-queue scan (an event picked too early is flushed, found not due and
   left blocked). Both are safe with a lower bound.
5. *Trace.* After a cut at T every emitted row has t < T and every later row has t >= T (pending
   receipts have due >= T and due never decreases; new ones are delivered at >= T). Inside a
   segment the final order is a function of the row set: sort by t, quotes first, then
   (order id, owner); (t, order id, owner) is unique because a trader dispatches at most once per
   nanosecond (computation delay 50). So merging is exact. All fill rows are receipt rows, so
   `last_fill` is set as they are placed by the merge, in time order per order.
6. *Stop rule*: delegated to the classic loop as described.
Guard for the scratch image (no Python fallback): if an invariant fails in lazy mode (a row earlier
than the open bucket, a delivery before the current time), rebuild the engine from the same config
and rerun with the lazy lane off; the engine is deterministic, so this costs time, not correctness.

Second version (not sketched): ledger units. Receipt records are then merged into `lrec` at each
cut by (dispatch time, src, dst, message id). That key equals dispatch order only if no event can
be created and dispatched in the same nanosecond, i.e. it additionally needs minimum total delay
>= 1 ns (true for every public unit) and a per-segment array of dispatch times for the kernel
events. deep-book-like units would gain most (47.7% receipts, and the blocked-queue detour of
115K events disappears because the inbox handles busy recipients directly).

## 3. Code sketches

### 3.1 A1: wakeup FIFOs

```cpp
// Engine members
struct WakeQ { std::vector<u128> q; uint32_t head = 0, tail = 0, mask = 0; };
WakeQ wq[4]; int n_wq = 0;          // one per distinct interval (t3_create); Agent::wq = index or -1
u128 wk = ~(u128)0; int wk_src = -1; // earliest pending wakeup: 0..3 ring, 4 heap
void wk_refresh() {
    wk = ~(u128)0; wk_src = -1;
    for (int i = 0; i < n_wq; i++) { WakeQ& W = wq[i];
        if (W.head != W.tail && W.q[W.head & W.mask] < wk) { wk = W.q[W.head & W.mask]; wk_src = i; } }
    if (!wheap.empty() && wheap.top().k < wk) { wk = wheap.top().k; wk_src = 4; }
}
void set_wakeup(int32_t agent, i64 t) {
    if (__builtin_expect(next_msg_id > 0xFFFFFFFFll, 0)) throw std::runtime_error("message id exceeds heap key packing");
    const u128 k = HeapEntry::make(t, heap_key(agent, agent, next_msg_id++), 0).k;
    const int f = agents[agent].wq;
    if (f >= 0) { WakeQ& W = wq[f];
        const bool room = W.tail - W.head <= W.mask;               // capacity = mask + 1 >= n_agents + 1
        if (room && (W.head == W.tail || k > W.q[(W.tail - 1) & W.mask])) {
            W.q[W.tail++ & W.mask] = k;
            if (k < wk) { wk = k; wk_src = f; }
            return; } }
    wheap.push(HeapEntry{k, NONE});                                  // out of order or no ring: exact fallback
    if (k < wk) { wk = k; wk_src = 4; }
}
// run(): candidates
u128 best = kNoEvent; int src = -1;                // 0 message heap, 1 wakeup, 2 blocked
if (!mheap.empty()) { best = mheap.top().k; src = 0; }
if (wk < best) { best = wk; src = 1; }
/* blocked scan as now, sets src = 2 */
if (src == 1) {
    const u128 k = wk;
    if (wk_src < 4) wq[wk_src].head++; else wheap.pop();
    wk_refresh();
    current_time = time_of(k); r = recipient_of(k);
    if (agent_current_times[r] > current_time) { block(r, (uint64_t)k, NONE); continue; }
    hole = nullptr;                                   // only mheap uses the hole from now on
    /* dispatch as a wakeup: id = (uint32_t)k, no pool read, no slot to free */
}
// a blocked entry with slot == NONE is a wakeup; the initial wakeups (1264-1265) go through set_wakeup too
```
`t3_create`: assign `wq` by scanning agents for distinct `interval_ns` (first four), ring capacity
= next power of two >= n_agents + 2. The ledger fields that a wakeup leaves unset (`t_send`,
`order_id`, `causal`) are masked for wakeups by both writers (`finish_ledger` 1602-1608 and the
launcher callbacks), so they need no value.

### 3.2 A2 + A3 + ledger part of A4

```cpp
bool bk_slow = false;                           // the open bucket needs close_bucket()
void trace_at(i64 t) {
    if (t == bk_t) return;
    if (bk_slow) { close_bucket(); bk_slow = false; }
    if (t < bk_t) trace_bad = true;
    bk_t = t; bk_start = trace.size();
    trace_closed.store(bk_start, std::memory_order_release);
}
void log_order(Agent& a, int8_t kind, Side side, i64 price, i64 qty, i64 order_id) {
    trace_at(a.current_time);
    row_fits(qty, order_id);
    const size_t i = trace.size();
    *trace.next() = OrderRow{a.current_time, price, (int32_t)qty, (int32_t)order_id, a.id, kind, side};
    if (i != bk_start) bk_slow = true;                               // second order row: sort at close
    else if (kind == 3) last_fill.set(order_id, (uint32_t)i);        // lone row: index is final unless the bucket turns slow
}
// handle_limit_order, after trace_at(...) at 979: bk_slow = true;   (quote rows are inserted at close)
// finish_trace_rows(): keep the unconditional close_bucket() (harmless for a fast bucket)
// place_limit_order 1056:      if (a.kind == A_MM) a.orders.put(o);
// trader_receive 1167, 1177:   if (a.kind == A_MM) { ...find / erase... }
// run() 1318-1327:             if (!skip_ledger) { LedgerRec* L = lrec.next(); ...; lrec_done.store(...); }
```
`close_bucket` itself is unchanged: when it runs it re-sets `last_fill` for every fill row of the
bucket at its final index (573-574), which overwrites the early value written by `log_order`.

### 3.3 C1: lazy passive receipts (no-ledger units)

```cpp
struct PRec { i64 d, price; uint32_t id; int32_t order_id, qty; int8_t kind; Side side; };  // kind 1 ACC, 2 CAN, 3 EXE
bool lazy;                                  // skip_ledger && pipeline_delay >= 0 && lat_min_ns >= 0 && lat_max_ns >= 0
std::vector<std::vector<PRec>> inb;         // per trader, in send order (= increasing id)
std::vector<int32_t> dirty;                 // traders with a non-empty inbox (+ position index for O(1) removal)
std::vector<OrderRow> pscr;                 // served rows since the last cut, sorted by (t, order_id, owner)
i64 p_max_t = INT64_MIN; size_t seg_start = 0;

// send_order_msg(type, recipient, o), lazy branch (recipient is a trader):
//   row_fits(o.quantity, o.order_id);  id = next_msg_id++ (same overflow guard);
//   d = current_time + agent_comp_delays[exchange_id] + c.pipeline_delay + next_latency();
//   inb[recipient].push_back({d, price, id, order_id, qty, kind, side}); mark dirty

void flush_trader(int32_t r, i64 T, uint64_t K) {       // serve r's receipts that precede (T, K)
    auto& q = inb[r];
    while (!q.empty()) {
        const i64 b = agent_current_times[r];
        size_t j = q.size();
        for (size_t i = 0; i < q.size(); i++) if (q[i].d <= b) { j = i; break; }     // blocked ones: smallest id first
        if (j == q.size()) { j = 0; for (size_t i = 1; i < q.size(); i++) if (q[i].d < q[j].d) j = i; }
        const PRec p = q[j];
        const i64 due = p.d > b ? p.d : b;
        if (due > T || (due == T && heap_key(exchange_id, r, p.id) > K)) break;
        Agent& a = agents[r];
        a.current_time = due;
        agent_current_times[r] = due + agent_comp_delays[r];
        insert_sorted(pscr, OrderRow{due, p.price, p.qty, p.order_id, r, p.kind, p.side});   // from the back
        if (due > p_max_t) p_max_t = due;
        if (a.kind == A_MM) { /* lines 1167-1171 for kind 3, 1177 for kind 2 */ }
        q.erase(q.begin() + j);
    }
    if (q.empty()) undirty(r);
}
void cut(i64 T) {                                        // precondition: T > bk_t && T > p_max_t
    for (size_t i = dirty.size(); i-- > 0;) flush_trader(dirty[i], T - 1, ~0ull);
    close_bucket(); bk_slow = false;
    // backward in-place merge of pscr into trace[seg_start, size): by t; at equal t a quote row first,
    // then (order_id, owner); while placing a kind-3 row at index i: last_fill.set(order_id, i)
    merge_tail(pscr);  pscr.clear();
    seg_start = bk_start = trace.size();  trace_closed.store(seg_start, std::memory_order_release);
}
// run(), after the candidate (T, K, r) is chosen and before it is popped:
if (lazy) {
    if (best == kNoEvent || T > c.stop_time) {           // hand the tail to the classic loop
        for (...dirty...) flush_trader(r2, c.stop_time, ~0ull);          // repeat until nothing is served
        cut_final();                                      // close bucket, merge everything served
        requeue every remaining PRec exactly as the classic send() would (pool slot; block() if
            agent_current_times[r2] > d && d <= stop_time, else mheap.push); lazy = false; continue; }
    if (T > bk_t && T > p_max_t && pscr.size() >= 48) cut(T);
    if (r != exchange_id && !inb[r].empty()) {
        flush_trader(r, T, K);
        if (agent_current_times[r] > T) { /* heap event: pop and block(r, K, slot); blocked event: leave it */ continue; }
    }
}
```
Notes for the implementer:
- `cut(T)` passes `T - 1`, so only receipts due strictly before T are served there; the per-trader
  flush right after it may serve receipts due exactly at T (they belong to the next segment).
- The loop-top break test (`current_time > c.stop_time`) is unaffected while lazy: served receipts
  never set `current_time`, and all of them are due <= stop_time.
- In lazy mode `close_bucket` sees no fill rows from kernel events (all fills are receipts), so the
  A3 early `last_fill` write is simply never taken for kind 3.
- A test hook that forces `lazy = false` gives the reference tables for an A/B over all 65 units
  and the 1,318 fuzz cases; the 29 negative-latency cases must take the classic loop by the guard.
- Expected cost per receipt after the change (estimate): latency + append ~25 instructions, flush
  ~30, row + insertion ~30, merge share ~15; against ~410 today (send side + dispatch).

## 4. Other threads (question 3)

| Work | Movable? | Why |
|---|---|---|
| Latency stream | done | one consumer, position-indexed |
| Noise-trader draws | yes (B1), on the existing helper | unconditional fixed pattern per `act` |
| Value-trader noise | yes but pointless | 15K draws per run |
| Oracle stream | no | megashock draws interleave on the same generator at run-dependent positions (1021-1038); 1% of sim anyway |
| Trace ordering | already online; with C1 it could move to the encoders (segments are independent) | only worth it if the online merge of C1 shows up in a profile |
| Order book | no | QuerySpread and LimitOrder need it synchronously |
| Encoding during the run | yes, on the latency helper's idle time, in memory, no syscalls | see section 6; a process-time gain, not a simulation-thread gain |

Helper capacity: one latency draw costs ~175 cycles in the supplied profile (27% of 0.79e9 over
~1.2M draws). The helper is a hard floor of about 0.85 x 45 ns = 38 ns per event; the simulation
thread reaches that only after a 70% cut, so one helper is enough for everything proposed here.
If it ever binds: MT19937 plus the polar rejection loop is ~15 cycles per draw, the rest is
log/sqrt/exp, so two helpers can each run the generator and compute the transcendental part only
for alternate 64-draw chunks (each value is still a pure function of the stream position).

## 5. Considered and rejected

- **16-byte heap entries** (time relative to start in 47 bits, hub-topology pair in 17, id 32, slot
  32). The heaps are 3-5 KB and live in L1; the gain is a few moves per sift (~1%), and it adds a
  horizon limit that needs a second code path.
- **Radix heap / calendar queue for messages.** Monotone in time under non-negative latency, so it
  would be exact, but at ~100 entries spread over ~1,000 ns I estimate 75-80 instructions per
  element with data-dependent loops against ~120 for the tuned 4-ary heap: 3-5% at best, with a
  new failure mode. C1 removes 58% of all heap operations instead.
- **Sorted array for the message queue.** Insertion ~55-60 cycles, pop free; the heap with the
  hole trick is ~40 cycles for a replaced event. No clear gain.
- **Separate heap for passive receipts.** Halves two heaps (one level less) but adds a three-way
  minimum; dominated by B4 and C1.
- **Eliding QuerySpread or its response.** Each draws from the shared latency stream in global
  send order and reads the book at its own position in the order; neither can leave the queue.
- **Start-up / shutdown (question 4).** By reading, nothing exceeds ~1 ms on native Linux with the
  memory switches off: `t3_create` seeds 147 generators twice (the default constructor seeds with
  0, then the real seed; ~0.15 ms), creates the helper thread, reads `/sys/fs/cgroup/cpu.max`;
  after the run 3-5 threads are created (~0.05-0.1 ms each); `_exit` skips all frees. The 3 ms
  "parse" on the laptop is file I/O on the Windows-backed mount, not parsing (a 4 KB JSON). A
  whole millisecond per run is ~0.25% of a small unit's score at a 0.35-0.45 s container cost, so
  none of this is worth an upload. I could not measure any of it.

## 6. Why incremental writing may lose on the host (question 5)

No measurement supports any of this; these are mechanisms visible in the code.

1. **The tail after the run is single-threaded.** `do_trace(true)` / `do_msg(true)`
   (launcher 725-760, 831-855) give each file one thread that encodes every column of a group,
   hashes it (`FileSink::put`, 499-507) and writes it (`flush`, one `writev` per 4,096-row group,
   `Stream::add_group` 443-466). Whatever that thread has not finished when the run ends, plus
   `finish()` (467-554: the deferred `msg_type` column for **all** groups, appended to one growing
   string, and a footer with one entry per column per group; 286 groups on gb-mega) is done by
   that one thread. The after-the-run path encodes a file's columns on 2-4 threads and hashes on
   another. If the writer falls behind the simulation on the host (a `writev` into the bind mount
   every 4,096 rows blocks it; the Xeon may run the event loop relatively faster than the laptop
   does), the process ends with one busy CPU where the other design has four.
2. **More work per row.** 4,096-row groups repeat the dictionary page and page headers of the
   string columns, allocate a `std::vector<ChunkMeta>` and restart the delta encoder per group
   (output 97.3 MB against 95.2 MB), and issue hundreds of small `writev` calls instead of one per
   file.
3. **Sleep/wake churn next to a spinning helper.** Each writer sleeps 100 us at a time
   (launcher 669, 736, 840), i.e. thousands of timer wake-ups per second, while `Feed::body`
   (731) never sleeps (2,000 `_mm_pause`, then `sched_yield`). `--cpus=4` is a CFS quota, not a
   CPU set, so the kernel may place a waking writer on the helper's CPU (the sleeper preempts the
   spinner) or on the hyper-thread sibling of the simulation thread. If the helper loses its CPU
   for longer than the ring covers (8,192 values, about 1.2 ms of simulation), `feed_wait` (744-751)
   spins the simulation thread. With only the simulation and the helper runnable during the run,
   nothing wakes up to disturb them. Throttling itself is unlikely: the four threads use well
   under 400 ms per 100 ms period.
4. **Small units pay fixed costs for nothing**: thread creation before the run, up to 100-150 us
   of nap latency after it, and a single encoder thread for a file of one or two groups.
5. Two data points, each bundled with other changes, against a known 1.6% spread between
   identical uploads: the loss may be partly noise.

Host-safe design:
- During the run, exactly two runnable threads (simulation, latency helper); no sleeping pollers,
  no system calls from helpers.
- If output is to overlap the run at all, do it **in the helper's idle slots**: when its ring is
  full, instead of `_mm_pause` it encodes one small slice (a few hundred closed rows of one column,
  a few microseconds) into memory and re-checks the ring. No new thread, no wake-ups, no I/O; the
  bytes depend only on fixed group boundaries. The `kind` column stays deferred as today.
- After the run: finish the remainder on up to four threads, large row groups, one `writev` per
  file, hashing in parallel with encoding.
- Optional robustness: let the helper publish a generator snapshot every 1,024 draws so that a
  starved simulation thread can take the stream over inline (replaying at most ~9K draws in
  skip mode, ~35 us) instead of spinning.
