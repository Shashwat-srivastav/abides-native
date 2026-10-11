### 9.9 sub16 on the host, sub17, sub18, sub19 and five more scores

This section records everything done from the upload of sub16 to the build of sub19. The record it is assembled from is `lab/agent_report/facts_sub16_19.md`. Where a result was not available when this was written, the text says "pending when this was written". Readings that were announced during the period and later proved wrong are kept and labelled as wrong (§9.9.8).

#### 9.9.1 Scores of the period

All five uploads are scratch images on Docker Hub `slashalpha/agenthon-track3`, and all were scored.

| Upload | Tag | Digest (sha256) | What it is | Score | Change |
|---|---|---|---|---:|---|
| 975649 | `native-v16m` | `96856191063e0cefe726d5c9a0d8bbea049ef52182e6a3308fe174aadfcdbd83` | sub16, memory switches off | **203,394.4709** | +7.6% against sub11m (189,018.28) |
| 976478 | `native-v17n` | `6d1a0d8fdfce8001fe4d7722009bfa9e7b54f15b458ff68bdb86a1290e03c192` | sub17, writer threads off | 196,164.8389 | −3.6% against sub16m |
| 976489 | `native-v17t` | `998c2f45c2eac81bb50c14679694a1ca090e43534d0c6bbce9f8b208bb81ecd8` | sub17, writer threads on (`T3_TRAIL=1`) | 199,285.2183 | +1.6% against sub17n |
| 976768 | `native-v16-helper-off` | `31cb73d3789e38dba5f47f6c6e91068ecd216f45656fa1dd4fc405bbf8788f5c` | sub16 binary, latency helper thread off (`T3_LAT_THREAD=0`) | 185,818.3472 | −8.6% against sub16m |
| 976794 | `native-v18-helper-off` | `b437b60816126789b60d9faa5c0c0a16b0fdd7d7e851d5b4711140ff5feaf6ce` | sub18 binary, helper thread off | 193,962.2805 | +4.4% against sub16 helper off |

- **Best score: 203,394.4709 (sub16m).** No later upload of the period beat it. The board keeps a team's best score.
- **Pushed, not uploaded when this was written:** `native-v19a`, `sha256:abca67f17b3558eedca6e44ec2e437ec5b9ff7ccb3121c4ad2c4879f53dcf434` (sub19a, §9.9.9).
- **Pushed, never uploaded:** `native-v18-helper-sleeping`, `sha256:2f9c4d39a04390cb7700dfc8730746efabe3cf9bbbe64c26846235fcfae38ea7` (sub18 with its sleeping helper on).
- **Arrival times.** Results arrived much faster than the 45 to 60 minutes of the earlier uploads. Upload 976478 read "Submitting" for a while after 976489, uploaded five minutes later, had finished; it then finished normally.
- **Upload budget.** The competition page allows 5 uploads per day and 23 per person in total (`max_submissions_per_day: 5`, `max_submissions_per_person: 23`, read from the public CodaBench competition API). The figure of 20 in §9.8.7 and §9.8.12 (E92) came from a toolkit document and is superseded. After 976794 the team had used 21 of 23: **two uploads remained.**
- **Board** (screenshot from the team, 50 teams): fuzz 231,024.2407; VerityLovityFalsityCruelty 222,058.1706; abc123 221,088.2954; IMAnonymous 215,963.1445; Yan Su 214,393.6369; "recently rejected" 211,718.1931; Proof of Alpha 211,712.3699; Cornfield Chase 210,201.3605; Warkop PuteraPrakoso 206,152.3034; **S2WISH 203,394.4709 (rank 10)**.

#### 9.9.2 Organizer statements found

All from the GitHub repository `Agenthon-2026/track3-simulation-public`. The statements are in issues. (We recorded here that the repository had no commit after `bffb572`. That was wrong: two documentation commits had been made, see §9.9.16.)

| Issue | Who | Statement | Consequence for us |
|---|---|---|---|
| #34 | PawPol | Track 3 Development "runs on a single machine that takes only Track 3 runs, and it's the same machine the Final is timed on"; it "runs one submission at a time, and that submission's units one after another" | The Development score is measured on the Final's machine. The "busy shared host" readings of §9.4 and §9.8.2 are not supported by this statement |
| #34 | SebastianBoehler (the issue's author) | "a fixed per-container cost of roughly half a second"; a simulator "well under 0.1 s" on most units; two runs agreeing "to within 0.1%" | A participant's report, not an organizer's. It is far tighter than the 1.6% once seen between our two sub4 uploads (§9.4) |
| #34 | PawPol | "please keep accepting the GPU device the card attaches: don't set `NVIDIA_VISIBLE_DEVICES` in your image" | We never set it |
| #35 | PawPol | The official runner mounts the unit's input folder at `/input` as a whole, so `/input/card.toml` is present; "writing the ledger everywhere is always safe"; batch units need a ledger for every sub-scenario whatever the card says; do not use `scenario_family` as a stand-in for the flag | Confirms the ledger skip of §9.8.3 as built: it reads the flag from `card.toml`, and `simulate-batch` never skips |
| #24 | PawPol | The Final rehearsal was postponed. The calibration post (minimal process and `t3-eq-deterministic-baseline`, timed both create-to-remove and StartedAt-to-FinishedAt) had not been published when this was written | The fixed per-container cost on the host stays unknown |
| #24 | krllx (comment) | "whether the main simulation thread shares a physical core with a helper thread moves a large unit's median window by about 6%" | krllx states in issue #36 that he is team fuzz, the leader. Thread placement matters on the host at the scale of our score steps |
| #2 | organizers | Final limits: 300 s per run, five runs per unit (a warm-up and four counted), 4 CPUs, 16 GiB, 24-hour allowance for the whole run | Final planning (§9.9.15) |
| #20 | | An upload reading "Submitting" well over an hour is usually held for a team-claim problem; a held upload still consumes an attempt | Explains what to watch for; 976478 was not such a case |

#### 9.9.3 Measurement corrections

