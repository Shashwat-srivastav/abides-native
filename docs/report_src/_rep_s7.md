### 7.7 Engine rewrite for sub4

**Starting point.** A fresh profile of the sub3 engine (perf, 4 scenarios) was flat: event loop including the heap about 36% of simulate time, `standard_normal` 14%, `send` 13%, ledger appends 9%, order book about 12%. By source line, `std::vector` append bookkeeping accounted for about 11% and heap sifting about 11%. No single hot spot remained, so the data paths were rewritten together.

**Measurement method.** Wall-clock timing on this laptop was too noisy to rank changes (the same binary measured 5.0M and 5.5M mean in back-to-back runs; under memory pressure individual scenarios varied 2×). `native/engine/bench.cpp` therefore reads hardware counters (`perf_event_open`, user-mode cycles and instructions) around `t3_simulate` only, takes the minimum over 5 repetitions per scenario, and reports the mean over all 65 scenarios. Repeated runs agreed within about 1% on cycles and exactly on instructions.

| Step | What changed | Cycles/event (mean of 65) | Instructions/event | 65/65 byte-identical |
|---|---|---:|---:|---|
| sub3 engine | — | 557–561 | 1,010 | ✔ |
| A. Compact records + split heaps | see below | 445–464 | 773 | ✔ |
| B. Blocked queues | see below | 437 | 761 | ✔ |
| C. Latency helper thread | see below | **352** | **576** | ✔ (3 consecutive full runs) |

With the helper thread disabled (`T3_LAT_THREAD=0`) the step-C binary measured 470 cycles/event, so the thread itself is worth about 25% of the loop on scenarios that draw log-normal or Pareto latencies (61 of the 65).

**A. Compact records and split heaps.**

- *Message* shrunk from about 136 to 56 bytes. Order messages carry one price (the fill price for `OrderExecutedMsg`, the limit price otherwise — each reader uses only one of them); the spread reply reuses the same fields with a flag byte; the never-read bid/ask sizes are no longer stored.
- *Message pool*: a plain vector with slot reuse. The dispatched message is copied by value (56 bytes) and its slot freed before the handler runs, replacing the `std::deque` whose indexing needed two loads and a division.
- *Ledger*: one 40-byte record per delivery (`t_recv, t_send, order_id, message_id, causal, src, dst, type`) written through a raw cursor, instead of 13 separate column appends. The 13 output columns are built from these records in `t3_finish`. Fields that do not apply to a message type hold stale values and are masked there (`t_send`, `causal` for wakeups; `order_id` for non-order messages). `seq` is the row index; `latency = t_recv − t_send`.
- *Order log*: 40-byte rows through a raw cursor; the per-owner sequence number was dropped (within one owner, log order equals append order, so the row index gives the same tie-break). The "final fill" tag is now found in `t3_finish` by one backward scan instead of a per-execution index update.
- *Quote log*: one record per handled order holding both sides, instead of two.
- *Event queue*: two 4-ary heaps, one for wakeups and one for in-flight messages; the next event is the smaller of the two tops. Measured sizes explain the gain: on `mp07` the wakeup heap averaged 15 entries and the message heap 10; on `gb_mega` 145 and 106. Near-term messages no longer sift through the wakeup population.
- *"Hole" trick*: the dispatched event stays at the top of its heap until the handler schedules something into the same heap, which then replaces it with one sift instead of a pop plus a push.
- *Rounding*: `py_round` uses `cvtsd2si` (rounds in the current mode, nearest-even) inline instead of a `nearbyint` library call. Equal for every in-range value.

**B. Blocked queues (requeues).** Instrumentation showed that in a few scenarios most loop iterations did no work:

| Scenario | Loop iterations | of which requeues | Deliveries |
|---|---:|---:|---:|
| `mp07_heavy_flow_oldest` | 64,257 | 126 | 64,131 |
| `sf_01_baseline_regime` | 64,498 | 1,211 | 63,287 |
| `fastlob_core` | 194,469 | 131,554 | 62,915 |
| `as03_mm_liquidity_heavy` | 105,590 | 56,150 | 49,440 |
| `mr_deep_book_state_size` | 980,960 | 711,316 | 269,644 |
| `gb_mega_throughput` | 1,481,452 | 60,590 | 1,420,862 |

A requeue is the reference kernel popping an event whose recipient is still busy and pushing it back at the recipient's busy-until time. When a market maker sends a burst of k orders, the exchange handles one, becomes busy, and the other k−1 are popped and pushed back — once per busy period, O(k²) in total.

Equivalent formulation: a blocked event's effective time *is* its recipient's busy-until time, which changes only when that recipient dispatches. So all blocked events of one agent share one time and are ordered by their key `(sender, recipient, message_id)` alone. They wait in a per-agent min-heap on the 64-bit key; the loop takes the minimum over the two main heaps and every non-empty blocked queue's `(busy_until, smallest key)`. An event is also blocked directly at send time when the recipient is busy past the delivery time.

*(From sub18 the blocked queues are sorted vectors with a read position instead of binary heaps: §9.9.7.)*

