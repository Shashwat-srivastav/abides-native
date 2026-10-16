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
- **Upload budget.** The competition page allows 5 uploads per day and 23 per person in total (`max_submissions_per_day: 5`, `max_submissions_per_person: 23`, read from the public CodaBench competition API). The figure of 20 in §9.8.7 and §9.8.12 (E92) came from a toolkit document and is superseded. After 976794 the team had used 21 of 23: **two uploads remained.** (Both were used later, by sub19a and sub16t: §9.9.16, §9.10.1.)
- **Board** (screenshot from the team, 50 teams): fuzz 231,024.2407; VerityLovityFalsityCruelty 222,058.1706; abc123 221,088.2954; IMAnonymous 215,963.1445; Yan Su 214,393.6369; "recently rejected" 211,718.1931; Proof of Alpha 211,712.3699; Cornfield Chase 210,201.3605; Warkop PuteraPrakoso 206,152.3034; **S2WISH 203,394.4709 (rank 10)**.

#### 9.9.2 Organizer statements found

All from the GitHub repository `Agenthon-2026/track3-simulation-public`. The statements are in issues. (We recorded here that the repository had no commit after `bffb572`. That was wrong: two documentation commits had been made, see §9.9.16.)

| Issue | Who | Statement | Consequence for us |
|---|---|---|---|
| #34 | PawPol | Track 3 Development "runs on a single machine that takes only Track 3 runs, and it's the same machine the Final is timed on"; it "runs one submission at a time, and that submission's units one after another" | The Development score is measured on the Final's machine. The "busy shared host" readings of §9.4 and §9.8.2 are not supported by this statement |
| #34 | SebastianBoehler (the issue's author) | "a fixed per-container cost of roughly half a second"; a simulator "well under 0.1 s" on most units; two runs agreeing "to within 0.1%" | A participant's report, not an organizer's. It is far tighter than the 1.6% once seen between our two sub4 uploads (§9.4) |
| #34 | PawPol | "please keep accepting the GPU device the card attaches: don't set `NVIDIA_VISIBLE_DEVICES` in your image" | We never set it |
| #35 | PawPol | The official runner mounts the unit's input folder at `/input` as a whole, so `/input/card.toml` is present; "writing the ledger everywhere is always safe"; batch units need a ledger for every sub-scenario whatever the card says; do not use `scenario_family` as a stand-in for the flag | Confirms the ledger skip of §9.8.3 as built: it reads the flag from `card.toml`, and `simulate-batch` never skips |
| #24 | PawPol | The Final rehearsal was postponed. The calibration post (minimal process and `t3-eq-deterministic-baseline`, timed both create-to-remove and StartedAt-to-FinishedAt) had not been published when this was written; it appeared during the Final (§9.10.2) | The fixed per-container cost on the host stays unknown (later published, §9.10.2) |
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

Every engine change of this period was judged by these counters first. They say what the simulation thread does; they say nothing about thread placement on the host, which another team reports to be worth about 6% on a large unit (§9.9.2) and which our own single uploads could not measure (§9.9.8).

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
- **Uploaded** as 975649. **Score 203,394.4709**, +7.6% over sub11m (one upload per side).
- **Reading.** sub16 differs from sub11 by the engine of sub14 and sub15: three post-run passes over the trace and their threads are gone. The laptop had shown 4–7% less process time for that step. The host score rose by more than that; with one upload per side, and identical images reported up to 14% apart (§9.10.2), how much of the +7.6% is the change is not known.
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

**On the host:** sub17n 196,164.8389 and sub17t 199,285.2183. Both are below sub16m's 203,394.4709. §9.9.8 gives what that does and does not establish.

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
- **What turned out wrong, or is not established:** "helper disabled" was valued lowest (0.50). The upload with the helper disabled became the project's only comparison of one binary with one setting changed (§9.9.8), although as a score it was the lowest of the period; with one upload per side, its difference is within the reported noise and not established.

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
- **What turned out wrong, or is untested:** sub18 with its own helper was never uploaded, so "sub18 beats sub16" has no host answer. With the helper off, sub18 scored above sub16 (193,962 against 185,818, +4.4%): one upload per side; within the reported noise; not established.