The laptop is an AMD Ryzen 5 5500U with Docker Desktop on Windows; the Docker VM had 2.76 GiB in this period.

**The unit folders are a slow Windows mount.** A system-call trace of the smallest unit (`t3-s001-price-time-priority`, 604 events) showed:

| Call | Time |
|---|---:|
| First `openat` of `card.toml` | 9.65 ms |
| `openat` of `scenario.json` | 2.08 ms |
| Each `read` / `fstat` / `close` on those files | 0.2–1.0 ms |
| Everything after the inputs were read | under 4 ms |

- Every earlier "whole process" figure measured from the unit folders includes 10 to 20 ms per run that the scoring host does not have. That covers the `fig_*.json` files and the 3.5 to 3.9 s totals of §9.8.15.
- `lab/true_p.py` copies the inputs to `/dev/shm` first and then times the process.

**True process time, all 71 units (65 single and 6 batch), best of 5, inputs in memory:**

| Session | Build | Total (s) | File |
|---|---|---:|---|
| One session | sub16 | 1.895 | `lab/bench/truep_sub16.json` |
| | sub17, writer threads off | 1.627 | `truep_sub17n.json` |
| | sub17, writer threads on | 1.348 | `truep_sub17t.json` |
| Another session | sub9 | 1.838 | |
| | sub10 | 1.736 | |
| | sub11m | 1.982 | |
| | sub13m | 1.759 | |
| Later, slower session | sub16 | 2.228 | `truep_sub16_b.json` |
| | sub17n | 2.152 | `truep_sub17n_b.json` |
| | sub18 | 1.876 | `truep_sub18.json` |

sub16 measured 1.895 s in one session and 2.228 s in another. Only ratios within one session mean anything.

**Hardware counters are the stable instrument.** `perf stat -e cycles:u,instructions:u,branch-misses:u` with `T3_LAT_THREAD=0 T3_TRAIL=0` (one thread) in the dev container `t3dev`:

- `instructions:u` repeats to ±0.00%;
- `branch-misses:u` repeats to under 0.5%;
- `cycles:u` repeats to 0.5–2% on a quiet machine.

Every engine change of this period was judged by these counters first. They say what the simulation thread does; they say nothing about thread placement on the host, which §9.9.8 shows to be worth more than any engine change made here.

**Where the cycles go** on the largest unit, one thread (sub17 test build):

| Part | Share of cycles |
|---|---:|
| `Engine::run` with inlined handlers | 21.7% |
| Latency draws: `standard_normal` 11.5%, `exp` 5.1% + 2.3%, `log` 4.3%, `latency_from` 4.4% | about 27.5% |
| Output encoding and SHA-256 | about 20% |
| `sift_down` | 5.8% |
| `send` | 4.1% |
| `set_wakeup` | 3.7% |
| `handle_limit_order` | 3.6% |
| `close_bucket` | 2.6% |

**Event-loop counts** (scratch build with `-DT3_STATS`):

| Unit | Heap iterations | From the message heap | Mean message-heap size | Mean wakeup-heap size | Re-queued as blocked |
|---|---:|---:|---:|---:|---:|
| `t3-gb-mega-throughput` | 1,420,862 | 1,200,228 | 105.6 | 145.0 | 53,845 |
| `t3-mr-deep-book-state-size` | 269,644 | 265,339 | 43.7 | 12.0 | 115,505 |
| `t3-as06-throughput-fast` | 83,337 | 72,515 | 19.4 | 21.0 | 9,718 |

**Helper thread on the laptop** (simulation phase, ms, best of several):

| Unit | With the helper | Without |
|---|---:|---:|
| Largest unit | 211–220 | 257–298 |
| deep-book | 52–55 | 61–63 |
| pop-horizon-scale | 122–138 | 151–170 |

**Writer threads during the run on the laptop** (total process ms, best of 9; the two sub17 columns are the same binary):

| Unit | sub16 | sub17, `T3_TRAIL=0` | sub17, `T3_TRAIL=1` |
|---|---:|---:|---:|
| Largest unit | 228.8 | 198.3 | 175.7 |
| pop-horizon-scale | 134.3 | 114.9 | 113.4 |
| deep-book | 67.0 | 63.9 | 51.9 |
| cancel-replace-churn | 64.6 | 62.0 | 46.4 |
| mp05 | 45.7 | 44.5 | 34.1 |
| as06 | 19.9 | 18.7 | 13.9 |

**A run that was thrown away.** A "calibration" run of eight binary and helper combinations was discarded: the laptop was two to three times slower than in the earlier session, and the two rounds of one binary differed by up to 45%.

#### 9.9.4 sub16 on the host

sub16 was built (§9.8.15): the engine of sub15 (trace in final order during the run, `repair_trace` for out-of-order rows, agent fields regrouped, allocator settings) with sub11's writer (files built after the run, columns encoded on two to four threads, one write).

- **Validation** (`lab/bench/validate_sub16.log`): tables 65/65, repeat-run bytes 65/65, batch 6/6, fallback run, official regression 65/65. **Its fuzz replay crashed at 200 of 1,318** (Docker "unexpected EOF"). A separate replay on the same image, kept in `lab/bench/val_sub16/fuzz.log`, completed with 1,318 of 1,318 (1,296 launcher, 22 Python path); this section first said it had not been repeated (§9.9.16).
- **Scratch image** `sub16m`: binary identical to sub16, batch 6/6, official regression 65/65, no-ledger units 6/6 (`lab/bench/scratch_sub16m.log`).
- **Uploaded** as 975649. **Score 203,394.4709**, +7.6% over sub11m.
- **Reading.** sub16 differs from sub11 by the engine of sub14 and sub15: three post-run passes over the trace and their threads are gone. The laptop had shown 4–7% less process time for that step. The host paid far more.
- sub16 went up without a completed fuzz replay. sub17 and sub18, which contain its engine, replayed 1,318 of 1,318.

#### 9.9.5 sub17

sub17 = sub16 plus three things.