Why the output cannot change:
- The selection is still the global minimum of the same `(time, sender, recipient, message_id)` values the reference would hold, so the dispatch sequence is identical.
- A skipped requeue pop has no side effect except setting the kernel's current time, which the next dispatch overwrites. The one place it matters is the stop check, so send-time blocking is applied only when the delivery time is ≤ `stop_time`, and pop-time blocking still sets the current time first.
- The recipient cannot dispatch before its busy-until time, so an event blocked at send time would certainly have been requeued. (The sender is the dispatching agent and is never the recipient, so the busy-until value read at send time is final.)

Effect: the mean moved only from 773 to 761 instructions/event because few scenarios are requeue-heavy, but those scenarios left the list of slowest units (`mr_deep_book` was the worst at 1,077 instructions/event and 675 cycles/event before the change).

**C. Latency helper thread.** After A and B an instruction-level profile showed `standard_normal` (23%) and `send` including the latency draw (20%) as the largest items of simulate time. Every `send` is between two different agents and draws exactly one latency from a generator nothing else reads, so the k-th latency depends only on k.

- A helper thread computes the same stream with the same code from a copy of the generator, running ahead during the run; the loop takes value k from an 8,192-entry single-producer/single-consumer ring.
- Start-up is wait-free: the loop draws inline (counting its draws) until the helper has passed it, then switches to the ring at its own draw index. If the helper never gets ahead within 8,128 draws, the loop stays inline for the whole run.
- The helper is created only for the log-normal and Pareto models, and only when the process can run two threads at once (affinity mask and cgroup v1/v2 CPU quota ≥ 2; `T3_LAT_THREAD=0/1` overrides).
- Drawing ahead is unobservable because the latency generator has no other consumer.

*(Later history of the helper thread: its start-up and hand-over were changed in sub17 (§9.9.5), it was made to sleep on a full ring of 32,768 values in sub18 (§9.9.7), and the code described here was restored in sub19a and sub19b (§9.9.9). On the scoring host the thread as described here is worth 9.5% of score (§9.9.8). "Drawing ahead is unobservable" holds for the output files; a draw the run never consumes can, however, still raise the `log`-sensitivity flag of §7.8 and so change which path handles a scenario (§9.9.10).)*

**Independent review.** A read-only reviewer agent checked the refactor (hole logic, stale-field masking, delay ordering against the fork kernel source) and reported no bug; it also derived the blocked-queue equivalence independently. Its remaining suggestions (16-byte heap entries, PGO, struct layout, prefetching: 1–8% each, estimated not measured) were not implemented because the scoring change made the event loop a minor part of the measured time.

*(A profile-guided build was adopted later, in sub11: §9.8.4.)*

### 7.8 The no-Python launcher (sub4)

**Why.** Under the new rule (§2.2) the whole process is timed. Measured inside the sub3 image on this laptop, one process each:

| Command | Time |
|---|---:|
| `python -c pass` | 98 ms |
| `python -c "import ctypes, json, hashlib"` | 230 ms |
| `python -c "import pyarrow"` (imports numpy) | 747 ms |
| `python -c "import numpy"` | 1,011 ms (single run; noisy) |
| `simulate` on `eq_deterministic_baseline` (10,669 events; simulation ≈ 4 ms) | 808–888 ms warm, 2,129 ms first run |
| `/bin/true` | 18 ms |
| C++ program linked against pyarrow's libarrow/libparquet, writing a 100k-row file | 78–101 ms warm, 285 ms first run |

`python -X importtime` attributed about 289 ms to numpy and 343 ms to `t3native.native_sim` in total. The simulation was under 1% of the process.

**Feasibility test.** A 15-line C++ program including `<arrow/api.h>` and `<parquet/arrow/writer.h>` from the pyarrow wheel linked against `libarrow.so.1500` / `libparquet.so.1500` with `-D_GLIBCXX_USE_CXX11_ABI=1` (0 undefined references) and failed with ABI 0 (9 undefined references). That settled the build recipe.

**What the launcher does** is listed in §3. The points that needed care:

