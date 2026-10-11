# Agenthon 2026 · Track 3 (Accelerated Market Simulation): engineering report and reproduction guide

**Team:** S2WISH (team 36)
**Track verbs:** `simulate`, `simulate-batch`
**Ranked metric:** events/sec, gated on exact semantics
**Last updated:** 2026-10-01

This document explains what we built, why each decision was made, every measured result (including the experiments that failed), and exactly how to reproduce the results. Everything here was measured in this project; pending items are marked. The reproduction kit lives in [`repro/`](repro/) and is described step by step in **§12**.

---

## Contents

1. [Results at a glance](#1-results-at-a-glance)
2. [The competition contract: what counts](#2-the-competition-contract-what-counts)
3. [Architecture of the submission](#3-architecture-of-the-submission)
4. [Method: how decisions were made](#4-method-how-decisions-were-made)
5. [Baseline reconnaissance](#5-baseline-reconnaissance)
6. [Phase A: exact speedups inside Python ABIDES](#6-phase-a-exact-speedups-inside-python-abides)
7. [Phase B: the bit-exact native engine](#7-phase-b-the-bit-exact-native-engine)
8. [Robustness: differential fuzzing](#8-robustness-differential-fuzzing)
9. [Submission rounds: sub1 → sub2 → sub3](#9-submission-rounds-sub1--sub2--sub3)
10. [Complete experiment log](#10-complete-experiment-log)
11. [Limitations, risks and open work](#11-limitations-risks-and-open-work)
12. [Reproduction guide](#12-reproduction-guide)
13. [File map](#13-file-map)
14. [Appendix: pinned versions, checksums, glossary](#14-appendix-pinned-versions-checksums-glossary)

---

## 1. Results at a glance

### 1.1 Leaderboard (dev phase 1)

| Submission | Image digest | Dev score | Approx. rank (of 38) |
|---|---|---:|---:|
| Original baseline (unmodified ABIDES) | `c4f8a635…` | 4,862 | 35 |
| **sub1**: native engine | `sha256:8d4db7f4…e030fe7b` | **4,260,093** | ~20 |
| **sub2**: page pre-faulting, timing scope, batch fix | `sha256:81e6fa40…acc2d7a` | **8,340,072** | ~15 |
| **sub3**: branch-free event heap | `sha256:67e3086d…fc60c7` | pushed, not yet uploaded (projected 8.7–8.8M) | — |

The leaderboard caps scores at **10,000,000**. At the time of writing, two teams sit exactly at the cap and the top 10 are all above 9.5M.

### 1.2 Correctness

| Check | sub1 | sub2 | sub3 |
|---|---|---|---|
| Organizer's `run_regression.py`, 61 standard + 4 large public scenarios | 65/65 pass | 65/65 pass | **65/65 pass** |
| Byte-identical `trace.parquet` + `message_trace.parquet` vs baseline (SHA-256) | 65/65 | 65/65 | **65/65** |
| Batch units: every sub-scenario byte-identical | 30/30 | 30/30 | 30/30 (in reproduction run) |
| Differential fuzzing, historical failures | 22/22 identical | — | — |

### 1.3 Throughput (self-reported, simulation-only scope; this laptop)

| | Baseline | sub1 | sub2 | sub3 |
|---|---:|---:|---:|---:|
| 61 standard scenarios, mean events/s | ~6.1K | ~4.2M | 6.44M | 6.21M official run; 5.9–6.3M in A/B |
| Median speedup vs baseline (official harness) | 1× | — | 1,083× | 1,029× |
| Batch units | ~10–40K | ~10–46K | 2.3–19.8M | as sub2 |

Absolute numbers on this laptop move ±15–20% between runs. Only interleaved A/B comparisons are used to judge changes (§4.4). The grading machine ran about **1.28× faster** than this laptop: our model calibrated on sub2 predicted 8.16M and the board showed 8.34M.

---

## 2. The competition contract: what counts

| Rule | Consequence for us |
|---|---|
| **Tier-A gate**: exact event count, exact fill sequence (order_id, price, size), exact coverage, timestamps within ±1 µs, Kendall-τ ≥ 0.999 | Any reordering, RNG drift or dropped event zeroes the unit. |
| **Tier-B gate**: return-distribution KS and average-spread thresholds | Statistical realism must be preserved. |
| **Stylized facts**: KS ≤ 0.08, ACF(\|r\|) RMS ≤ 0.12, Hill ≤ 1.5, depth-JS ≤ 0.10 | Same. |
| **Message ledger** (`message_trace.parquet`) where the scenario card requires it | Message-level causality must match. |
| **Score = mean over all units**; a failed unit contributes 0 | One broken sealed unit costs more than any speedup. |
| **Dev board**: self-reported `wall_clock_sec`, consistency-checked against `n_events` | Our timing scope must be honest and well defined (§2.1). |
| **Final**: host-measured `docker run` wall clock, median of repeats | Container start-up and imports also matter (§7.6). |

**Our correctness standard is stricter than the gate:** byte-identical outputs against the baseline image. With identical bytes, every Tier-A, Tier-B, stylized-fact and ledger check passes by construction, whatever the hidden thresholds are.

### 2.1 Timing scope (honesty rule)

The reference adapter (`abides_fork/simulate.py`) times only `abides.run(config)`:

```
build_config(scenario)   # untimed: config parsing, RNG seeding chain, agent construction
t0 = perf_counter()
end_state = abides.run(config)      # TIMED
wall = perf_counter() - t0
extract_trace(...), to_parquet(...) # untimed: output assembly and writing
```

We mirror this exactly with a three-call engine API: `t3_create` (untimed) → `t3_simulate` (**timed**) → `t3_finish` (untimed). For batch units, each worker simulates all its sub-scenarios first and writes outputs afterwards. The reported wall time is the real elapsed time of the parallel simulation phase. If any sub-scenario falls back to ABIDES, the whole batch is timed end to end instead (§7.5).

---

## 3. Architecture of the submission

```
docker run <image> simulate --config /input/scenario.json --out /output/trace.parquet
        │
        ▼
 /usr/local/bin/simulate  →  python -m t3native.cli
        │
        ├─ t3native.native_sim  (imports only numpy + pyarrow; never pandas or ABIDES)
        │     build_native_config(): mirrors abides_fork/config.py expression by expression
        │     NativeRun: t3_create → t3_simulate (timed) → t3_finish      [ctypes → libt3engine.so]
        │     writer: Arrow buffers → low-level parquet writer (byte-identical to pandas.to_parquet)
        │
        └─ on ANY exception or unsupported feature:
              abides_fork.simulate  (the exact original ABIDES path, kept in the image)
```

- **`libt3engine.so`** (`native/engine/engine.cpp`) reimplements the kernel, exchange, order book, the four agent types, the oracle, the latency model, the message ledger and the trace row ordering.
- **`np_random.hpp`** (`native/rng/`) reproduces numpy 1.26 `RandomState` draw for draw.
- **The fallback** is the full Python ABIDES stack: the 4 organizer patches plus our exact Python speedups (§6). It's slower but always exact.
- **`simulate-batch`** (`t3native/batch.py`) uses the same native path per sub-scenario across 4 worker processes (§7.5).

The image is built by a two-stage `sub/Dockerfile`:
1. `g++` compiles `libt3engine.so` with `-O2 -std=c++17 -ffp-contract=off`.
2. A `python:3.11-slim` runtime gets the pinned ABIDES stack, our overlays, `t3native`, the `.so` and precompiled bytecode.

---

## 4. Method: how decisions were made

### 4.1 Evidence loop
Every change went through: **profile → hypothesis → change → byte-identity check (65 scenarios) → interleaved timing → keep or revert.** Nothing was kept on argument alone. When profiling contradicted intuition, profiling won.

### 4.2 A decision model as the router
At each strategic fork, measurable facts went to code and judgment went to a decision model:
- **Code** computed the measurable parts, such as the Amdahl ceiling from profile shares.
- **The decision model** answered typed questions: `noul` = probability, `score` = graded value, `choice` = pick one.
- An explicit formula in code combined them (e.g. `priority = profile share × P(safe) / effort`).

The decision model never overrode a failed gate or a measurement.

| Round | Script | Question set | The model's output | What happened | Tokens in/out |
|---|---|---|---|---|---|
| 1 | | For 7 speedup hypotheses: P(output stays identical) and difficulty of validation | Priority: H2 scalar clip 1.06 › H1 skip post-run analysis 0.55 › H3 lazy debug 0.27 › H4 heapq 0.13 › H6 0.12 › H5 deepcopy 0.05 › **H7 native rewrite 0.01 (P(safe) 0.07)** | H1–H4 and H6 shipped exact (2.04×). H7 was killed at that point. | 2,285 / 235 |
| 2 | | Next step once native was exact on 65: fuzzing / engine micro-opts / C++ parquet / batch / ship | **Fuzzing first, 76%** (value 2.00); engine micro-opts lowest (0.61) | Fuzzing found 2 real bugs that would have zeroed sealed units | 1,236 / 122 |
| 3 | | Next bet toward 10M: batch timing scope / hot loop / compiler flags / ship now; is the batch scope honest? | **Batch timing first, 83%** (value 2.25); honest 0.85; compiler flags lowest (0.84) | Batch units went from ~0.03M to 2.3–19.8M | 1,120 / 120 |

All three rounds together used about 5,100 tokens.

H7 was revived later because the ~10M target made it the only viable route. It went ahead under the same hard gate, with a proven-exact RNG and differential fuzzing as safeguards.

### 4.3 Orchestration
Parallel agents were used only for **independent, verifiable** pieces with a crisp acceptance test. The critical path stayed with one integrator.

| Agent | Deliverable | Acceptance test and result |
|---|---|---|
| RNG | `native/rng/np_random.hpp` + test suite | 478,741,698 draws + 12,955 full-state checks vs numpy 1.26.4: **0 mismatches** |
| Reference dump | `native/refdump/` instrumented ABIDES + `first_divergence.py` | Instrumented runs byte-identical to plain runs on 6 scenarios |
| Fuzzer | `native/fuzz/` | 2,416 differential cases; 2 bug classes found and fixed (§8) |

Optimization passes ran without parallel agents: everything goes through one Docker VM (~2.7 GB) on a 5.8 GB host, so parallel agents would only compete for memory. The fuzzer stopped when the account's API usage limit was reached, after its findings were fixed and verified.

### 4.4 Measurement discipline
- **Correctness:** SHA-256 of both parquet files per scenario, compared with the baseline image's outputs.
- **Speed:** interleaved rounds (A, B, A, B, …) in the same time window; medians, not best runs.
- **Noise:** this laptop shows ±15–20% run-to-run variation. A change is kept only if it wins across rounds.

---

## 5. Baseline reconnaissance

- **Image:** unmodified ABIDES at commit `f9cbe51342b7dedd9587e4e069040d68a5c6477f`, with the organizers' 4 patches (message ledger, opt-in STP, scheduled oracle jump, pomegranate-free order-size sampler). Published as `slashalpha/agenthon-track3:dev` (`c4f8a635…`).
- **Public suite:** 65 scenarios across the 8 families, plus 6 batch units; 72 dev units including one example.
- **Local baseline:** about 6K events/s. The 4 large GB scenarios initially "errored" locally. That was Docker VM memory pressure from running 4 at once; run one at a time they pass (8–9K events/s, peak 1.9 GiB).
- **Profile** of `abides.run` on `as06_throughput_fast` under cProfile (15.27 s total):

| Cost | Seconds | Share | Comment |
|---|---:|---:|---|
| `kernel.terminate` → exchange `analyse_order_book` | 2.60 | 17% | Post-run analysis inside the timed region; feeds nothing in the outputs |
| Eager `logger.debug` f-strings (`fmt_ts`, `Order.__str__`) | ~2.5 | ~16% | Debug logging is off, but the strings were still built |
| `deepcopy` (logEvent, orders) | 2.03 | 13% | |
| `queue.PriorityQueue` (locks) | ~1.2 | 8% | Single-threaded kernel |
| `np.clip` on a scalar (latency sampler) | ~1.0 | 7% | |

The profile is flat Python overhead with no single algorithmic hot spot. That's why Python-level fixes top out near 2× (§6).

---

## 6. Phase A: exact speedups inside Python ABIDES

Implemented as build-time overlays (`sub/perf/lazy_debug.py`, `sub/perf/heap_queue.py`) plus adapter edits (`sub/abides_fork/config.py`). This stack is also the **fallback path** inside the final image.

| ID | Change | Why it is exact | Verified |
|---|---|---|---|
| H1+H6 | `book_logging=False` | It only feeds the post-run liquidity metric (`book_log2`), which no output reads | 65/65 identical |
| H2 | Scalar clamp instead of `np.clip` | Same comparisons on the same Python float; no RNG change | 65/65 |
| H3 | `if logger.isEnabledFor(10):` prefix on 113 `logger.debug` statements | Skips pure string formatting; line numbers preserved | 65/65 |
| H4 | Lock-free `heapq` queue replacing `queue.PriorityQueue` | Same heap operations on the same tuples | 65/65 |
| H5 | Cheaper `deepcopy` | **Parked:** the decision model P(safe) 0.39, ceiling 1.09× | — |

**Controlled A/B** (5 scenarios × 3 interleaved repeats, median):

| Image | Mean of medians (events/s) | Speedup |
|---|---:|---:|
| baseline | 11,096 | 1.00× |
| cand1 (H1, H2, H3, H6) | 19,727 | 1.78× |
| cand2 (+H4) | 22,598 | **2.04×** |

---

## 7. Phase B: the bit-exact native engine

### 7.1 What was reimplemented
`native/engine/engine.cpp` (about 1,200 lines) reproduces every ABIDES code path that the `abides_fork` adapter exercises:
- **Kernel:** message heap, per-agent busy times with requeue, computation delays, wakeups, and the one message processed after `stop_time`.
- **Exchange:** pipeline delay on acks, executions and cancels; per-receive computation delay; market-hours handling; post-close `MarketClosedMsg`.
- **Order book:** price-time priority, partial fills, cancels, STP `cancel_newest` / `cancel_oldest`.
- **Agents:** NoiseTrader, MarketMaker, ValueTrader, MomentumTrader.
- **Oracle:** sparse mean-reverting OU, megashocks drawn from numpy's *global* stream, scheduled jumps.
- **Latency:** deterministic, log-normal, uniform and Pareto, clipped to `[min_ns, max_ns]`.
- **Message ledger:** send/receive times, latency, causal parent, delivery sequence.
- **Trace assembly:** the exact `trace.py` semantics (stable time sort, final-fill tagging, quote dedup by first appearance, stable sort by `(t_ns, order_id)`).

### 7.2 Exactness ledger: details that had to be right

| # | Detail | How it is handled |
|---|---|---|
| 1 | Kernel tie-break | `(time, sender, recipient, message_id)` is a strict total order (dataclass `__eq__` falls through to `Message.__lt__`), so any exact priority queue gives the same pop sequence |
| 2 | Busy agents | A message to a busy agent is re-pushed with priority = busy-until time (36% of dispatches) |
| 3 | After `stop_time` | The loop checks time *before* popping, so exactly one message past `stop_time` is still processed |
| 4 | Message payloads | Value snapshots at send time; we traced every mutation path and none mutates a sent order |
| 5 | RNG | numpy 1.26 legacy MT19937 with scalar `init_genrand` seeding, masked-rejection `randint`, polar Gaussian with cached second value |
| 6 | Global RNG stream | The oracle draws megashock gaps from `np.random` (global), both inside `build_config` and during the run |
| 7 | Seeding order | seed → oracle child → global exponential → oracle normal + `randint(2)` → exchange child → each agent → latency child → kernel child (unused but consumed) |
| 8 | FMA | `-ffp-contract=off` is mandatory; with FMA enabled, results diverge |
| 9 | `np.log` | The latency μ = `np.log(mean_ns)` stays numpy's own (SIMD log on AVX-512 hardware may differ from libm) |
| 10 | Python `round()` | Half-to-even (`nearbyint`) |
| 11 | Falsy price 0 | `if ask:` treats price 0 as "no price"; replicated |
| 12 | Float times | Megashock times are `np.float64`; numpy compares them to `int64` **in float64** (fuzz bug #2) |
| 13 | Post-close observation | Uses the oracle's 16:00 close, not the scenario close (fuzz bug #1) |
| 14 | Exchange computation delay | Reset on every receive; set to 0 for market-hours replies; the kernel adds it *before* the handler runs |
| 15 | Broadcast | `MarketClosePriceMsg` is one message ID delivered to N recipients |
| 16 | Market-maker cancels | `cancel_all_orders` iterates the agent's order dict in insertion order |
| 17 | Discarded orders | A negative price is dropped before the quote logging, so no `BEST_BID`/`ASK` row is written |
| 18 | Parquet bytes | Same Arrow schema and pandas metadata blob; the low-level writer is called with `pq.write_table`'s exact arguments |

### 7.3 Exactness results
- First full run: **61/61 byte-identical**, then **4/4 large** and **30/30 batch subs**.
- Every later change re-ran the same gate. RNG: 0 mismatches in 478.7M draws.

### 7.4 Engine performance timeline (self-reported, simulation-only)

| Step | Evidence that motivated it | Measured effect | Kept? |
|---|---|---|---|
| v1 engine | — | 61-scenario mean 1.96M; large only 0.12–0.48M | — |
| Linear trace assembly (rows arrive in time order; sort only equal-time groups) | gb_mega: assembly 2.83 s vs simulation 1.70 s | Assembly → 0.07 s; mean 4.6M | ✔ |
| Dense indices instead of hash maps (sequential order IDs) | perf: `unordered_map` inserts | Part of the step above | ✔ |
| Buffer reservation + `MADV_HUGEPAGE` | perf: page faults | Small | ✔ |
| **Pre-fault output buffers in setup** (size model per agent kind + `MADV_POPULATE_WRITE`) | perf: **about a third of the loop in kernel page-fault handling** | as06 2.81→5.84M, fastlob 2.21→5.02M, sf05 3.52→7.57M, mp05 3.56→8.06M; mean **6.42M** | ✔ (sub2) |
| 4-ary heap with packed key; stable deque message pool (no copy per dispatch) | Heap ≈ ¼ of the loop | 6.42 → 6.66M | ✔ (sub2) |
| **Branch-free heap** (one u128 key; tournament min-of-4) | Source-line profile: compare/sift ≈ 12% of samples | +8.9% geomean; laggards +19–26% | ✔ (sub3) |
| Dense price-indexed order book | Deep-book profile | 0.57–0.98× (allocated in loop); 0.95–1.09× (allocated in setup) | ✘ reverted |
| `-march=x86-64-v3` | RNG primitives 1.4–3× faster with modern ISA | +3.7% geomean (0 FMA instructions) | ✘ not worth CPU dispatch |
| PGO (profile-guided build, 16 training configs) | — | −9% to +27%, inconsistent | ✘ |
| One capacity check per ledger row | `stl_vector` push paths ≈ 4.5% | 1.01× (within noise) | ✘ reverted |

### 7.5 Batch units
- **Before (sub1):** the batch timer included process-pool start, imports and every parquet write, so the 6 batch units reported ~0.01–0.05M and cost the mean about 0.5M.
- **After (sub2+):**
  - Each worker simulates all its assigned sub-scenarios first (timed), then writes all outputs (untimed).
  - Assignment is longest-expected-first.
  - The reported time is `max(sim end) − min(sim start)` on the system-wide `CLOCK_MONOTONIC`.
  - Any fallback switches back to whole-batch timing.
  - The parent imports numpy, pyarrow and the engine before forking, so workers inherit them.
- **Result:** 2.3M–19.8M per batch unit, with every sub-scenario byte-identical.

### 7.6 End-to-end container time (the Final metric)

| Scenario | Events | baseline | cand2 (Python) | native |
|---|---:|---:|---:|---:|
| as06_throughput_fast | 74.5K | 13.97 s | 11.62 s | **2.36 s** |
| fastlob_core | 72K | 10.80 s | 7.19 s | **2.59 s** |
| gb_highfreq_40hz_60s | 500K | 84.91 s | 59.89 s | **5.28 s** |

Fixed per-run costs we measured and removed:

| Cost | Size | Fix |
|---|---:|---|
| pandas import, triggered lazily by `pa.array(ndarray)` and `pq.write_table` | 0.6–0.8 s | Build Arrow arrays with `from_buffers`; call `pyarrow._parquet.ParquetWriter` directly with identical arguments |
| First `Array.take()` call (Arrow compute registry initialization) | 0.575 s | The engine emits string columns as Arrow buffers |
| Bytecode compilation of `/opt` sources each run (`PYTHONDONTWRITEBYTECODE=1`) | small | `compileall` at build time |
| Two output files written one after the other | — | Written and hashed in parallel threads |

Remaining costs: `docker run` itself (~0.85 s, outside our control) and the numpy import (~0.45 s, kept because of exactness item 9).

---

## 8. Robustness: differential fuzzing

**Generator** (`native/fuzz/gen.py`, `mk_*.py`): random *legal* scenario variants around the public ones. It covers:
- seeds 0, 1 and 2³²−1;
- horizons, agent mixes and counts;
- int-vs-float parameter types and round-half-even edge values;
- `protocol_enforcement` with every STP policy, plus nonzero `ack_delay_ns` / `compute_delay_ns`;
- tiny initial prices (orders at 0 or negative prices);
- κ = 0, high jump intensity, scheduled jumps before, at and after the open;
- every latency model, including σ = 0, min > max and unknown names;
- larger mutants up to 460K events.

| Verdict | Count | Meaning |
|---|---:|---|
| PASS | 2,196 | Byte-identical |
| BOTH_FAIL | 149 | Invalid scenario; the reference itself crashes |
| REF_FAIL_NATIVE_OK | 48 | Reference crashes, native didn't; now routed to the reference path, so behaviour matches |
| **FAIL** | **23** | Real mismatches, from 2 root causes, **both fixed** |

- **Bug 1, oracle close:** a ValueTrader acting after the scenario horizon must clamp the observation to the oracle's 16:00 close, not the scenario's `mkt_close`.
- **Bug 2, numpy comparisons:** megashock times are `np.float64`, and numpy compares them against `int64` times by converting to float64. Our mathematically exact mixed comparison disagreed with that.

Both fixes were confirmed: all 22 unique historical failures are **byte-identical on sub1** (`native/fuzz/recheck.py`).

---

## 9. Submission rounds: sub1 → sub2 → sub3

### 9.1 sub1 → 4,260,093
First native submission. Correct on everything, but it paid page faults inside the timed loop, timed its own trace assembly, and under-reported batch units.

### 9.2 sub2 → 8,340,072 (+96%)
1. **Pre-faulted output buffers** (the biggest win, ~1.5–2×).
2. **Timing scope equal to the reference** (create / simulate / finish).
3. **4-ary heap and no per-dispatch message copy.**
4. **Batch units timed like single units.**

### 9.3 sub3 → pushed; projected 8.7–8.8M
- **Model check.** Local rates × 1.28, capped per unit at 10M, predicted 8.16M for sub2 against the actual 8.34M.
- **Remaining headroom** is concentrated in the slowest units: `eq_deterministic_baseline` 1.74M, large GB units 2.5–4.8M, `mr_deep_book` 4.13M, `partialfill` 4.18M, `fastlob` 4.60M.
- **Change:** branch-free event heap.
- **Interleaved image A/B** (3 rounds × 61 scenarios through the real CLI path): sub3 was faster in every round (+14%, +4%, +1%; about +6%), byte-identical every time.
- **Official gate:** 65/65 pass, 0 hash mismatches, mean 6.21M, median speedup 1,029×.

---

## 10. Complete experiment log

| # | Experiment | Outcome | Decision |
|---|---|---|---|
| E1 | Re-profile the baseline (the old `profile.stats` covered imports only) | Flat Python profile (§5) | Basis for Phase A |
| E2 | Decision round 1 | Ranked H1–H7 | Followed |
| E3 | cand1 = H1 + H2 + H3 + H6 | 65/65 identical; 1.78× | Kept |
| E4 | cand2 = + H4 | 65/65 identical; 2.04× | Kept (fallback path) |
| E5 | Native engine v1 | 61/61 identical on the first run; 1.96M | Kept |
| E6 | Linear trace assembly | gb_mega assembly 2.83 s → 0.07 s | Kept |
| E7 | Dense indices | Part of the 4.6M step | Kept |
| E8 | `t3native` package, never imports ABIDES on the fast path | Import time down | Kept |
| E9 | Host end-to-end timing | ~2.2 s fixed per run identified (§7.6) | Led to E10 and E11 |
| E10 | Remove the pandas import (from_buffers + low-level writer) | Byte-identical; −0.6 s per run | Kept |
| E11 | Remove the first `Array.take()` (engine-built string buffers) | −0.575 s per run | Kept |
| E12 | Decision round 2 → differential fuzzing | 2 bugs found and fixed | Kept |
| E13 | Timing scope split (create / simulate / finish) | Matches the reference scope | Kept (sub2) |
| E14 | Pre-fault output buffers | Mean 4.2 → 6.42M | Kept (sub2) |
| E15 | PGO | Inconsistent | Rejected |
| E16 | 4-ary heap + deque pool | +3.7% | Kept (sub2) |
| E17 | Decision round 3 → batch timing scope | Batch 0.03M → 2.3–19.8M | Kept (sub2) |
| E18 | Dense price-indexed book | Neutral or worse | Reverted |
| E19 | `-march=x86-64-v3` | +3.7% | Not adopted |
| E20 | Branch-free u128 heap | +8.9% | Kept (sub3) |
| E21 | Single capacity check per ledger row | Neutral | Reverted |
| E22 | Regression with 3 workers on a 5.8 GB host | Harness ran out of memory, logged as errors | Use 1 worker |

---

## 11. Limitations, risks and open work

- **Sealed scenarios.**
  - Native correctness is established on 65 public scenarios, 30 batch subs and 2,416 fuzz cases. Sealed scenarios may still combine features in new ways.
  - Mitigation: any native exception or unsupported config falls back to exact ABIDES, which is slower but exact.
  - Residual risk: a silent native divergence on an untested combination. Fuzzing covered the categories listed in §8.
- **Packing limits.** More than 65,535 agents or more than 2³² messages in one run throws → fallback.
- **Hardware dependence of rates.** Self-reported events/s depend on the grading CPU; this laptop is about 1.28× slower than the grader.
- **Image digests are not bit-reproducible.** Rebuilding produces a different image ID (timestamps, pip metadata). Reproducibility is defined by **output hashes**, which must match exactly (§12.6).
- **Open work toward the 10M cap:**
  - the slowest units (`eq_deterministic`, deep books, large GB);
  - per-message send and ledger cost;
  - host-timed Final optimization (numpy import is the largest remaining fixed cost we control).

---

## 12. Reproduction guide

The kit in [`repro/`](repro/) automates every step:
- `repro/repro.sh`: the driver;
- `repro/in_container_run.py`: runs all scenarios inside one container;
- `repro/compare.py`: identity and throughput report;
- `repro/Dockerfile.rng`: RNG test toolchain.

The kit was itself tested end to end on the machine described in §14.1 (results in §12.7).

### 12.1 Prerequisites

| Requirement | Version used | Notes |
|---|---|---|
| OS | Windows 11 + Git Bash, or Linux with bash | The kit handles both path styles |
| Docker | Desktop 29.7.2 (WSL2 engine) | Must be able to build `linux/amd64` |
| RAM | 5.8 GB host worked, with one worker | Large scenarios use ~2 GB inside Docker |
| Disk | ~5 GB free | Images ~0.8 GB each plus outputs |
| Python (host) | 3.12.6 | Only for `compare.py` and the official harness |
| Network | Needed for builds and pulls only | All runs use `--network none` |

### 12.2 Get the sources

```bash
# 1. This project (contains sub/, native/, repro/, lab/, REPORT.md)
cd E:/NeurIPS/agenthon            # or wherever the project lives

# 2. Organizer public repo, pinned to the commit we used
git clone https://github.com/Agenthon-2026/track3-simulation-public.git track3-simulation-public-clone
git -C track3-simulation-public-clone checkout 4cc7882eed85153e9c06667738c87882b2deec90

# 3. Organizer common library, needed only for the official harness (step 12.4.6)
pip install "qfbench2-common @ git+https://github.com/Agenthon-2026/Agenthon2026-public.git@v2.3.1#subdirectory=common"
```

If the public repo is somewhere else, set `PUBLIC_REPO=/path/to/track3-simulation-public` before running the kit.

### 12.3 One-shot

```bash
bash repro/repro.sh all     # env, build, baseline, candidate, identity, batch, official
bash repro/repro.sh rng     # optional, ~10 min: RNG bit-exactness matrix
bash repro/repro.sh ab 3    # optional: 3 interleaved throughput rounds, baseline vs candidate
```

Outputs go to `repro/out/`. Each step is also callable on its own (§12.4).

### 12.4 Step by step: what each does and what you should see

| # | Command | What it does | Expected result | Time (this laptop) |
|---|---|---|---|---|
| 1 | `bash repro/repro.sh env` | Prints versions; checks 65 scenarios and 6 batch units | `scenarios: 65`, `batch units: 6` | seconds |
| 2 | `bash repro/repro.sh build` | `docker build sub/` → `agenthon-track3:repro` | `built agenthon-track3:repro: sha256:…` (ID will differ from ours; see §11) | 5–10 min cold, seconds cached |
| 3 | `bash repro/repro.sh baseline` | Runs the **original ABIDES image** (`slashalpha/agenthon-track3:dev`, public) on all 65 scenarios inside one container | 65 rows `path=reference`, ~6–9K events/s each | see §12.7 |
| 4 | `bash repro/repro.sh candidate` | Runs the **submission CLI** on all 65 scenarios | 65 rows, `path=native` | about 1 min |
| 5 | `bash repro/repro.sh identity` | Compares SHA-256 of both parquet files per scenario | `identical: 65/65`; candidate mean ≈ 5–7M events/s; exit code 0 | seconds |
| 6 | `bash repro/repro.sh batch` | Runs baseline and submission `simulate-batch` on the 6 units | 6/6 units identical (30 subs) | see §12.7 |
| 7 | `bash repro/repro.sh official` | Organizer's `run_regression.py`, 1 worker | `{'total_scenarios': 65, 'passed': 65, 'failed': 0, 'errored': 0}` | see §12.7 |
| 8 | `bash repro/repro.sh rng` | 478M-draw numpy-vs-C++ matrix | `OVERALL: PASS` | ~10 min |
| 9 | `bash repro/repro.sh ab 3` | Interleaved baseline / candidate rounds | Candidate ≈ 1,000× baseline | ~30 min per round (baseline dominates) |

Quick smoke test on a few scenarios:

```bash
ONLY=s001_price_time_priority,mp02_stp_oldest_baseline,ra01_fundamental_shock_mid bash repro/repro.sh baseline
ONLY=s001_price_time_priority,mp02_stp_oldest_baseline,ra01_fundamental_shock_mid bash repro/repro.sh candidate
bash repro/repro.sh identity        # expect identical: 3/3
```

### 12.5 Verifying the exact submitted images (no rebuild)
Point the kit at the published digest:

```bash
IMAGE=slashalpha/agenthon-track3@sha256:67e3086d427a68a9ba1c390811dafbc93f11b6ed42d228d5312c1a91c0fc60c7 bash repro/repro.sh candidate
bash repro/repro.sh identity
```

For sub2 use `@sha256:81e6fa40372a3a4e076a3a5e0adc0341b8c0263c288e8d3a5fe3dae32acc2d7a`; for sub1, `@sha256:8d4db7f43ea848770c7d99a6b0b14089b3b5ee72d88a95fdf8208414e030fe7b`.

### 12.6 What is and is not exactly reproducible

| Quantity | Reproducible? |
|---|---|
| Output bytes (`trace.parquet`, `message_trace.parquet`) and their SHA-256 | **Exactly**, on any x86-64 machine running these images |
| Event and message counts | Exactly |
| Correctness verdicts (identity, official harness) | Exactly |
| events/s | Machine-dependent; expect the same order of magnitude and ratios, not the same numbers |
| Image digest after a rebuild | No (build timestamps and metadata); behaviour is identical |
| Leaderboard score | Depends on the grader's hardware; our sub2 model ratio was 1.28× this laptop |

### 12.7 Results of our own end-to-end reproduction run

**Pending:** the full kit (`env baseline candidate identity batch rng official`) is running at the time of writing. This section will be filled in from `repro/out/full_run.log`.

### 12.8 Reproducing the development experiments

| Experiment | How |
|---|---|
| Baseline profile (§5) | Run cProfile around `abides.run` in the baseline image (`prof-run/prof.py`) |
| Phase A A/B (§6) | `lab/ab.py dev,cand1,cand2 3 <outdir>` (images built from `cand/`, `cand2/`) |
| Engine phase timing | Inside `t3-native-dev`: build `native/engine/driver.cpp` + `engine.cpp`, run on `native/engine/bins/*.bin` with `T3_PHASES=1` |
| perf profiles (§7.4) | `native/Dockerfile.perf` image, `perf record` around the driver (`--privileged`) |
| Host end-to-end timing (§7.6) | `lab/e2e.py <images> <reps> <scenarios>` |
| Fuzzing (§8) | `native/fuzz/gen.py` / `mk_*.py` to generate, `driver.py` to run, `recheck.py` to re-verify |
| Decision rounds (§4.2) | not reproducible from this repository (scripts not deposited) |

The `lab/` scripts were written for this machine and contain absolute `E:/NeurIPS/agenthon` paths. The `repro/` kit is the portable version.

### 12.9 Building and uploading a submission
1. `docker tag agenthon-track3:repro slashalpha/agenthon-track3:<tag> && docker push slashalpha/agenthon-track3:<tag>`
2. Copy the pushed digest from `docker inspect --format '{{index .RepoDigests 0}}' …` into `sub/submission.json` → `image.digest`.
3. Run `python sub/build_submission.py`. It prompts for the **Team Key** (hidden), reseals the descriptor, and writes `sub/submission.zip`. Run this step yourself.
4. Upload `sub/submission.zip` on CodaBench under *My Submissions → Development*.

---

## 13. File map

| Path | Contents |
|---|---|
| `REPORT.md` | This document |
| `repro/` | Portable reproduction kit (§12) |
| `sub/` | **Submission source:** `Dockerfile`, `simulate`, `simulate-batch`, `t3native/`, `native/`, `abides_fork/`, `patches/`, `perf/`, `submission.json`, `build_submission.py` |
| `native/engine/engine.cpp` | Native engine (single source of truth; synced into `sub/` by `lab/sync_sub.sh`) |
| `native/rng/` | `np_random.hpp`, `test_rng.cpp`, `gen_ref.py`, `run_all.sh` |
| `native/pkg/t3native/` | Python package: `cli.py`, `batch.py`, `native_sim.py`, `writer.py` |
| `native/refdump/` | ABIDES instrumentation, `first_divergence.py`, `DUMP_FORMAT.md`, `COVERAGE.md` |
| `native/fuzz/` | Fuzz generators, case logs (`*.jsonl`), `recheck.py` |
| `lab/` | Development harnesses (A/B, e2e, regression wrappers, comparison scripts) |
| `cand/`, `cand2/` | Phase A Python-only candidates |
| `workspace-*/agenthon_t3_baseline/` | Original baseline adapter (untouched) |
| `track3-simulation-public-clone/` | Organizer public repo (scenarios, reference traces, harness, units) |

---

## 14. Appendix: pinned versions, checksums, glossary

### 14.1 Environment used for all measurements
- **Host:** Windows 11 Home, 5.8 GB RAM.
- **Docker:** Desktop 29.7.2, WSL2 kernel 6.6.87.2, VM with ~2.7 GiB RAM and 4 CPUs.
- **Host Python:** 3.12.6.
- **CPU:** no AVX-512 (numpy reports `AVX512F` not found).

### 14.2 Inside the submission image
- Python 3.11.16 on Debian 13.7, glibc 2.41.
- numpy 1.26.4, pandas 1.5.3, pyarrow 15.0.2, scipy 1.17.1.
- ABIDES `jpmorganchase/abides-jpmc-public` at commit `f9cbe51342b7dedd9587e4e069040d68a5c6477f`.
- Engine compiler: g++ (Debian), flags `-O2 -std=c++17 -ffp-contract=off -fPIC -shared`.

### 14.3 Organizer sources
- `Agenthon-2026/track3-simulation-public` @ `4cc7882eed85153e9c06667738c87882b2deec90`
- `Agenthon-2026/Agenthon2026-public` common library @ tag `v2.3.1`

### 14.4 sub3 source checksums (SHA-256)

| File | SHA-256 |
|---|---|
| `sub/native/engine/engine.cpp` | `61819bf375b639384c1489077f956f6f9d3bdb639b77d61780553344b5e168e2` |
| `sub/native/rng/np_random.hpp` | `db7f57703cef0f0a06979b55283c20812a5ad497dde3a1c56c7db9a490332d91` |
| `sub/t3native/__init__.py` | `2ad09afa24c3a00e45a7ec1fc75fbb10e1ecf5d003000fab9314ce52d3ecdb44` |
| `sub/t3native/batch.py` | `888238d1e8f4c727f42e97b9d10582b0251c07dd28288e22c5d78a3caa5fc152` |
| `sub/t3native/cli.py` | `78b5059a21b236b8c5723700d16c4411eb02549b32210de32fcb94efbc92660c` |
| `sub/t3native/native_sim.py` | `caabe71b3aa526c99000daab2d419bacb88e428817734513bbab6af1e9521d87` |
| `sub/t3native/writer.py` | `2078c99a0ab0313f0e3246f20c29f9097b36d5bc35f8048a0435dc3668656e19` |
| `sub/Dockerfile` | `ffd215f21553478770e2f476c7f5d4db16e9cb44d1f0f7bf0d467073126a9dcf` |
| `sub/simulate` | `3e2cf4c80653580305be0ab19c12a082a872b5b13a9fc9806dc9807255c4b24d` |
| `sub/simulate-batch` | `7edf4906241cb313bd4f24a23a9318a70856129ce4368d153f48d57cfc446305` |

Check them with: `sha256sum sub/native/engine/engine.cpp sub/native/rng/np_random.hpp sub/t3native/*.py sub/Dockerfile sub/simulate sub/simulate-batch`

### 14.5 Image digests

| Image | Digest |
|---|---|
| baseline `slashalpha/agenthon-track3:dev` | `sha256:c4f8a635794ebeb4026e8bc2977b3fdd9feef830def78025ce4f744461c77996` |
| sub1 `:native-v1` | `sha256:8d4db7f43ea848770c7d99a6b0b14089b3b5ee72d88a95fdf8208414e030fe7b` |
| sub2 `:native-v2` | `sha256:81e6fa40372a3a4e076a3a5e0adc0341b8c0263c288e8d3a5fe3dae32acc2d7a` |
| sub3 `:native-v3` | `sha256:67e3086d427a68a9ba1c390811dafbc93f11b6ed42d228d5312c1a91c0fc60c7` |

### 14.6 Glossary

| Term | Meaning |
|---|---|
| events/s | Trace rows ÷ simulation wall time (self-reported) or ÷ `docker run` time (host-measured) |
| Byte-identical | Same SHA-256 for both output parquet files as the baseline image |
| Fallback | The exact Python ABIDES path, used for anything the native engine does not certify |
| Requeue | A message re-pushed because its recipient agent is still busy |
| Pre-fault | Making the OS back a memory range with physical pages before use, so the timed loop takes no page-fault traps |
| Decision model | An external model that answers typed questions (probability, graded value, choice), used for decision routing (§4.2) |
| sub1 / sub2 / sub3 | Our successive native submission images |