**1. A heap step without data-dependent branches.** `EventHeap::sift_down` picks the smallest of four children. In sub16 the choice was written as conditional expressions, and the compiler had turned them into branches. In sub17, when all four children exist, the choice is a tournament on index arithmetic: `b01 = c + (h[c+1].k < h[c].k)`, `b23 = c + 2 + (h[c+3].k < h[c+2].k)`, then a mask selects between `b01` and `b23`. A node with fewer than four children keeps the loop over `heap_less`. The comparison is the same total order on the same keys, so the heap pops the same sequence.

Counters, profile-guided builds, one thread (`T3_LAT_THREAD=0 T3_TRAIL=0`):

| Unit | Build | cycles:u | instructions:u | branch-misses:u |
|---|---|---:|---:|---:|
| `t3-gb-mega-throughput` (144 agents, 1,420,862 kernel events, 1,168,360 trace rows, no ledger written) | sub16 | 934–945 M | 1,395 M | 11.59 M |
| | sub17 | 787–863 M | 1,324 M | 4.93–5.12 M |
| `t3-mr-deep-book-state-size` (269,644 kernel events, 115,505 re-queued as blocked) | sub16 | 279–289 M | 420.6 M | 2.53 M |
| | sub17 | 255–275 M | 407.8 M | 1.64–1.67 M |
| `t3-as06-throughput-fast` | sub16 | 72.0 M | | 0.643 M |
| | sub17 | 66.6 M | | 0.412 M |

**Tried and dropped: a sentinel-padded heap** (every node always has four readable children). Instructions fell 2.0% on the largest unit (1,324.3 M → 1,296.0 M), but cycles stayed within noise and were slightly worse on one unit. It was reverted before sub17 was built.

**2. A changed start-up of the latency helper thread** (`Engine::Feed`).

- In sub16 the helper waits on a condition variable until the run starts, spins when its ring is full, and the event loop falls back to drawing inline for the whole run if the helper is late.
- In sub17 the helper starts producing at engine creation. The event loop no longer gives up on it for the whole run: it publishes its position every 64 draws and switches to the ring whenever the helper is ahead (`feed_mode` 0 inline, 1 inline while the helper catches up, 2 from the ring). The mutex and the condition variable were removed. The ring stayed at 2^13 values.
- **Why:** it was added "as a safeguard" against a late helper. There was no host evidence for it. §9.9.14 records this as a failure.
- The draws are produced by the same generator in the same order whichever side makes them, so the outputs do not change. Checked by byte comparison with the helper on and off (below).

**3. `T3_TRAIL` as a build argument and environment variable** in both Dockerfiles (`sub/Dockerfile`, `sub/Dockerfile.min`). The launcher's default stayed 0. This lets one validated binary ship with the writer threads of §9.8.10 on or off.

**Images.**

| Image | Kind | Settings |
|---|---|---|
| `agenthon-track3:sub17` | full | built with `T3_TRAIL=1`, so the long validation exercised the writer threads |
| `sub17n` | scratch | `T3_TRAIL=0`, `T3_HUGE=0`, `T3_PREFAULT=0` |
| `sub17t` | scratch | `T3_TRAIL=1`, `T3_HUGE=0`, `T3_PREFAULT=0` |

**Checks.**

- Before any image build: the candidate binary compared byte for byte with the sub16 binary on the 65 single units (`lab/cmp_bins.sh`), also with `T3_LAT_THREAD=0`; by tables on all 71 units where the writer mode differs (`lab/cmp_tables.py`).
- **Full validation** (`lab/bench/validate_sub17.log`, with the regression and replay output in `lab/bench/val_sub17/official.log` and `fuzz.log`): tables 65/65, repeat-run bytes 65/65, batch 6/6, fallback run, official regression 65/65, fuzz replay 1,318/1,318 (1,293 handled by the launcher, 25 handed to the Python path).
- **Scratch images:** both variants have a binary identical to sub17 and pass batch 6/6, official regression 65/65 and the six no-ledger units (`lab/bench/scratch_sub17n.log`, `scratch_sub17t.log`). Both ran correctly when pulled by digest.

**Laptop process time** (§9.9.3): sub16 1.895 s, sub17n 1.627 s, sub17t 1.348 s over the 71 units.

**On the host:** sub17n 196,164.8389 and sub17t 199,285.2183. Both are below sub16m's 203,394.4709. §9.9.8 gives what that established.

#### 9.9.6 Three agents and two decision rounds

Records of the three studies are under `lab/agent220/`. The agents' figures are estimates from reading code and our measurement files, not measurements.

**Decision round 6** (before sub17 was uploaded; 1,727 input and 207 output tokens).

| Question | Answer |
|---|---|
| Value of "upload sub17 with writer threads first" | 2.07 |
| Value of "engine change alone first" | 1.64 |
| Value of "helper disabled" | 0.50 |
| Value of "wait for per-unit data" | 1.01 |
| Which first | engine change alone first (0.44), or wait (0.41) |
| 200K reachable | 0.67 |
| 210K reachable | 0.44 |
| 230K reachable | 0.18 |
| Next work | the event queue (0.67) |