| Topic | Decision | Reason |
|---|---|---|
| Parquet bytes | Same library binary as pyarrow, with the properties `pyarrow.parquet.write_table` sets (read from `_parquet.pyx` in the image): format 2.6, data page V1, Snappy, dictionary on, statistics on, `max_row_group_length` 64 Mi, page index and checksum off, `store_schema`, engine V2, compliant nested types; `WriteTable(table, min(rows, 1,048,576))`; the same pandas metadata string | Guarantees identical bytes rather than merely equivalent content |
| Parallel column encoding | `set_use_threads(true)` for single scenarios | Tested: identical bytes |
| Hashing | The file is encoded into memory, hashed with libcrypto's `SHA256`, then written with one `write` | No re-read of the file |
| JSON | Own strict parser; integers must be integer tokens, floats are parsed with `strtod` (correctly rounded, like Python's `float`) | Reproduces `int(...)`/`float(...)` only where they are unambiguous |
| `events.json` | Same keys in the same order, floats printed as the shortest round-tripping decimal | The file is not hashed against the reference, but consumers parse it |
| Exit | `_exit(0)` after the outputs are complete | Skips freeing large buffers and library destructors |
| Self-reported `wall_clock_sec` | Single scenario: the event loop, as before (reference scope). Batch: the whole batch, start of first sub to last write | Never flattering |

**When the launcher declines** (it then `exec`s the Python path with the same arguments):

- unrecognised command-line argument; missing config; UTF-8 BOM; trailing data; JSON that is not strictly standard (e.g. `NaN`, `Infinity`);
- a value of an unexpected JSON type (a float where an integer is expected, a string where a number is expected, a non-boolean `protocol_enforcement`, and so on);
- any value outside the certified numeric domain (the same checks as `native_sim._check_domain`), seed outside `[0, 2³²−1]`, more than 60,000 agents;
- a `scenario_id` or batch file name that would need JSON escaping; a hidden or non-regular file in the batch directory;
- no `latency_config`; an agent type other than the four supported;
- the engine rejects the scenario, fails, or produces an empty trace;
- `T3_FORCE_REFERENCE=1` or `T3_NO_LAUNCHER=1`;
- **a latency draw whose rounding is sensitive to the `log` implementation** (next paragraph).

*(Changed in sub7: a whole number written as a float is accepted where an integer is expected, exactly as `int()` accepts it in the Python path: §9.7.2.)*

**The `np.log` problem and its resolution.** The log-normal model needs μ = `np.log(mean_ns)`. The reference computes it with numpy, whose `log` on AVX-512 machines is a vectorised implementation that may differ from glibc's `log` in the last bits; this laptop has no AVX-512, the grading host does. Without Python the launcher can only call glibc's `log`. Options considered:

| Option | Verdict |
|---|---|
| Keep a Python process just for this value | Costs the numpy import; defeats the purpose |
| Embed numpy's vectorised `log` code | Cannot be tested here (no AVX-512 hardware); a wrong dispatch condition would silently zero units |
| Compute μ with glibc and **detect whether it could matter** | Chosen |

A difference of a few ulps in μ changes a latency `exp(μ + σ·g)` by a relative 10⁻¹⁵–10⁻¹⁴, which alters the integer result only if the value lies that close to a rounding boundary or a clamp bound. The engine flags any log-normal draw within a relative 6·10⁻¹⁴ (more than 16 ulps of μ) of a `.5` boundary or of `min_ns`/`max_ns`. If a run is flagged, the launcher discards it and re-runs through the Python path, where numpy supplies μ. An unflagged run is therefore the same for either `log`. Expected flag rate: about 6·10⁻⁹ per draw at a 100 µs mean latency, i.e. under 1% of runs even for a million-draw unit. In the 65 public scenarios and 6 batch units, **0 runs were flagged**.

*(The guard was first seen to fire, on 4 of the 1,318 stored fuzz cases (§9.7.2). The number of flagged cases later differed between replays of different builds; §9.9.10 gives an explanation that has not been confirmed by a targeted test.)*

This assumes numpy's result is within 16 ulps of glibc's. That bound was not verified on AVX-512 hardware (§11).

**Results** (launcher binary in the dev container, hashes recomputed from the files on disk and compared with the baseline image's):

| Check | Result |
|---|---|
| 65 single scenarios | 65/65 identical, 0 fallbacks (run 3 times: before parallel encoding, after it, and after adding the batch verb) |
| 6 batch units (30 sub-scenarios) | 6/6 identical, `batch_events.json` structure and per-sub hashes equal |
| Total process time for the 65 scenarios | 22.2 s and 25.7 s in two runs (Python path: not measured for all 65; 15.3 s for just 5 of them) |
| Batch unit process time | 148–1,192 ms (`dense-3` 781 ms, `hetero-mix` 1,192 ms, `homog-4` 163 ms, `homog-8` 228 ms, `many-6` 185 ms, `varsize` 148 ms) |

Phase breakdown from `T3_PHASES=1`, two runs each (ms):

| Scenario | parse | create | simulate | finish | write | of which encode trace / ledger |
|---|---:|---:|---:|---:|---:|---|
| `eq_deterministic_baseline` | 86 / 5 | 5 / 4 | 4 / 4 | 9 / 5 | 46 / 24 | 18 / 36 and 12 / 20 |
| `mp07_heavy_flow_oldest` | 6 / 7 | 10 / 7 | 14 / 18 | 15 / 31 | 1,517 / 206 | 41 / 74 and 97 / 177 |
| `gb_mega_throughput` | 8 / 5 | 282 / 1,234 | 299 / 270 | 711 / 532 | 1,452 / 1,745 | 770 / 980 and 1,120 / 1,331 |

The spread between paired runs (create 282 vs 1,234 ms; a 2.3 MB file write taking 21 ms or 1,440 ms) is this machine under memory pressure, not the program. What the table does establish: for small units almost all remaining time is Parquet encoding and file writing; for the largest unit, buffer pre-faulting, output assembly and encoding each cost as much as or more than the simulation.