**Score-model agent** (`lab/agent220/model/`).

- A model "fixed cost + k × laptop process time" cannot reproduce the ranking of our own builds: rms residual 3.2%, maximum 6.3%.
- The smallest structure that fits needs five parameters on six points: a memory-mode factor, a new-engine factor, and a penalty of 27–41 ms per unit for builds that write incrementally. A per-write cost is inconsistent by 9–16×.
- It predicted sub17n at 205–209K if that penalty were real, and at 189–194K if sub17's own changes cost time.
- From sub16's score, 220K needs host process time cut by 27% (fixed cost 0.36 s) to 46% (0.44 s); 230K needs 41% to 68%.
- **What turned out wrong:** sub17n scored 196,165, between the two predictions. The "penalty for incremental writing" reading found no support in sub17t's score either: sub17t scored 1.6% above sub17n (one upload per side; within the reported noise; not established).
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

In the order the results were read. Each wrong reading is kept, labelled **Wrong**. Every comparison below rests on one Development upload per side. Another team later reported identical images scoring up to 14% apart on the Development board (issue #37, §9.10.2), so a difference of a few percent between two single uploads is within the reported noise. The readings made at the time are kept as they were made; what each actually establishes is stated with it.

**1. sub16m: 203,394.** +7.6% over sub11m, one upload per side. At the time this was read as: building the trace in order during the run paid far more than the laptop's 4–7% suggested. The difference is larger than the others of this section, but it is still one upload per side.

- **Wrong:** a first projection for sub17 from laptop process times: 197–205K. Then, after a refit to 203,394: 205–209K for sub17n and 209–219K for sub17t. Actual: 196,165 and 199,285. All three projections were wrong. The score-model agent had already shown that such a model does not fit (§9.9.6).

**2. sub17t: 199,285 (uploaded after 976478, finished before it).**

- **Wrong:** "writer threads lose on the host", announced on this one score. The comparison score had not arrived. It was corrected about an hour later.

**3. sub17n: 196,165.** The comparison build scored lower still.

- sub17n → sub17t: +1.6%. Read at the time as: writer threads during the run were a small gain on this binary. One upload per side; within the reported noise; not established. It therefore does not contradict the reading of sub13 as "a streaming writer loses" (§9.8.15) either; neither is established.
- sub16m → sub17n: −3.6%, although the laptop counters and process time both had sub17 ahead. One upload per side; within the reported noise; not established.
- **Wrong:** "adding or strengthening a thread loses; removing threads wins", a pattern read from nine score steps, each of them a single upload per side. One counterexample was dismissed. On this pattern a 60/40 bet was made that sub16 with the helper off would score above 203,394.

**4. sub16 with the helper off: 185,818.**

- sub16m → sub16 helper off: −8.6%. Same binary, one environment variable (`lab/bench/Dockerfile.nohelper` adds `ENV T3_LAT_THREAD=0` to the scratch image without adding a layer). Read the other way, the helper thread is worth +9.5% on this binary. This is the only comparison of the project in which one binary differs by one setting, and +9.5% is the largest of the single-upload differences of this section. It is still below the 14% spread reported for identical images: one upload per side; within the reported noise; not established.
- The 60/40 bet lost: the score was below 203,394. The "threads lose" pattern was not supported by this score; it was never established in the first place.
- **Not established:** the arithmetic 185,818 × 1.056 = 196,222 is close to sub17n's 196,165 and suggested that sub17's helper was not working at all on the host. The next result neither proved nor disproved that.

**5. sub18 with the helper off: 193,962.**

- sub16 helper off → sub18 helper off: +4.4%. Read at the time as: sub18's engine (the branch-free heap step plus the cuts of §9.9.7) is better on the host at equal helper setting. One upload per side; within the reported noise; not established. The laptop counters do show sub18's simulation thread doing less work (§9.9.7).
- It said nothing about whether sub17's helper works on the host.

**Summary of the five scores.** Each row is one upload per side.

| Comparison | Host result | Reading at the time | Status |
|---|---|---|---|
| sub11m 189,018 → sub16m 203,394 | +7.6% | Three post-run passes and their threads removed; worth far more than the laptop said | Observed, one upload per side |
| sub16m 203,394 → sub16 helper off 185,818 | −8.6% (the helper "worth +9.5%") | The helper thread helps on the host | Within the reported noise (largest such pair, below the 14% spread); not established |
| sub16 helper off 185,818 → sub18 helper off 193,962 | +4.4% | sub18's engine is better at equal helper setting | Within the reported noise; not established |
| sub16m 203,394 → sub17n 196,165 | −3.6% | By elimination, sub17's changed helper start-up is the cause | Within the reported noise; not established. The elimination rested on the two rows above, which are not established either |
| sub17n 196,165 → sub17t 199,285 | +1.6% | Writer threads during the run are a small gain on this binary | Within the reported noise; not established |

**A guess about the mechanism, untested.** A thread that runs from engine creation is placed by the scheduler's fork-time balancing, possibly far from the simulation thread, even on the other socket. A thread woken by the simulation thread at run start is placed near it. The krllx comment of §9.9.2 (about 6% from core sharing) shows placement effects of this size exist on the host. Nothing we measured confirms the guess, and the difference it was meant to explain is itself not established.

**What followed.** At the time the best engine (sub18) and the best helper behaviour (sub16) were read as not yet scored together, and sub19 was built as that combination. Both "best" readings rest on single uploads.

#### 9.9.9 sub19a and sub19b

- **What:** sub18's engine with sub16's helper code restored verbatim: started through a condition variable when the run begins, spinning when the ring is full, ring of 2^13 values, permanent inline fallback if the helper is late.
- **sub19a** keeps the branch-free heap step. **sub19b** restores the branching one.
- **Why:** sub16's helper start-up is the only one with a good host score, and sub18's engine scored above sub16's at equal helper setting. Both readings rest on one upload per side and are within the reported noise (§9.9.8, §9.10.2); they were the best guide available, not established results. sub19b exists because the heap step has not been scored separately from the other engine changes.
- **Sources:** `lab/bench/engine_sub19a.cpp`, `lab/bench/engine_sub19b.cpp`.
- **Checked so far, both:** byte-identical to sub16's output on 65/65 single units in the dev container.
- **sub19a full validation** (`lab/bench/validate_sub19a.log`): tables 65/65, repeat-run bytes 65/65, batch 6/6, fallback run, official regression 65/65, fuzz replay 1,318 of 1,318 (1,296 through the launcher, 22 handed to the Python path).
- **sub19a scratch image** (`sub19am`, `lab/scratch_checks.sh`): binary identical to the one in the validated image, batch 6/6, official regression 65/65, no-ledger units 6/6. Pulled back by digest, it wrote the correct files on three units under the runtime restrictions.
- **Pushed** as `native-v19a`, `sha256:abca67f17b3558eedca6e44ec2e437ec5b9ff7ccb3121c4ad2c4879f53dcf434`. Not uploaded when this was written.
- **sub19a scratch image checks, push, upload:** not done when this was written.
- **sub19b:** full validation not run when this was written.
- **Host score:** sub19a 199,057.7311 (§9.9.16); sub19b never uploaded.

#### 9.9.10 The fuzz-replay breakdown varies between builds and passes, and a fix that has not shipped

**The finding.** The number of cases handed to the Python path is not the same in every run of the same corpus: it varies between builds (22 to 27 over this section and §9.10) and, on one build, between a full replay and a launcher-only pass (22 against 23 on sub19a, §9.9.16, item 4):

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

The experiments of this section are E105 to E133 in §10.

#### 9.9.13 Hypotheses of this section

The hypotheses of this section are H68 to H83 in §15, with H53, H63 and H65 carried from earlier sections.

#### 9.9.14 Failures

| Failure | Cause | Consequence |
|---|---|---|
| sub17 bundled a speculative helper change with a measured optimisation | The helper change was added "as a safeguard" with no host evidence | sub17n scored 3.6% below sub16 (one upload per side; within the reported noise); the two changes could not be told apart, and the cause, if any, was never isolated |
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
- **Uploads:** two of 23 remain. (Later: both were used, by sub19a and sub16t; §9.9.16, §9.10.1.)
- **The fixed per-container cost on the host** is still unknown. It is bounded above by 0.471 s from the leader's score (§9.8.7). The organizers' calibration post had not appeared. (Later: published; how it relates to that bound is in §9.10.2.)
- **Whether a helper thread started at engine creation is worth less on the host than one woken at run start at all:** not established; the −3.6% that suggested it is one upload per side.
- **Whether the branch-free heap step is a gain on the host by itself:** not scored separately.
- **The fix of §9.9.10** is in no image and has not been fuzz-replayed.
- **The Final:** one submission, the same host, sealed units, five runs per unit. Undecided: a scratch image, in which a declined scenario scores zero, or the full image with the exact Python fallback. (Later: the full image was chosen, uploaded and scored, §9.10.)

#### 9.9.16 After this section was written: sub19a's score and four corrections

**sub19a scored 199,057.7311** (upload 977400), the 22nd of 23 uploads. One upload remained; it was used for sub16t (§9.10.1).

Each cell is one upload:

| Engine | Helper off | Helper on | Difference |
|---|---:|---:|---:|
| sub16 | 185,818.35 | 203,394.47 | +9.5% (same binary) |
| sub18 | 193,962.28 | 199,057.73 (sub19a, sub16's helper code) | +2.6% |

- Observed: sub19a is 2.1% below sub16 and 2.6% above sub18 with the helper off. Both are one upload per side; within the reported noise; not established. The +9.5% of sub16's row is the largest single-upload difference of this section and is still below the 14% spread reported for identical images (§9.10.2).
- The expectation behind sub19 (the engine's +4.4% and the helper's +9.5% adding up, about 212,309 by arithmetic, a product of two ratios and not a score) was not met. Since neither ratio is established, this shows only that the expectation failed, not why. H81 (sub19a above 203,394): sub19a scored below it, one upload per side; within the reported noise; not established (§15).
- What sub19a says about the reading of §9.9.8 that sub17 lost because of its changed helper start-up: nothing either way. That reading was never established (§9.9.8), and sub19a's score, one upload, cannot settle it.
- A guess, untested: once the event loop is fast enough it finds the helper behind at the start of the run, and in sub16's helper code the loop then draws its own latencies for the whole run (`feed_mode = 0`, "the helper is not keeping up: stay inline for the whole run"). A faster engine would then forfeit most of the helper's benefit. No measurement separates this from other explanations, or from noise.

**Corrections to the record above.**

1. **sub16's fuzz replay was completed.** `lab/bench/validate_sub16.log` ends with the replay crashed at 200 of 1,318. `lab/bench/val_sub16/fuzz.log`, written later by a separate replay on the image tagged `sub16`, holds a complete one: 1,318 of 1,318, 1,296 through the launcher, 22 handed to the Python path. The image under that tag was created once and not rebuilt; no digest was recorded with the log. The statements in §9.9.4, §9.9.14 and §11 that the replay was not repeated were wrong.
2. **sub19b was validated.** `lab/bench/validate_sub19b.log`: tables 65/65, repeat-run bytes 65/65, batch 6/6, official regression 65/65, fuzz 1,318 of 1,318 (1,296/22), in its full image. No scratch image of it was built.
3. **The organizers' repository did have later commits.** `160f86e` and `1d7e994` change documentation only. With the answers in `Agenthon-2026/Agenthon2026-public` issues #2 and #9 they say: the Final takes one upload per team at any time in a window of about two weeks after Development closes; the code may change during that window; a Final upload that ends as failed does not use the attempt; ties go to the earlier upload; outputs, logs and the Final board are hidden. This record had treated the Final as a single submission immediately after Development. The hub repository's issues had not been read; only the Track 3 repository's had.
4. **The declined-case count on one build is not one number.** Three launcher-only passes over the stored cases on the sub19a image declined 23 each (19 with a non-boolean `protocol_enforcement`, 4 with a latency draw sensitive to the `log` implementation); the full replay on the same image handed 22 to the Python path. The launcher-only tool starts the launcher with an emptied environment, so the image's settings are not applied in it; whether that or the helper's look-ahead (§9.9.10) explains the one case was not traced.

**Consequence for the Final.** After the last Development runs there is no host timing. Anything changed after that ships unmeasured, and the Final compares `trace.parquet` byte for byte across five repeats of each unit, so a hand-over decision that depends on thread timing (§9.9.10) matters more there than in Development.

**The last upload, prepared and not made when this was written** (it was made later and scored below sub16, §9.10.1). `sub16t`: the sub16 scratch image with `T3_TRAIL=1` added as an environment setting (`lab/bench/Dockerfile.trail`). Binary identical to sub16's; batch 6/6; official regression 65/65; no-ledger units 6/6; output bytes identical across three runs on the 65 single units (`lab/bench/scratch_sub16t.log`). With the setting on, the files differ in bytes from sub16's own output with it off (same tables, different page layout). Evidence for a gain: the sub17 pair only (+1.6%; one upload per side; within the reported noise; not established). No fuzz replay was run with the setting on this binary.

The experiments of this section are E134 to E136 in §10.

### 9.10 The Final

This section covers everything from the last Development upload to the Final result. Its sources are the fact sheet `lab/agent_report/facts_final.md` and the logs it cites in `lab/bench/`.

#### 9.10.1 The last Development upload

The last upload was `sub16t`, prepared in §9.9.16: the sub16 scratch binary with writer threads on (`T3_TRAIL=1`), pushed as `slashalpha/agenthon-track3:native-v16t`, `sha256:b0478b41338580ff4cd4285551ce0b3dcaff1a96e974bf391d739d9403f32602`. Checks before the upload: binary identical to sub16's, batch 6/6, official regression 65/65, no-ledger units 6/6, output bytes identical across three runs on the 65 single units (`lab/bench/scratch_sub16t.log`).

It was the 23rd and last Development upload. **It scored below sub16**; the team reported it as "not good", and its exact score was not recorded in this record. **sub16's 203,394.4709 stays the best Development score.** The last board reading the team recorded put S2WISH at rank 10 of 50. The one pair of scores that had suggested writer threads help (sub17, +1.6%) was not repeated on sub16's binary. Both results are one upload per side; within the reported noise (§9.10.2); not established, either way.

#### 9.10.2 What the organizers published about the Final

From the CodaBench competition API (phase "Final & Verification"), the issue trackers and the README of the Agenthon-2026 repositories:

| Topic | Statement | Consequence for us |
|---|---|---|
| Window and budget | The Final phase opened when Development closed and runs for about two weeks, with **one upload per person in total** and one Final upload per team. A Final upload that ends as Failed does not use the attempt; a held one does. Code may change after Development; ties go to the earlier upload | One upload and no host feedback before it: anything changed after Development ships untimed on the host |
| What is hidden | Outputs, logs, per-unit outcomes and the Final board; results are published after the Final closes. The image must stay pullable until then | No rank and no per-unit result can be read during the window |
| Timing | Each unit runs **five times back to back with the same seed**; the unit's rate is verified events ÷ the **median of the four runs after the warm-up**; each run is timed from `StartedAt` to `FinishedAt` (creating and removing the container are not counted) | Most of the fixed container cost that dominated Development lies outside the timed window |
| Score | The **arithmetic mean of the unit rates** over the whole roster: the public units plus an unpublished number of **sealed scenarios** | Units with the most events weigh most |
| Correctness | Every scenario, public and sealed, must pass ("a single failure anywhere is inadmissible"); a run that crashes, times out (300 s) or runs out of memory scores the unit 0; **all runs of a unit must write byte-identical trace and ledger files** | All or nothing: one declined input in a scratch image (exit 127) or one repeat with different bytes would be fatal |
| Runtime | Read-only root, 64 MiB `noexec` `/tmp`, uid 65534, no network, `--cpus=4` quota (not pinned), 16 GiB, GPU attached through CDI (it cannot be opted out of) | Every fallback path must work under these restrictions, not only the launcher |
| Calibration (issues #24 and #34) | The timing machine is a KVM virtual machine on an Intel Xeon Platinum 8570, 20 vCPUs as 10 cores × 2 threads, one NVIDIA B200. A static binary that only copies outputs takes a median **0.165–0.173 s** per Final window (runtime and GPU set-up); the same work from a Python image **0.342–0.343 s**. Create-to-remove, as the Development board counted it, was **0.630–0.643 s** for the static binary | About 0.46 s per unit lies outside the Final window. How the 0.630–0.643 s relates to the 0.471 s bound of §9.8.7 is explained below the table |
| Noise (issue #37) | Another team reported identical images scoring up to **14% apart** on the Development board (203.0K and 219.4K; 230.9K and 202K). The organizers could not tell drift from noise in two of their own timings 26 minutes apart | See below |
| The organizers' baseline | ABIDES writes `summary_log.bz2` under `./log/` at the end of every run, which fails on the read-only root; fixed upstream in commit `fe32378` with `log_dir="/tmp/abides"` | Our own last-resort path had the same defect (§9.10.3) |

**The calibration and the 0.471 s bound.** This is the one place in this record where the two are compared; other sections point here. §9.8.7 derived a bound from the leader's Development score: over the 71 units the score with zero process time is 108,853 ÷ c for a fixed cost of c seconds per container, so the leader's 231,024 requires c ≤ 0.471 s. The organizers' calibration gives 0.630–0.643 s create-to-remove for a static binary that only copies outputs, which is above that bound. Two things separate the figures:

- The calibration was taken on the organizers' Final timing path. They said that path "adds a few organizer checks inside that span", so "a Development run of the same image may come out a little lower". The 0.630–0.643 s is therefore not a measurement of Development's create-to-remove.
- The 0.471 s bound assumes the same fixed cost on every unit. If the cost differs between units, the bound does not hold as stated.

The most likely reading is that Development's create-to-remove was lower than the rehearsal's. The published figures do not settle it, and our own fixed cost per container on the host was never measured (§9.9.14).

**What the 14% report means for this record.** The report in issue #37 contradicts the 0.1% agreement another participant had reported (§9.9.2), and the organizers could not settle it. Every conclusion of this record that rests on one Development upload per side and a difference of a few percent is therefore **not established**. In this section and §9.9 that covers the helper thread's +9.5% (sub16 against sub16 with the helper off; §9.9.8), sub18's engine +4.4% (the helper-off pair), the writer threads' +1.6% (the sub17 pair), sub17's −3.6% and the "by elimination, its helper start-up" reading built on it, sub19a's −2.1% and +2.6% (§9.9.16), and sub16t below sub16 (§9.10.1). The observed scores stand; the readings become: one upload per side; within the reported noise; not established. The helper's +9.5% is the largest of these pairs, and it is still below the 14% spread reported for identical images. sub16's +7.6% over sub11m is larger than the others but is also one upload per side.

#### 9.10.3 Two defects found in the best image while preparing the Final

**1. The last-resort ABIDES path crashed on the read-only root.** `sub/abides_fork/simulate.py` called `abides.run(config)` without `log_dir`. With the reference path forced (`T3_NO_LAUNCHER=1 T3_FORCE_REFERENCE=1`) under the Final's restrictions, the sub16 full image exited with `OSError: [Errno 30] Read-only file system: './log'` on a single unit and wrote no files (`lab/bench/refpath_sub16/single.err`; script `lab/ref_path_check.sh`). The batch path was not affected: it changes into a temporary directory, and the batch unit completed (`lab/bench/refpath_sub16/batch.out`). The scored scratch images have no Python layer, so this never affected a score; it would have affected any declined input in a full image. The organizers' own baseline had the same defect (§9.10.2). **Fix:** `abides.run(config, log_dir=tempfile.mkdtemp(prefix="abides-log-"))`, one directory per run so that parallel batch workers never share it.

**2. The hand-over decision could depend on thread timing.** This is the finding of §9.9.10, now traced in the code. The helper thread computes latency draws ahead of the event loop and raised the "rounding-sensitive" flag for draws the run might never use. Launcher-only passes over the stored fuzz cases declined 23; full replays handed 22 to Python (§9.9.16, item 4). Across the five repeats of one sealed unit this could have sent one repeat to the Python path and not another: different file bytes, and a refused unit. **Fix** (`lab/bench/engine_final.cpp`, made by `amb_patch16.py` from `lab/bench/engine_sub16.cpp`): `latency_from` reports sensitivity through a flag argument; the event loop's own inline draws raise the global flag as before; the helper records only the index of the first sensitive draw it computed, and after the run that index counts only if the loop used the ring and the index is below the number of values it consumed. The source-only fix of §9.9.10 was written against sub18's engine; this one is applied to sub16's.

#### 9.10.4 The Final build

**What.** sub16's engine, launcher and Parquet writer (launcher and writer byte-identical to the sub16 snapshots) with the two fixes, in the **full image with the exact Python fallback**, with the environment `T3_HUGE=0 T3_PREFAULT=0 T3_TRAIL=0`: the memory settings and the writer setting of the 203,394 run. The memory settings are set by `lab/bench/Dockerfile.memoff` (`ARG BASE`, `FROM ${BASE}`, `ENV T3_HUGE=0 T3_PREFAULT=0`), which changes the image's environment and adds no layer. Locally the validated full image is tagged `final` and the image with the memory settings `finalm`.

**Image:** `slashalpha/agenthon-track3:native-final`, **`sha256:44f825eb7b8a5e0276baea84aafe3c344bdbb927500dac2a6ac0782e05e93487`**, 773 MB, `linux/amd64`, interface label 2.0, no `VOLUME`, no entrypoint (the command starts the static launcher directly).

**Why the full image and not the 2 MB scratch image that scored 203,394.** With all-or-nothing correctness on sealed scenarios, a declined input in a scratch image exits with status 127, which counts as a crash. In the timed window both images start the same static launcher; Python loads only for a declined input. **What the full image costs on the host was never measured**: no Development uploads were left. The earlier reading that image shape and output size are minor factors on the host (sub5 against sub7, +1.85%) is not verified either: it is one bundled pair that also changed the output encoding, one upload per side, within the reported noise (§9.10.2). The choice of the full image was therefore a risk decision, made for all-or-nothing correctness on sealed scenarios, not a measured one.

**Decision round 8.** The decision model was given both sides. Its answers are judgments, not measurements:

| Question | Answer |
|---|---|
| Which image for the Final | **Full image 0.97**; scratch as scored 0.01; a new scratch image of the fixed binary 0.02 |
| At least one sealed scenario will be handed over to the Python path | 0.56 |
| The full image scores more than 1% below scratch | 0.36 |
| The full image scores more than 3% below scratch | 0.23 |

Followed: the full image was validated, pushed and uploaded.

**Validation** (`lab/bench/validate_final.log`, `lab/bench/checks_finalm.log`, `lab/bench/fuzz_final.log`, `lab/bench/refpath_final/`, `lab/bench/refpath_finalm/`, `lab/bench/pullcheck/`):

| Check | Result |
|---|---|
| Output against the sub16 binary, 65 single units | Byte-identical with the helper on and with it off |
| Tables, 65 scenarios | 65/65 |
| Repeat-run bytes, three runs of each scenario | 65/65 |
| Batch units under the runtime restrictions | 6/6 |
| Single run and forced fallback (two modes) under the restrictions | All exit 0 with three files |
| Official regression | 65/65 on `final`, and again on `finalm` |
| `finalm` against `final` | Binary identical; batch 6/6; no-ledger units 6/6 |
| Fuzz replay of the 1,318 stored cases | 1,318 of 1,318 (1,296 through the launcher, 22 to the Python path) |
| Forced reference path under the Final's restrictions | One single unit: 604 and 664 rows, equal to the reference tables; one batch unit completed |
| Pushed image pulled back by digest and run on one unit under the restrictions | Tables equal to the reference (71,932 and 63,287 rows) |

**Also recorded:** sub16's fuzz replay did complete in a separate run before its upload: `lab/bench/fuzz_sub16_complete.log`, 1,318 of 1,318 (1,296/22). This agrees with the correction in §9.9.16, item 1.

#### 9.10.5 The Final result

**Upload 993712, status Finished, primary score 1,755,232.6496** (events per second, the Final metric). It used the one Final upload.

- The run summary page lists the kinds of problems a run had; it listed none (no reason codes). It shows no unit count and no per-unit outcomes on a sealed phase. Our reading: no unit failed. This is not a unit-by-unit proof.
- The Final board and the other teams' Final scores are hidden until results are published, so **no rank is known**.
- **The Final score is not comparable with Development scores.** The timed window is different: about 0.46 s per unit less is counted, by the organizers' calibration (§9.10.2).

#### 9.10.6 Experiments of this section

The experiments of this section are E137 to E150 in §10.

#### 9.10.7 Hypotheses of this section

The hypotheses of this section are H84 to H90 in §15; H53, H65, H77, H80 and H82, carried from earlier sections, have their final status there too.

#### 9.10.8 Failures and lessons

| Failure | Cause | Consequence |
|---|---|---|
| The scored line's fallback paths were never tested under the runtime restrictions with the last-resort path forced | The validation's forced-fallback check (`T3_NO_LAUNCHER=1`) does not force the ABIDES reference path; that path was first run under the read-only root with `lab/ref_path_check.sh` while preparing the Final | Any declined single input in a full image would have crashed. The scored scratch images never reached that path |
| The Final's rules were read late | The hub repository's issues and the Final phase's settings were read late (see also §9.9.16, item 3) | The choice between scratch and full image, the five-repeat byte rule and the runtime restrictions were weighed with no Development uploads left to measure anything |
| The hand-over decision depended on thread timing for several builds | The helper's look-ahead set a global flag (§9.9.10); the source-only fix of §9.9.10 never shipped | No public unit was affected in Development; fixed before the Final, where five repeats must match |
| Single-upload differences were read as findings | No repeat upload of one digest was ever made | The conclusions of §9.9.8 and §9.9.16 rest on one upload per side and are within the reported noise: not established (§9.10.2) |
| sub16t's exact score was not recorded | — | Its comparison with sub16 is qualitative only |

The first two lessons are one: test the image that will be scored on every path it can take, under the conditions it will run in, and read those conditions before the last uploads are spent.

#### 9.10.9 Open after the Final

- **Verification and publication** by the organizers: the Final board, the rank, and whether every sealed unit passed are not known until results are published.
- The image must stay pullable by digest until then.
- Nothing in this record measures the full image's cost against the scratch image on the host (H88).