- **Used:** both sub17 variants were uploaded, the engine-only one (sub17n) first. The next engine work went to the event queue (sub18's wakeup rings and blocked queues).
- **What turned out wrong:** "helper disabled" was valued lowest (0.50). The upload with the helper disabled gave the cleanest single-variable measurement of the project (§9.9.8), although as a score it was the lowest of the day.

**Decision round 7** (before sub17n's score; 1,586 input and 227 output tokens).

| Question | Answer |
|---|---|
| Upload sub18 when validated, then start the high-risk restructuring | 0.74 |
| Attempt the restructuring | 0.34 |
| sub18 beats sub16 | 0.80 |
| 220K reachable | 0.55 |
| 230K reachable | 0.24 |
| Final candidate | the best-scoring build (0.69) |

- **Used:** the restructuring ("lazy passive receipts", below) was not attempted. No decision on the Final image had been taken when this was written.
- **What turned out wrong, or is untested:** sub18 with its own helper was never uploaded, so "sub18 beats sub16" has no host answer. With the helper off, sub18 beat sub16 (193,962 against 185,818).

**Score-model agent** (`lab/agent220/model/`).

- A model "fixed cost + k × laptop process time" cannot reproduce the ranking of our own builds: rms residual 3.2%, maximum 6.3%.
- The smallest structure that fits needs five parameters on six points: a memory-mode factor, a new-engine factor, and a penalty of 27–41 ms per unit for builds that write incrementally. A per-write cost is inconsistent by 9–16×.
- It predicted sub17n at 205–209K if that penalty were real, and at 189–194K if sub17's own changes cost time.
- From sub16's score, 220K needs host process time cut by 27% (fixed cost 0.36 s) to 46% (0.44 s); 230K needs 41% to 68%.
- **What turned out wrong:** sub17n scored 196,165, between the two predictions. The "penalty for incremental writing" reading was then contradicted by sub17t beating sub17n.
- **Used:** its first result, that laptop process time does not predict our own scores. It was not heeded at once: three projections from laptop timing were still given (§9.9.8).

**Open-source research agent** (`lab/agent220/osint/`).

- No public code from the leading teams.
- Two public engines by other teams (malik-redwood, jarnav07), with 4-ary heaps, static binaries and scratch images.
- jarnav07's notes say that NumPy 1.26's `np.log` on AVX-512 CPUs is Intel SVML and differs from libm on about 27% of inputs. This is relevant to our launcher's `log` for the log-normal location. Our scored runs pass on the host.
- The platform flags from the toolkit's DEVELOPMENT-RUNTIME document; `/output` is a bind mount of a host directory.
- **Used:** the issue threads it collected are the source of §9.9.2.

**Engine-review agent** (`lab/agent220/engine/review.md`; read-only, nothing compiled). It ranked nine changes.

| Change | Its estimate | State |
|---|---|---|
| Wakeup rings | 7–9% of simulation-thread time | In sub18 |
| Own-order bookkeeping only for market makers | about 3% | In sub18 |
| One-row trace buckets | 3–4% | In sub18 |
| No ledger record when the ledger is skipped | part of 4–6% | In sub18 |
| Blocked queue as a sorted vector | 0.6% on the largest unit, 6–7% on deep-book | In sub18 |
| Bottom-up pop | | Not implemented |
| Noise-trader draws on the helper thread | | Not implemented |
| Prefetching | | Not implemented |
| "Lazy passive receipts" (order receipts handled outside the event queue) | 20–28% more; 12–20 hours; high risk | Not implemented |

Its count: receipts are 37.6% of the largest unit's events and 47.7% of deep-book's.

#### 9.9.7 sub18

sub18 = sub17 plus seven changes. The binary was compared byte for byte with the sub16 binary on the 65 single units, with the helper on and off, before any image was built (§9.9.11).

Counter figures below are from non-profile-guided test builds on the largest unit, one thread, in the order the changes were made. The starting point is the sub17 engine: 1,491.7 M instructions, 830–850 M cycles.

| # | Change | Why the output is unchanged | Measured effect |
|---|---|---|---|
| 1 | 32-byte trace row: `OrderRow` stores size and order id in 32 bits | `row_fits` checks every value before it is stored. A value that does not fit stops the run, which sends the scenario to the fallback path. A row that is written holds the same values as before | Instructions 1,491.7 M → 1,470.2 M; cycles 797–805 M; page faults 14,654 → 12,354; cache misses 2.6–2.8 M → 2.05–2.14 M |
| 2 | Own-order bookkeeping (`OwnOrders`) only for market makers | Its only reader is `cancel_all_orders`, which is reached only from the market-maker case. For every other agent the structure was written and never read | With 3 and 4: instructions → 1,429.0 M; branch misses 5.12 M → 4.71 M |
| 3 | Fast path for a trace bucket of one order row and no quote (`bk_slow`) | Such a bucket is already in its final order: there is nothing to sort and no quote row to place. `close_bucket` runs only when a second row or a quote has set `bk_slow` | Counted with 2 and 4 |
| 4 | No delivery record at all when the ledger is skipped | Since sub10 those records went to one scratch record that nothing read (§9.8.3). Not writing it changes no output | Counted with 2 and 3 |
| 5 | Wakeups kept in up to four per-interval rings, with the wakeup heap as catch-all; a wakeup has no slot in the message pool (`WakeRing`, `wake_setup`, `wake_refresh`, `wake_pop`) | A ring takes a key only if it is greater than the ring's last one; any other key goes to the heap. Every container is sorted and keys are unique, so the earliest wakeup is the smallest of the ring heads and the heap top: the same order as one heap | With 6: instructions → 1,381.5 M; branch misses → 4.35 M; cycles 733 M (750 M just before). On `t3-mr-deep-book-state-size`: cycles 264.6 M → 237.8 M, branch misses 1.77 M → 1.58 M |
| 6 | Blocked queues as sorted vectors with a read position (`BQueue`) instead of binary heaps | All blocked events of one agent share one time and are ordered by key alone. A vector kept in ascending key order gives the same minimum as a heap on that key. An out-of-order key is inserted at its place by binary search | Counted with 5 |
| 7 | The latency helper sleeps on a futex while its ring is full and is woken by the event loop when half the ring is used; ring enlarged from 2^13 to 2^15 values (`Feed::CAP`) | The helper produces the same draws in the same order; only when it produces them changes | Timing experiment below |

**The helper ring-size experiment.** Sleeping helper against spinning helper, 13 to 15 interleaved runs, simulation phase in ms, minimum / median:

| Unit | Spinning (ring 2^13) | Sleeping, ring 2^13 | Sleeping, ring 2^15 | Sleeping, ring 2^16 |
|---|---:|---:|---:|---:|
| horizon-240s | 104.3 / 118.4 | 115.6 / 125.8 | 99.1 / 105.8 | 95.4 / 101.5 |
| Largest unit | 226.8 / 262.6 | | 221.0 / 246.2 | |
| deep-book | 60.4 / 65.7 | | 61.0 / 66.2 | |

A sleeping helper with the old ring is slower than a spinning one. With a ring of 2^15 it is not. Ring 2^15 was chosen. This is laptop timing of a thread interaction, which §9.8.5 says is not evidence about the host.

**Validation** (`lab/bench/validate_sub18.log`): tables 65/65, repeat-run bytes 65/65, batch 6/6, fallback run, official regression 65/65, fuzz replay 1,318/1,318 (1,291 handled by the launcher, 27 handed to the Python path; §9.9.10 is about that 27).

**Scratch variants:**

| Image | Setting | Checks | Log |
|---|---|---|---|
| `sub18n` | helper sleeping | binary identical to sub18, batch 6/6, official regression 65/65, no-ledger units 6/6 | `lab/bench/scratch_sub18n.log` |
| `sub18h0` | `T3_LAT_THREAD=0` | the same | `lab/bench/scratch_sub18h0.log` |

`sub18n` was pushed as `native-v18-helper-sleeping` and not uploaded. `sub18h0` was uploaded as `native-v18-helper-off`.

**An earlier image also tagged sub18** held the 32-byte rows only. It was validated and then replaced; its log is `lab/bench/validate_sub18_rows_only.log` (fuzz replay 1,318/1,318; 1,293 and 25).

**Laptop process time** in the later, slower session (§9.9.3): sub16 2.228 s, sub17n 2.152 s, sub18 1.876 s.

#### 9.9.8 The sequence of host results and what each established

In the order the results were read. Each wrong reading is kept, labelled **Wrong**.

**1. sub16m: 203,394.** +7.6% over sub11m. Building the trace in order during the run paid far more than the laptop's 4–7% suggested.

- **Wrong:** a first projection for sub17 from laptop process times: 197–205K. Then, after a refit to 203,394: 205–209K for sub17n and 209–219K for sub17t. Actual: 196,165 and 199,285. All three projections were wrong. The score-model agent had already shown that such a model does not fit (§9.9.6).

**2. sub17t: 199,285 (uploaded after 976478, finished before it).**

- **Wrong:** "writer threads lose on the host", announced on this one score. The comparison score had not arrived. It was corrected about an hour later.

**3. sub17n: 196,165.** The comparison build scored lower still.

- sub17n → sub17t: +1.6%. Writer threads during the run were a small gain on this binary, not a loss. This contradicts the reading of sub13 as "a streaming writer loses" (§9.8.15).
- sub16m → sub17n: −3.6%, although the laptop counters and process time both had sub17 ahead.
- **Wrong:** "adding or strengthening a thread loses; removing threads wins", a pattern read from nine score steps. One counterexample was dismissed. On this pattern a 60/40 bet was made that sub16 with the helper off would score above 203,394.

**4. sub16 with the helper off: 185,818.**

- sub16m → sub16 helper off: −8.6%. Same binary, one environment variable (`lab/bench/Dockerfile.nohelper` adds `ENV T3_LAT_THREAD=0` to the scratch image without adding a layer). **The helper thread is worth +9.5% on the host.** This is the cleanest single-variable measurement of the project.
- The 60/40 bet lost. The "threads lose" pattern is refuted for the helper thread.
- **Not established:** the arithmetic 185,818 × 1.056 = 196,222 is close to sub17n's 196,165 and suggested that sub17's helper was not working at all on the host. The next result neither proved nor disproved that.

**5. sub18 with the helper off: 193,962.**

- sub16 helper off → sub18 helper off: +4.4%. sub18's engine (the branch-free heap step plus the cuts of §9.9.7) is better on the host at equal helper setting.
- It showed only that the engine is better. It did not show whether sub17's helper works on the host.

**Summary of what the five scores established:**

| Comparison | Host result | Reading |
|---|---|---|
| sub11m 189,018 → sub16m 203,394 | +7.6% | Three post-run passes and their threads removed; worth far more than the laptop said |
| sub16m 203,394 → sub16 helper off 185,818 | −8.6% (the helper is worth +9.5%) | The helper thread helps on the host |
| sub16 helper off 185,818 → sub18 helper off 193,962 | +4.4% | sub18's engine is better at equal helper setting |
| sub16m 203,394 → sub17n 196,165 | −3.6% | sub17's engine is better (previous row implies it for sub18, which contains it), yet sub17n scored lower. By elimination the cause is the changed helper start-up of sub17. **Mechanism not established** |
| sub17n 196,165 → sub17t 199,285 | +1.6% | Writer threads during the run are a small gain on this binary |

**A guess about the mechanism, untested.** A thread that runs from engine creation is placed by the scheduler's fork-time balancing, possibly far from the simulation thread, even on the other socket. A thread woken by the simulation thread at run start is placed near it. The krllx comment of §9.9.2 (about 6% from core sharing) shows placement effects of this size exist on the host. Nothing we measured confirms the guess.

**What follows.** The best engine (sub18) and the best helper behaviour (sub16) have not yet been scored together. sub19 is that combination.

#### 9.9.9 sub19a and sub19b

- **What:** sub18's engine with sub16's helper code restored verbatim: started through a condition variable when the run begins, spinning when the ring is full, ring of 2^13 values, permanent inline fallback if the helper is late.
- **sub19a** keeps the branch-free heap step. **sub19b** restores the branching one.
- **Why:** sub16's helper start-up is the only one with a good host score. sub18's engine is the only one shown better on the host at equal helper setting. sub19b exists because the heap step has not been scored separately from the other engine changes.
- **Sources:** `lab/bench/engine_sub19a.cpp`, `lab/bench/engine_sub19b.cpp`.
- **Checked so far, both:** byte-identical to sub16's output on 65/65 single units in the dev container.
- **sub19a full validation** (`lab/bench/validate_sub19a.log`): tables 65/65, repeat-run bytes 65/65, batch 6/6, fallback run, official regression 65/65, fuzz replay 1,318 of 1,318 (1,296 through the launcher, 22 handed to the Python path).
- **sub19a scratch image** (`sub19am`, `lab/scratch_checks.sh`): binary identical to the one in the validated image, batch 6/6, official regression 65/65, no-ledger units 6/6. Pulled back by digest, it wrote the correct files on three units under the runtime restrictions.
- **Pushed** as `native-v19a`, `sha256:abca67f17b3558eedca6e44ec2e437ec5b9ff7ccb3121c4ad2c4879f53dcf434`. Not uploaded when this was written.
- **sub19a scratch image checks, push, upload:** not done when this was written.
- **sub19b:** full validation not run when this was written.
- **Host score:** sub19a 199,057.7311 (§9.9.16); sub19b never uploaded.

#### 9.9.10 The fuzz-replay breakdown varies between runs, and a fix that has not shipped

**The finding.** The number of cases handed to the Python path is not the same in every run of the same corpus:

| Run | Handled by the launcher | Handed to the Python path |
|---|---:|---:|
| Launcher-only pass, sub16, sub17 and sub18 (identical) | | 23 |
| Full replay, sub17 | 1,293 | 25 |
| Full replay, first sub18 (32-byte rows only) | 1,293 | 25 |
| Full replay, sub18 | 1,291 | 27 |

- The 23 of the launcher-only pass, by reason (`native/fuzz/decline_reasons.py`): 19 "protocol_enforcement is not a bool", 4 "latency rounding sensitive to the log implementation".
- **Explanation, not confirmed by a targeted test:** the helper thread draws latencies ahead of the event loop. A draw that the run never uses can still set the global "sensitive" flag. A larger ring (sub18: 2^15) looks further ahead.
- **Consequence.** In the full image the affected case falls back and passes. In a scratch image it would exit with status 127 and the unit would score zero.
- **No public unit is affected:** all 71 are handled by the launcher in every run made.

**The fix, in the source only** (`native/engine/engine.cpp`; snapshot `lab/bench/engine_sub19_wip.cpp`):

- `latency_from` reports sensitivity to its caller instead of setting the flag itself.
- The helper records the index of its first sensitive draw.
- After the run the flag is raised only if that index is below the number of draws the run consumed.

State: byte-identical on 65/65 units with the helper on and off. **Not in any image. Not fuzz-replayed.**

sub19a and sub19b use sub16's helper code and so have sub16's look-ahead behaviour (ring 2^13), not the fix.

**Source state when this was written.** `native/engine/engine.cpp` is sub18 plus this fix. Snapshots in `lab/bench/`: `engine_sub17.cpp`, `engine_sub18.cpp`, `engine_sub18_pre_park.cpp`, `engine_sub18_park.cpp`, `engine_sub18_low.cpp`, `engine_sub18b.cpp`, `engine_sub19_wip.cpp`, `engine_sub19a.cpp`, `engine_sub19b.cpp`, `launcher_sub17.cpp`, `launcher_sub18.cpp`.

#### 9.9.11 Tools written

| Tool | Purpose |
|---|---|
| `lab/true_p.py` | Process time of every unit with the inputs copied to `/dev/shm` first (§9.9.3) |
| `lab/cmp_bins.sh` | Byte comparison of a candidate binary's output with the sub16 binary's on the 65 single units, also with `T3_LAT_THREAD=0` |
| `lab/cmp_tables.py` | Table comparison on all 71 units, for builds whose writer mode differs |
| `lab/build_pgo_dev.sh` | Profile-guided build inside the dev container |
| `lab/validate_rest.sh`, `lab/build_validate.sh`, `lab/build_variant.sh` | Build an image and run the validation stages; build a scratch variant of a validated binary |
| `lab/bench/Dockerfile.nohelper` | Adds `ENV T3_LAT_THREAD=0` to a scratch image without adding a layer |
| Dev container `t3dev` (image `t3-native-perf`) | `/native`, `/units`, `/lab`, `/sub` mounted; `perf` available |

**Exactness method of this period.** Every candidate binary is compared byte for byte with the sub16 binary on the 65 single units, with `T3_LAT_THREAD=0` as well, and by tables on all 71 units when the writer mode differs, before any image is built.

#### 9.9.12 Experiments of this section

| # | Experiment | Result | Decision |
|---|---|---|---|
| E105 | sub16m on the host | 203,394.4709 (+7.6% against sub11m) | Best score; base for everything after |
| E106 | System-call trace of the smallest unit | 9.65 ms in the first `openat` of `card.toml`; under 4 ms after the inputs were read | Time with inputs in memory (`lab/true_p.py`) |
| E107 | True process time, 71 units, best of 5 | sub16 1.895 s; sub17n 1.627 s; sub17t 1.348 s; another session sub16 2.228 s | Compare only within one session |
| E108 | Repeatability of hardware counters, one thread | instructions ±0.00%; branch misses under 0.5%; cycles 0.5–2% | Counters are the local instrument |
| E109 | Branch-free `sift_down`, largest unit | Branch misses 11.59 M → 4.93–5.12 M; instructions 1,395 M → 1,324 M | Keep (sub17) |
| E110 | Sentinel-padded heap | Instructions −2.0%; cycles within noise, slightly worse on one unit | Reverted |
| E111 | Cycle shares and event-loop counts (`-DT3_STATS`) | Latency draws about 27.5%; `Engine::run` 21.7%; output about 20% | Recorded; decision round 6 then named the event queue as next work |
| E112 | Helper thread on against off, laptop | Largest unit 211–220 against 257–298 ms | Helper helps on the laptop |
| E113 | Writer threads on against off, same binary, laptop, best of 9 | Largest unit 198.3 → 175.7 ms; as06 18.7 → 13.9 ms | Ship both variants of sub17 |
| E114 | Decision round 6 | Engine change alone first 0.44; wait 0.41; next work the event queue 0.67 | sub17n uploaded first, sub17t five minutes later |
| E115 | sub17 full validation and two scratch variants | All stages pass; fuzz 1,318/1,318 (1,293 / 25) | Push both |
| E116 | sub17t on the host | 199,285.2183 | Read wrongly at first (§9.9.8) |
| E117 | sub17n on the host | 196,164.8389 (−3.6% against sub16m) | sub17's helper start-up is suspect |
| E118 | Score-model agent | Linear model: rms residual 3.2%, max 6.3%; five parameters needed for six points | Laptop process time does not predict the score |
| E119 | Open-source research agent | No public code from the leaders; organizer statements collected | §9.9.2 |
| E120 | Engine-review agent | Nine ranked changes | Five implemented in sub18 |
| E121 | Decision round 7 | Upload sub18 then restructure 0.74; attempt restructuring 0.34 | Restructuring not attempted |
| E122 | 32-byte trace rows | Instructions 1,491.7 M → 1,470.2 M; page faults 14,654 → 12,354 | Keep; validated alone first (`validate_sub18_rows_only.log`) |
| E123 | Own orders for market makers only; one-row buckets; no skipped-ledger record | Instructions → 1,429.0 M; branch misses 5.12 M → 4.71 M | Keep |
| E124 | Wakeup rings and sorted blocked queues | Instructions → 1,381.5 M; branch misses 4.35 M; deep-book cycles 264.6 M → 237.8 M | Keep |
| E125 | Sleeping helper, ring 2^13, 2^15, 2^16 | 2^13 slower than spinning; 2^15 and 2^16 not | Ring 2^15 |
| E126 | sub18 full validation and two scratch variants | All stages pass; fuzz 1,318/1,318 (1,291 / 27) | Push both variants; upload one |
| E127 | sub16 binary with the helper off, on the host | 185,818.3472 (−8.6%) | The helper is worth +9.5% on the host |
| E128 | sub18 binary with the helper off, on the host | 193,962.2805 (+4.4% against E127) | sub18's engine is better on the host |
| E129 | Upload limits read from the CodaBench competition API | 5 per day, 23 per person | 22 used after sub19a; one remains |
| E130 | "Calibration" run of eight binary and helper combinations | Laptop 2–3 times slower than in the earlier session; rounds differ by up to 45% | Thrown away |
| E131 | sub19a and sub19b: sub18's engine with sub16's helper | Both byte-identical to sub16 on 65/65; sub19a passed the full validation (fuzz 1,318 of 1,318) and the scratch checks | sub19a pushed as `native-v19a` and scored 199,057.7311 (E134). sub19b passed the full validation; not pushed |
| E132 | Launcher-only fuzz pass on sub16, sub17, sub18 | 23 declined in each (19 + 4), against 25 and 27 in full replays | Explanation proposed, not confirmed |
| E133 | Sensitivity flag raised only for consumed draws | Byte-identical 65/65, helper on and off | In the source only; not fuzz-replayed |

#### 9.9.13 Hypotheses of this section

| ID | Hypothesis | Test | Outcome |
|---|---|---|---|
| H63 | Building the trace in order during the run removes real work (from §9.8.13) | E105 | **Confirmed on the host** (+7.6%) |
| H68 | Writer threads during the run are a net gain (from §9.8.15) | E116, E117 | **Supported on the host for sub17** (+1.6%, one pair of scores) |
| H69 | Laptop whole-process times from the unit folders measure the process | E106 | **Refuted**: 10–20 ms per run is the input mount |
| H70 | "Fixed cost + k × laptop process time" predicts the host score | E118, E116, E117 | **Refuted** |
| H71 | sub17 scores above sub16 (projections 197–205K, then 205–209K and 209–219K) | E116, E117 | **Refuted** (196,165 and 199,285) |
| H72 | Writer threads lose on the host | E116 alone | **Wrong**; withdrawn after E117 |
| H73 | Adding or strengthening a thread loses on the host; removing threads wins | E127 | **Refuted** for the helper thread |
| H74 | sub16 with the helper off scores above 203,394 (held at 60/40) | E127 | **Refuted** (185,818) |
| H75 | The latency helper thread helps on the host | E127 | **Confirmed** (+9.5%) |
| H76 | sub18's engine is faster on the host than sub16's at equal helper setting | E128 | **Confirmed** (+4.4%) |
| H77 | The branch-free heap step is a gain on the host | E128 (bundled with the other engine changes) | **Open**: not scored alone; sub19a against sub19b would test it |
| H78 | sub17's helper does not work at all on the host | 185,818 × 1.056 = 196,222 against 196,165 | **Open**: neither proved nor disproved by E128 |
| H79 | sub17n lost because a helper started at engine creation is placed far from the simulation thread | none | **Untested guess** |
| H80 | The 25 and 27 declined fuzz cases come from helper look-ahead setting the "sensitive" flag on unused draws | E132 | **Plausible; not confirmed by a targeted test** |
| H81 | sub18's engine with sub16's helper beats 203,394 | sub19a upload | **Refuted**: sub19a scored 199,057.7311 (§9.9.16) |
| H65 | 210,000 is reachable by the Development deadline (from §9.8.13) | Decision round 6: 0.44 | **Open** |
| H82 | 220,000 is reachable | Decision round 7: 0.55; score-model agent: host process time must fall 27–46% | **Open** |
| H83 | A streaming writer loses on the host (the reading of sub13 in §9.8.15) | E116, E117 | **Contradicted**: writer threads during the run gained 1.6% on sub17 |
| H53 | 240,000 is reachable by the Development deadline | | **Open; very doubtful** |

#### 9.9.14 Failures

| Failure | Cause | Consequence |
|---|---|---|
| sub17 bundled a speculative helper change with a measured optimisation | The helper change was added "as a safeguard" with no host evidence | sub17n scored 3.6% below sub16; two uploads spent before the cause was isolated |
| Three score projections given from laptop timing, all wrong | The model had been shown not to fit | The team planned around numbers that meant nothing |
| "Writer threads lose" announced after one score | The comparison score had not arrived | Corrected an hour later |
| A pattern read from nine scores ("threads lose") used for a 60/40 bet | One counterexample was dismissed | 185,818; one upload |
| A background validation was believed killed by a tool timeout and restarted | It was still running | Two validations ran at once; a log line was removed by hand from a file the first was still writing |
| A detached build "started" from PowerShell never ran | Not checked for 10 minutes | Reported as running when it was not; corrected |
| A finished log from the previous image was read as the new result | Same file name; the new build had not reached that stage | Caught by the identical timing figures; file renamed |
| First per-thread profile attributed the helper's samples to the simulation thread | Thread chosen by sample count, not by id | Redone |
| Laptop "whole process" figures since sub4 included the slow input mount | Never traced | 10–20 ms per run of noise in every earlier comparison |
| Upload budget believed to be 20 in total | Read from a toolkit document; the competition page says 23 | Corrected |
| Per-unit host results were never obtained | Needs the team's login; asked several times, not done | Fixed cost per container still unknown |

Two further points belong with these. sub16's validation log ends with its fuzz replay crashed at 200 of 1,318; the completed replay is in a separate file and was overlooked when this section was first written (§9.9.16). And the second failure repeats the first failure of §9.8.14: a proxy was trusted after it had been shown not to predict the host.

#### 9.9.15 Open when this was written

- **sub19a:** uploaded and scored after this list was written (§9.9.16). **sub19b:** validated, not uploaded.
- **Uploads:** two of 23 remain.
- **The fixed per-container cost on the host** is still unknown. It is bounded above by 0.471 s from the leader's score (§9.8.7). The organizers' calibration post had not appeared.
- **Why a helper thread started at engine creation is worth less on the host than one woken at run start:** not established.
- **Whether the branch-free heap step is a gain on the host by itself:** not scored separately.
- **The fix of §9.9.10** is in no image and has not been fuzz-replayed.
- **The Final:** one submission, the same host, sealed units, five runs per unit. Undecided: a scratch image, in which a declined scenario scores zero, or the full image with the exact Python fallback.

#### 9.9.16 After this section was written: sub19a's score and four corrections

**sub19a scored 199,057.7311** (upload 977400), the 22nd of 23 uploads. One upload remains.

| Engine | Helper off | Helper on | Helper worth |
|---|---:|---:|---:|
| sub16 | 185,818.35 | 203,394.47 | +9.5% (same binary) |
| sub18 | 193,962.28 | 199,057.73 (sub19a, sub16's helper code) | +2.6% |

- The engine gain (+4.4% with the helper off) and the helper gain (+9.5% on sub16's engine) did not add up: sub19a is 2.1% below sub16. Had both held, the arithmetic gives 212,309; that is a product of two ratios, not a score.
- sub19a is within 0.1% of sub17 with writer threads on (199,285.22) although it carries sub16's helper start-up. The reading of §9.9.8 that sub17 lost because of its changed helper start-up is therefore weakened: restoring the old start-up did not restore the old score. H81 is refuted.
- A guess, untested: once the event loop is fast enough it finds the helper behind at the start of the run, and in sub16's helper code the loop then draws its own latencies for the whole run (`feed_mode = 0`, "the helper is not keeping up: stay inline for the whole run"). A faster engine would then forfeit most of the helper's benefit. No measurement separates this from other explanations.

**Corrections to the record above.**

1. **sub16's fuzz replay was completed.** `lab/bench/validate_sub16.log` ends with the replay crashed at 200 of 1,318. `lab/bench/val_sub16/fuzz.log`, written later by a separate replay on the image tagged `sub16`, holds a complete one: 1,318 of 1,318, 1,296 through the launcher, 22 handed to the Python path. The image under that tag was created once and not rebuilt; no digest was recorded with the log. The statements in §9.9.4, §9.9.14 and §11 that the replay was not repeated were wrong.
2. **sub19b was validated.** `lab/bench/validate_sub19b.log`: tables 65/65, repeat-run bytes 65/65, batch 6/6, official regression 65/65, fuzz 1,318 of 1,318 (1,296/22), in its full image. No scratch image of it was built.
3. **The organizers' repository did have later commits.** `160f86e` and `1d7e994` change documentation only. With the answers in `Agenthon-2026/Agenthon2026-public` issues #2 and #9 they say: the Final takes one upload per team at any time in a window of about two weeks after Development closes; the code may change during that window; a Final upload that ends as failed does not use the attempt; ties go to the earlier upload; outputs, logs and the Final board are hidden. This record had treated the Final as a single submission immediately after Development. The hub repository's issues had not been read; only the Track 3 repository's had.
4. **The declined-case count on one build is not one number.** Three launcher-only passes over the stored cases on the sub19a image declined 23 each (19 with a non-boolean `protocol_enforcement`, 4 with a latency draw sensitive to the `log` implementation); the full replay on the same image handed 22 to the Python path. The launcher-only tool starts the launcher with an emptied environment, so the image's settings are not applied in it; whether that or the helper's look-ahead (§9.9.10) explains the one case was not traced.

**Consequence for the Final.** After the last Development runs there is no host timing. Anything changed after that ships unmeasured, and the Final compares `trace.parquet` byte for byte across five repeats of each unit, so a hand-over decision that depends on thread timing (§9.9.10) matters more there than in Development.

**The last upload, prepared and not made when this was written.** `sub16t`: the sub16 scratch image with `T3_TRAIL=1` added as an environment setting (`lab/bench/Dockerfile.trail`). Binary identical to sub16's; batch 6/6; official regression 65/65; no-ledger units 6/6; output bytes identical across three runs on the 65 single units (`lab/bench/scratch_sub16t.log`). With the setting on, the files differ in bytes from sub16's own output with it off (same tables, different page layout). Evidence for a gain: the sub17 pair only (+1.6%). No fuzz replay was run with the setting on this binary.

| # | Experiment | Result | Decision |
|---|---|---|---|
| E134 | sub19a uploaded (977400) | 199,057.7311, −2.1% against sub16, +2.6% against sub18 with the helper off | sub16 stays the best build; H81 refuted |
| E135 | Launcher-only pass over the stored fuzz cases on sub19a, three times | 23 declined each time (19 + 4); full replay 22 | One case unexplained |
| E136 | sub16 binary with `T3_TRAIL=1`: scratch checks and three repeat runs | All passed; bytes stable across runs, different from the setting off | Candidate for the last upload |
