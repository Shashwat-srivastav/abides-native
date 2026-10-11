
---

## 15. Hypothesis register

Every hypothesis that drove a decision, the test, the outcome, and whether the evidence was a measurement or an argument. H1–H7 are the Phase-A hypotheses of §4.2 and §6; the rest are numbered in the order they arose. H44–H53 first appeared in §9.7.10, H54–H68 in §9.8.13 and §9.8.15, H69–H83 in §9.9.13; the rows here carry the status. Two pairs are one hypothesis under two numbers: H43 and H47, H64 and H68.

| ID | Hypothesis | Test | Outcome | Status |
|---|---|---|---|---|
| H1/H6 | Order-book logging feeds no output and can be switched off | 65-scenario byte identity | Identical; part of 1.78× | **Confirmed** |
| H2 | A scalar clamp equals `np.clip` on a float | Byte identity | Identical | **Confirmed** |
| H3 | Guarding `logger.debug` calls changes nothing but time | Byte identity | Identical | **Confirmed** |
| H4 | A lock-free `heapq` gives the same pop order as `PriorityQueue` | Byte identity | Identical; total 2.04× | **Confirmed** |
| H5 | Cheaper `deepcopy` is safe | Not tested (decision model P(safe) 0.39, ceiling 1.09×) | — | **Parked, untested** |
| H7 | A native reimplementation can be bit-exact | 65 scenarios + 30 batch subs + 2,416 fuzz cases | Identical after 2 fuzz-found fixes | **Confirmed on everything tested** |
| H8 | Trace rows arrive in time order, so only equal-time groups need sorting | Identity + a monotonicity check kept in the code as a safety net | Identical; assembly 2.83 s → 0.07 s | **Confirmed** on the public units; **refuted for negative latencies** (H67), which `repair_trace` handles since sub15 |
| H9 | Page faults on output buffers are a large share of the loop | perf (about one third in kernel fault handling); then A/B | Mean 4.2M → 6.42M | **Confirmed** |
| H10 | A dense price-indexed order book beats sorted vectors | A/B | 0.57–1.09× | **Refuted**; reverted |
| H11 | PGO gives a consistent gain | A/B on 16 training configs | −9% to +27% | **Inconclusive** with wall-clock timing; not adopted then. A profile-guided build was tested again (E86: −1.9% on six units) and has been in every build since sub11 |
| H12 | `-march=x86-64-v3` is worth a CPU-dispatch build | A/B | +3.7% | **Too small**; not adopted |
| H13 | One capacity check per ledger row is faster than 13 | A/B (wall clock) | 1.01× | **Not detected** at the time; superseded by H17 |
| H14 | A warm-up effect explains the low rates of very small scenarios | `bench.cpp`: first run vs best of N in one process | First run slower, but best-of-N of the *same* binary still far below the target; and the scoring change made the question moot | **Not the main cause** |
| H15 | The grader runs about 1.28× this laptop | sub2: predicted 8.16M, actual 8.34M | Within 2% | **Confirmed for the old rule only** |
| H16 | Wall-clock timing here is too noisy to rank changes of a few percent | Same binary twice: 5.30M vs 5.45M mean; individual scenarios varied up to 2× | Switched to CPU cycle counts, stable to about 1% | **Confirmed** |
| H17 | The flat profile is dominated by per-field bookkeeping and pointer chasing in message, ledger and heap data | Rewrite A (§7.7), counters | 1,010 → 773 instructions/event | **Confirmed** |
| H18 | Near-term messages waste work sifting through far-future wakeups | Heap-size instrumentation (15 vs 10 on `mp07`, 145 vs 106 on `gb_mega`); split heaps | Part of rewrite A | **Plausible**; not isolated from the other changes in A |
| H19 | The slowest units are slow because of requeues | Counters per scenario (711,316 of 980,960 iterations on `mr_deep_book`) | Blocked queues removed them from the slowest list | **Confirmed** |
| H20 | Blocked queues give exactly the reference's dispatch order | Argument (§7.7) + independent reviewer's derivation + 65/65 identity | Identical | **Confirmed on everything tested** |
| H21 | The latency stream depends only on the draw index, so it can be computed by another thread | Code reading (every `send` is between two different agents; generator has no other reader) + 65/65 identity × 3 | 437 → 352 cycles/event | **Confirmed** |
| H22 | The helper thread is safe when only one CPU is available | Design (inline start, switch only once the helper is ahead; CPU gate) | Forced inline mode (`T3_LAT_THREAD=0`) is identical and was benchmarked; **a real single-CPU container was not run** | **Partly verified**. On the host, with four CPUs, the thread is worth 9.5% of score (H75) |
| H23 | The Development board still ranks self-reported loop speed, capped at 10M | Organizer post, upstream README, live board | False since the scoring change | **Refuted** |
| H24 | Under the new rule, Python start-up dominates our measured time | Import timing; process timing (§7.8) | Simulation < 1% of an 800 ms process on a small unit | **Confirmed** |
| H25 | A C++ program can link pyarrow's bundled libarrow/libparquet | 15-line test program | Links with CXX11 ABI 1, not with 0 | **Confirmed** |
| H26 | The same library with the same writer properties produces the same bytes as pyarrow | SHA-256 on 65 scenarios + 30 batch subs, including files above the 1,048,576-row group size (`gb_mega`: 1,168,360 trace rows, 1,420,862 ledger rows) | Identical | **Confirmed** |
| H27 | Arrow's parallel column encoding does not change the bytes | Identity with and without `T3_PQ_SERIAL` | Identical | **Confirmed**; speed benefit **not demonstrated** (timings within noise) |
| H28 | A glibc-vs-numpy difference in `log(mean_ns)` can be made harmless by detecting sensitive draws | Argument (§7.8); 0 flags on the public set | Never triggered on the public set. First triggered, on 4 of the 1,318 stored fuzz cases, where the Python path then reproduced the reference (§9.7.2). The count of flagged cases varies with the helper thread's look-ahead (H80). The 16-ulp bound on numpy's `log` is supported by documentation only (H52) | **Partly verified** |
| H29 | The local rules checkout is still valid for validation | Diff against upstream `bffb572` | Scenarios and units unchanged; one reference line changed without changing its value | **Confirmed** |
| H30 | sub4 will be competitive under the new rule | Upload | 153,825 and 151,387: rank 9 of 17, 67% of the leader's 231,024; sub3 was never uploaded, so there is no measured sub3-vs-sub4 comparison on the board | **Partly confirmed** (mid-table, not top) |
| H31 | Large units decide rank under a plain mean | Arithmetic on the 65 public units with measured process times and the fitted overhead (§9.5); the decision model had answered "small units" (0.95) | The 8 largest units hold 55% of all events and supply 42–49% of sub5's modelled score; the 57 others supply the rest, each limited mainly by the fixed overhead | **Supported by a model that was later refuted** (H42, H60), not by a score. The second review's count is that the 58 units under 100,000 rows carry 45–50% of the score (§9.8.7). No per-unit host results exist to settle it |
| H32 | The gap to the leaders is mostly our own process time, not the engine | Phase timing in the sub4 image, best of 5, 10 units | Parquet write 50–63% of the process, event loop 7–15% | **Confirmed locally and by the score**: removing the Arrow encoder gave +18.0% (sub5) |
| H33 | The verifier accepts any valid Parquet file with the same table | Reading the scorer; official regression on sub5 and sub6 | 65 passed, 0 failed, 0 errored for both | **Confirmed for the public harness and for the Development scorer** (every upload since sub5 was scored); a sealed byte-level check in the Final cannot be excluded (§11.1) |
| H34 | A hand-written writer can produce files pyarrow and pandas read as the identical table, including nullable Int64 columns and dictionary strings | `check_fast.py`, `check_batch_tables.py` | 65/65 + 30 batch subs for sub5 and for sub6 | **Confirmed on everything tested** |
| H35 | Loading libarrow is a visible fixed cost | Not isolated: the static binary arrived together with the new writer | sub4's unaccounted time per process was 20–80 ms; sub5's was about 5 ms on `st01` and about 35 ms on `gb_mega` | **Plausible, not isolated** |
| H36 | Running the trace and ledger output chains concurrently shortens the output stage | Same build before/after, best of 5 | `gb_mega` 563 → 530 ms, `mr_deep_book` 126 → 102 ms, `st01` 45 → 30 ms (this step also removed engine teardown before exit) | **Confirmed**, the two changes not separated |
| H37 | Delta encoding pays for itself by leaving less to hash and write | sub5 vs sub6, three runs each on 65 units | Output 5.6× smaller; total process time 3.41 → 3.28 s; median unit unchanged (ratio 1.007) | **Weakly confirmed for time** (about 4%, near the noise of this machine); **confirmed for size** |
| H38 | sub6 is slower than sub5 (raised by one benchmark run) | Two further interleaved runs of each image | The slow run did not repeat (5.65 s, then 3.57 and 3.58 s) | **Refuted**; the run was noise |
| H39 | A fixed container overhead caps the score well below 1M | Model fitted to sub4's score | Ceiling 221–324K for host-speed factors 0.6–1.3; the leader (231,024) lies inside that band | **The cap exists; the fitted numbers do not hold** (H42, H60). The bound that stands is 108,853 ÷ c for a fixed cost of c seconds, with c at most 0.471 s (§9.8.7) |
| H40 | 300,000 is reachable | Same model | Needs the low end of the overhead range *and* near-zero process time | **Not reached and not in sight**: best score 203,394, leader 231,024 |
| H41 | sub5 will score about 185–220K | Upload | 181,496 | **Refuted, narrowly** (2% under the lower bound) |
| H42 | The two-parameter overhead model describes the board | Fit to sub4 and sub5: k = 0.50, overhead 0.551 s, ceiling 208,565 | The leader's 231,024 is above the fitted ceiling | **Refuted as stated**. Later attempts fared no better: the fixed cost must be at most 0.471 s (H60), and no model of the form fixed cost + k × laptop time reproduces the ranking of our own builds (H70) |
| H43 | Output size costs container time on the organizers' host | The sub7 scratch upload, whose files are 5.6× smaller than sub5's (E76); sub6 itself was never uploaded | +1.85%, including sub6's and sub7's other changes | **Not supported** (restated as H47) |
| H44 | The rewritten engine (sub4 onward) still reproduces the fuzz corpus | E67 and the fuzz stage of every full validation since | 1,318 of 1,318 on sub6 to sub14, sub17 and sub18 | **Confirmed** for those builds. For sub16 the replay in the validation log stopped at 200; a separate one completed with 1,318 of 1,318 (§9.9.16); 1,318 of 1,318 on sub19a |
| H45 | The launcher handles most inputs itself | E67, E68 | 27% of the corpus on sub6; 98.3% after `as_int` was made to mirror `int()` | **Refuted, then repaired** in sub7 |
| H46 | Part of the fixed container cost depends on image shape | E76 | +1.85% including other changes | **Refuted as a major effect** |
| H47 | Output size costs container time on the scoring host | E76 | As H43 | **Not supported** |
| H48 | Asynchronous pre-faulting helps | E71 | Inside noise on the laptop | **Not shown**; off by default |
| H49 | A two-thread trace merge helps | E71 | Inside noise on the laptop | **Not shown**; the merge itself was removed in sub14 |
| H50 | Our threads are throttled by the CPU quota | E72, E89 | 0 throttled periods in every local run checked | **Refuted locally**; cannot be read on the host |
| H51 | Memory handling dominates remaining process time | E77, E79, E80; then E82 | Laptop: −12.5% and −12.1% process time. Host: −0.8% | **Confirmed on the laptop, refuted for the host** (H54) |
| H52 | numpy's `log` on the Final's CPU type is within the guard's 16-ulp margin | Documentation (about 1 ulp, §9.7.5); another team's notes that the two differ on about 27% of inputs (§9.9.6); scores | Every upload since sub4 computed μ with glibc on the host and was scored | **Supported, not measured** |
| H53 | 240,000 is reachable by the Development deadline | Decision model 0.31; second review 1–2% | Best score so far: 203,394 | **Open; very doubtful** |
| H54 | The memory work of sub8 and sub9 is worth about 3% on the host | E82 | −0.8% | **Refuted** |
| H55 | The scorer does not need a ledger on units whose card says so | E83, E85; organizers' issue #35 (§9.9.2) | In the code, by a valid score, and stated by the organizers | **Confirmed** |
| H56 | The ledger skip is worth 2–3K | E85 | +5.3K | **Exceeded** |
| H57 | Huge-page requests and up-front population cost time on the host | E90 | +0.2% with both off, bundled with a compiler change | **Not supported** |
| H58 | Switching them off costs time on the host, as it does on the laptop | E90 | As H57 | **Refuted** |
| H59 | The CPU quota throttles our threads | E89 | As H50 | **Refuted locally**; unknown on the host |
| H60 | The fixed cost per container is about 0.55 s (§9.5) | Leader's score; second review | It must be at most 0.471 s | **Refuted**. The actual value is still unknown (§11.2) |
| H61 | Warm best-of-N timing predicts the direction of a host score | E82, E85, E90; E116, E117 | Wrong for memory changes (sub9) and for sub17, whose laptop figures were better than sub16's while its score was lower | **Refuted** as a general rule; it held where work was removed outright (sub5, sub10, sub16) |
| H62 | Per-run overheads (threads, allocation) are visible on the host | E94, E98 | The build that removed them scored 2.6% lower; it bundled five changes | **Not supported; not isolated** |
| H63 | Building the trace in order during the run removes real work | E95; E105 | Laptop: −6.8% warm on seven units. Host: sub11m → sub16m +7.6% | **Confirmed on the host** |
| H64 | Writing the files during the run is a net gain | E96, E103; E116, E117 | See H68 | **Supported on the host for sub17** |
| H65 | 210,000 is reachable by the Development deadline | Second review about 18%; decision round 6 0.44 | Best score so far: 203,394; one upload left | **Open** |
| H66 | sub13 lost because small files are encoded on one thread | E99 | Laptop: sub13 was faster than sub11 on the 27 small units (802 against 873 ms) | **Not supported by the laptop; never tested on the host**. Which of sub13's five changes cost 2.6% is still unknown (see also H83) |
| H67 | Trace rows always arrive in time order | E100, E101 | 29 stored fuzz cases with a negative latency | **Refuted** for negative latencies; handled natively since sub15 (E102) |
| H68 | Writer threads during the run are a net gain | E103; E116, E117 | Laptop timing contradicted itself. Host: sub17t 199,285 against sub17n 196,165 | **Supported on the host for sub17** (+1.6%, one pair of scores) |
| H69 | Laptop whole-process times from the unit folders measure the process | E106 | 10–20 ms per run is the input mount | **Refuted** |
| H70 | "Fixed cost + k × laptop process time" predicts the host score | E118, E116, E117 | rms residual 3.2%, maximum 6.3% on our own builds | **Refuted** |
| H71 | sub17 scores above sub16 (projections 197–205K, then 205–209K and 209–219K) | E116, E117 | 196,165 and 199,285 | **Refuted** |
| H72 | Writer threads lose on the host | E116 alone | The comparison build scored lower still | **Wrong**; withdrawn after E117 |
| H73 | Adding or strengthening a thread loses on the host; removing threads wins | E127 | The helper thread is worth +9.5% | **Refuted** for the helper thread |
| H74 | sub16 with the helper off scores above 203,394 (held at 60/40) | E127 | 185,818 | **Refuted** |
| H75 | The latency helper thread helps on the host | E127 | 203,394 with it, 185,818 without, same binary | **Confirmed** (+9.5%) |
| H76 | sub18's engine is faster on the host than sub16's at equal helper setting | E128 | 193,962 against 185,818, both with the helper off | **Confirmed** (+4.4%) |
| H77 | The branch-free heap step is a gain on the host | E128, bundled with the other engine changes | Not scored alone | **Open**; sub19a against sub19b would test it |
| H78 | sub17's helper does not work at all on the host | 185,818 × 1.056 = 196,222 against 196,165 | Neither proved nor disproved by E128 | **Open** |
| H79 | sub17n lost because a helper started at engine creation is placed far from the simulation thread | None | — | **Untested guess** |
| H80 | The 25 and 27 declined fuzz cases come from helper look-ahead setting the "sensitive" flag on unused draws | E132 | A launcher-only pass declines 23 on each of sub16, sub17, sub18 | **Plausible; not confirmed by a targeted test** |
| H81 | sub18's engine with sub16's helper beats 203,394 | sub19a upload | 199,057.7311, 2.1% below sub16 | **Refuted** |
| H82 | 220,000 is reachable | Decision round 7 0.55; score-model agent: host process time must fall 27–46% | — | **Open** |
| H83 | A streaming writer loses on the host (the reading of sub13 in §9.8.15) | E116, E117 | Writer threads during the run gained 1.6% on sub17 | **Contradicted** |

---

## 16. Investigations: what was looked into and what it explained

### 16.1 Why the first native submission scored half of what the engine could do
*Looked at:* perf profile of the sub1 loop. *Found:* about a third of loop time in kernel page-fault handling for output buffers written once. *Explains:* sub1 → sub2 (4.26M → 8.34M) together with timing the same scope as the reference and fixing batch timing. *Evidence:* per-scenario A/B in §7.4.

### 16.2 Why batch units reported 10–46K while single units reported millions
*Found:* the batch timer covered process-pool start, imports and every Parquet write. *Explains:* about 0.5M of mean score lost under the old rule. *Fixed* in sub2. Under the new rule the distinction disappeared; the native batch verb (§7.8) reduces the real time instead.

### 16.3 Why some units stayed far below the others
*Looked at:* per-scenario cycle counts and loop counters. *Found:* requeue storms (§7.7 B) on `mr_deep_book`, `fastlob_core`, `as03`. *Explains:* their position at the bottom of the per-unit list. *Not explained by this:* the `gb_*` units (few requeues; they have 128+ agents and deeper heaps) and the tiny `eq_*` units (higher ledger-rows-per-trace-row ratio, 1.26 on `eq_lognormal_highsigma` against 0.89 on `mp07`), which remained the most expensive per event after the fix (about 870–1,020 instructions/event before the helper thread).

### 16.4 Why the local numbers would not settle
*Looked at:* repeated runs of one binary; host memory. *Found:* the host had 54–153 MB of free RAM out of 5.99 GB with about 1.4–1.7 GB in Windows memory compression; the Docker VM has about 2.7 GiB. *Explains:* 2× swings in wall-clock rates, a 21 ms versus 1,440 ms write of the same 2.3 MB file, and three crashes (§16.6). *Response:* cycle counters for engine work; medians of interleaved runs for `docker run` timing; explicit "single run, noisy" labels where neither was possible. *Added later:* a further, constant error was found only then (§16.12), and from that day hardware counters on one thread are the local instrument for the whole launcher as well.

### 16.5 Why the goal of 10M became unreachable
*Looked at:* the live board (leader 212,671), the organizer post, the upstream README, the upstream scorer. *Found:* §2.2. *Explains:* why no team is near the old cap and why our earlier scores are not ranked. *How it was found:* a research subagent, asked to check the rules and the board before more loop optimisation, reported that the local rules checkout was a month old; the three key facts (post text, README text, board values) were then read directly rather than taken from the subagent's summary. A first attempt to confirm it by fetching the issue page showed only the issue's opening text (a note about weekly updates) and no scoring statement; the announcement is a later comment on that issue, found through the comments API.

### 16.6 Tooling failures and what caused them

| Failure | Cause | Resolution |
|---|---|---|
| First full reproduction run stopped during the baseline step; every later step failed within seconds | Docker Desktop's VM died (`error waiting for container: unexpected EOF`) while the original ABIDES ran the large scenarios inside one long-lived Python process | Baseline now runs each scenario in its own process |
| Second full reproduction run stopped 2 minutes into the baseline | Docker Desktop exited entirely; host free RAM about 150 MB | Kit made resumable; `repro/run_resilient.sh` restarts Docker and retries (§12.7) |
| Official regression attempt 1 | Upstream harness needs toolkit v2.5.1 (`cannot import name 'digest_members'`) | Fetched the tag into `toolkit-v2.5.1/` and put it on `PYTHONPATH` |
| Official regression attempt 2 | Fresh upstream checkout has no `reference_traces/` | `--reference-dir` pointing at the earlier checkout |
| Official regression attempt 3: 65 "errored" in 3 seconds | Harness worker died: `OpenBLAS error: Memory allocation still failed after 10 retries` | `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`; one helper container removed |
| In all three cases the wrapper printed "exit code 0" | The wrapper's last command was an `echo`; the harness's own status was non-zero or its report said 0 passed | Verdicts are now read from `report.json` and the log, never from the wrapper's status |
| Source patches applied through shell here-documents silently turned `\n` inside string literals into real newlines (3 compile failures, caught by the compiler each time) | Shell tool behaviour | Code containing escapes is written with file-writing tools; here-documents are used only for escape-free scripts |
| A latency-ambiguity check flagged every clamped draw | The first version compared the unclamped value with the rounded clamp bound | Found by reading the code before any run used it; fixed (only unclamped draws are tested for rounding sensitivity) |
| Phase-timing container ran more than 5 minutes | `--out` was given a directory; the launcher handed over to the Python path, which was grinding through the largest scenario on a swapping host | Killed; file path passed; behaviour re-tested (E62) |
| Static link of the launcher against OpenSSL failed | `libcrypto.a` needs zstd/zlib | Built-in SHA-256 instead |
| Two more compile failures from `\n` turned into line breaks by here-document patches; two commands containing here-documents failed to parse | Shell tool behaviour, as above | Patches and payloads written to files |
| A build failure went unnoticed for one benchmark run (the previous image was timed again) | The build's exit status was hidden behind a `grep` pipeline | Build output goes to a log file and the script stops on a non-zero status; the affected timings were discarded and re-measured |
| Report draft stated sub4's largest output as "about 35 MB" | Written from memory | Replaced by measured sizes (sub4 45.2 MB for `gb_mega_throughput`; 289.2 MB over 65 units) |

This table ends with sub5. The failures of the following days, tooling and judgment alike, are in §9.7.11, §9.8.14, §9.8.15 and §9.9.14.

### 16.7 Second opinions
- **Reviewer agent (read-only):** no bug in the rewrite; ranked 10 further optimisations with estimated gains. Its top suggestion — pre-computing the latency stream during set-up — was not adopted in that form: under the old rule it would have moved real simulation work out of the timed scope, and under the new rule it gains nothing. The in-run helper thread (§7.7 C) is the honest version of the same idea.
- **Decision round 4:** "ship" had the highest value (2.67 of 4) but "refresh the rules checkout first" was the preferred first step (0.47 vs 0.40), and shipping before refreshing was judged an acceptable risk with probability only 0.38. Followed: the checkout was refreshed (§2.2), then sub4 was validated with the upstream harness and pushed.
- **Decision round 5:** upload the scratch image first (0.64); best next code change: fuse trace assembly and encoding (0.92). Followed (§9.7.5).
- **Two read-only reviews:** the first found the ledger rule that became sub10; the second showed the fitted score model to be wrong, found the total upload limit in a toolkit document (its figure of 20 was corrected to 23), and criticised the method (§9.8.7).
- **Decision rounds 6 and 7:** round 6 valued "helper disabled" lowest (0.50); that upload turned out to be the most informative of the period. Round 7 put "sub18 beats sub16" at 0.80, which has no host answer because sub18 with its own helper was never uploaded (§9.9.6).
- **Three agents:** a score-model agent (laptop time does not predict our own scores), an open-source research agent (the organizers' issue statements of §9.9.2) and an engine-review agent (nine ranked changes, five of them in sub18) (§9.9.6).

### 16.8 Where a unit's time actually went
*Question:* why is sub4 33% below the leader when its engine is fast? *Looked at:* `T3_PHASES` timing inside the sub4 image, first two single runs, then best of 5 on the 10 largest units and best of 3 on all 65. *Found:* Arrow's Parquet encoding was 50–63% of the process on every unit measured and the event loop 7–15% (§7.9). §7.8 had already noted that "encode + write dominate" for small units (E37) and listed it as open work; what was missing was the measurement that it dominates large units too, and the check of what the verifier needs. *Explains:* why another round of engine work would have changed little. *Does it explain the gap to the leader?* In part. sub5 scored 181,496 (+18.0%), which closed 36% of the gap between sub4 and the then leader's 231,024; the model's forecast that sub5 would close most of it was wrong (§9.5).

### 16.9 Whether file bytes have to match the reference
*Looked at:* `scoring.py` (`pd.read_parquet`, `_sha256_file(trace_path)` against the declared digest, footer row count), `batch.py` (same per sub-scenario, plus `reference_message_sha256` as a *declaration* that a ledger is required), `limits.py` (256 MiB), the README's description of the Final's stable-output rule. *Found:* no comparison of our file bytes with the reference's. *Tested:* official regression on sub5 and sub6, 65/65 each. *Residual doubt:* the Final scorer is private (§11.1).

### 16.10 How high the score can go
*Looked at:* the scoring formula; per-unit event counts and process times; one known score. *Found:* with a fixed overhead per container the score has a ceiling of (mean of events ÷ overhead) for zero process time; fitted to sub4's 153,825 the overhead is 0.36–0.52 s and the ceiling 221–324K (§9.5). *Explains:* why the top of the board is bunched between 182K and 231K, and why 10M-style numbers are gone. *Limits:* one equation, two unknowns; batch units not modelled. *Later:* the fit to two scores gave a ceiling below the leader's score and was refuted (§9.5, §9.8.7). What stands is the bound: over the 71 units the score with zero process time is 108,853 ÷ c for a fixed cost of c seconds per container, so the leader's 231,024 requires c ≤ 0.471 s. The value of c is still unknown, because per-unit host results were never obtained (§16.16).

### 16.11 A benchmark run that pointed the wrong way
*Observed:* the first all-65 run of sub6 summed to 5.65 s against sub5's 3.87 s. *Checked:* the same units in the earlier 10-unit run (sub6 faster), then two more interleaved runs per image. *Found:* 3.57 and 3.58 s for sub6, 3.64 and 4.13 s for sub5. *Explains:* nothing about the code; the host was under memory pressure during that run (§16.4). *Consequence:* per-unit minima over several runs are used for the comparison, and the outlier is reported.

### 16.12 Why laptop whole-process figures were too high by a constant
*Looked at:* a system-call trace of the smallest unit (`t3-s001-price-time-priority`, 604 events). *Found:* 9.65 ms in the first `openat` of `card.toml`, 2.08 ms in the `openat` of `scenario.json`, 0.2–1.0 ms per `read`, `fstat` and `close` on those files, and under 4 ms for everything after the inputs were read. The unit folders are a Windows-backed mount. *Explains:* 10 to 20 ms per run in every whole-process figure measured from the unit folders since sub4 (§9.8.3, §9.8.15, the `fig_*.json` files). *Response:* `lab/true_p.py` copies the inputs to memory first; counters for engine work (§9.9.3). *Not explained by this:* anything about the host, which does not have this mount.

### 16.13 Whether the latency helper thread helps on the host
*Question:* open since sub4; on the laptop the largest unit's simulation phase takes 211–220 ms with the thread and 257–298 ms without (§9.9.3), but §9.8.5 had ruled laptop thread timings out as evidence. *Test:* the sub16 binary uploaded twice, the second time with `T3_LAT_THREAD=0` set in the image's environment and nothing else changed. *Found:* 203,394 with the helper, 185,818 without: the helper is worth 9.5% of score. *Explains:* why "threads lose on the host", a pattern read from nine earlier score steps, was wrong for this thread. The upload was made on a 60/40 bet that the score would go up (§9.9.8).

### 16.14 Why sub17 scored below sub16
*Observed:* sub17n 196,165 against sub16m 203,394 (−3.6%), although counters and laptop process time both had sub17 ahead. *Checked:* sub18, which contains sub17's engine changes, against sub16, both with the helper off: +4.4% for sub18. So the engine is not the cause. *Found, by elimination:* the cause is sub17's changed helper start-up (the thread produces from engine creation instead of being woken when the run starts). *Mechanism:* **not established.** The guess that the scheduler places a thread started early far from the simulation thread is untested; a comment by the leading team that core sharing moves a large unit by about 6% shows effects of that size exist on the host (§9.9.2, §9.9.8). *Response:* sub19a and sub19b put sub16's helper code back under sub18's engine (§9.9.9); no score when this was written.

### 16.15 Whether writer threads during the run lose on the host
*Observed first:* sub17t (writer threads on) 199,285, below sub16m; announced as "writer threads lose". *Then:* the comparison build sub17n, the same binary with the threads off, scored 196,165. *Found:* writer threads were worth +1.6% on that binary. *Explains:* nothing yet about sub13, whose 2.6% loss is still unattributed (§9.8.15); it removes "a streaming writer loses" as a safe reading of it.

### 16.16 What is known about the host itself
*Looked at:* the organizers' issue threads, collected by the research agent (§9.9.2, §9.9.6); the toolkit's DEVELOPMENT-RUNTIME document; the CodaBench competition API. *Found:* Development runs on a single machine that takes only Track 3 runs, one submission at a time, and it is the machine the Final is timed on; another team reports a fixed cost of roughly half a second per container and two runs agreeing to within 0.1%; the unit folder is mounted whole at `/input`, so `card.toml` is present; `/output` is a bind mount of a host directory; uploads are limited to 5 per day and 23 per person. *Explains:* why the "busy shared host" readings and the 1.6% noise figure of §9.4, §9.5 and §9.8 should not be relied on, and why the ledger skip is safe as built. *Still unknown:* the fixed cost per container (the organizers' calibration post had not appeared; per-unit results need the team's login and were not obtained), the filesystem behind `/output`, and how the host's scheduler places our threads.

### 16.17 Why the number of declined fuzz cases changes from build to build
*Observed:* 22 cases handed to the Python path on sub9, 23 on sub10 to sub13, 25 on sub17, 27 on sub18, all with 1,318 of 1,318 correct. *Checked:* a launcher-only pass gives 23 on each of sub16, sub17 and sub18 (19 non-boolean flag, 4 `log`-sensitive). *Explanation, not confirmed by a targeted test:* the helper thread draws ahead, and a draw the run never consumes can still raise the sensitivity flag; a larger ring looks further ahead. *Matters because:* a scratch image scores zero on a declined unit. *Response:* a fix in the source only, not in any image and not fuzz-replayed (§9.9.10).

### 16.18 Whether laptop time can be turned into a score
*Looked at:* by the score-model agent, the scores of our own builds against their laptop process times. *Found:* a model "fixed cost + k × laptop process time" leaves an rms residual of 3.2% (maximum 6.3%) and cannot reproduce the ranking of our builds; the smallest structure that fits needs five parameters on six points. Its two predictions for sub17n (205–209K or 189–194K) bracketed the result (196,165) without either being right. *Consequence:* no further projections; three had already been given that day and all were wrong (§9.9.8).

---

## 17. Evidence status: verified, partly verified, not verified

State at the time of writing.

**Verified by measurement in this project**

| Claim | Evidence |
|---|---|
| sub4 passes the organizers' regression on the 65 public scenarios | 65 passed, 0 failed, 0 errored (§9.4), and again in the kit's run (`repro/out/full_run_sub4.log`). The first run's output directory, `lab/reg_sub4/`, was deleted (§9.8.11) |
| The launcher's output is byte-identical to the baseline image on 65 scenarios (sub4) | `native/engine/check_launcher.py`, hashes recomputed from files; 3 full runs |
| The launcher's batch output is byte-identical on 6 units / 30 sub-scenarios (sub4) | `native/engine/check_batch.py` |
| The rewritten engine is byte-identical through the Python path too | `native/engine/try_all.py`: 65/65, run 3 times with the helper thread |
| Engine loop cost fell 37% in cycles per event from sub3 to sub4 | `native/engine/bench.cpp`, same session |
| The scoring rule changed partway through the Development phase | Organizer comment, upstream README, live board |
| Development scores under the new rule | sub4 153,825.02 and 151,386.96; sub5 181,495.89; sub7 184,857.72; sub9 183,419.75; sub10 188,687.15; sub11 189,018.28; sub13 184,046.62; sub16 203,394.47; sub17 196,164.84 (writer threads off) and 199,285.22 (on); sub16 with the helper off 185,818.35; sub18 with the helper off 193,962.28. Read from CodaBench by the team (§9.4, §9.5, §9.8.1, §9.9.1) |
| From sub5 on, the output files read back as the same tables as the byte-verified sub4 files, on 65 scenarios and 30 batch sub-scenarios | `native/engine/check_fast.py`, `check_batch_tables.py`; the tables and batch stages of every `lab/bench/validate_sub<N>.log` |
| Full validation (tables 65/65, repeat-run bytes 65/65, batch 6/6, fallback run, organizers' regression 65/65, fuzz replay 1,318/1,318) | Passed by sub7, sub8, sub9, sub10, sub11, sub12, sub13, sub14, sub17 and sub18 (`lab/bench/validate_sub<N>.log`) |
| The stored fuzz corpus is reproduced by the current engine line | 1,318 of 1,318 on the builds of the previous row (§9.7.2, §9.9.5, §9.9.7) |
| The uploaded scratch images were checked before upload | sub7: all 65 scenarios and the 6 batch units under the full restriction set (§9.7.4). sub10: the six no-ledger units (§9.8.3). sub11 and sub13: binary identical to the validated full image, organizers' regression 65/65, batch 6/6, six no-ledger units (§9.8.4, §9.8.8). sub16, sub17 (both variants) and sub18 (both variants): the same four checks (`lab/bench/scratch_sub16m.log`, `scratch_sub17n.log`, `scratch_sub17t.log`, `scratch_sub18n.log`, `scratch_sub18h0.log`). This report holds no record of a separate check of the sub9 scratch image |
| Declared hashes are the real file hashes, with either SHA-256 implementation | Recomputed with `hashlib` in every check; portable path forced on 4 scenarios per image (sub5, sub6) |
| The outputs are deterministic at the byte level | 3 runs × 65 scenarios in every full validation |
| The ledger may be left out on the six single units whose card says so, and `card.toml` is present on the official runner | Scorer and README read (§9.8.3); `lab/check_skip.sh` 6 of 6; valid scores since sub10; organizers' statement in issue #35 (§9.9.2) |
| Image shape and output size are minor on the host | sub7: +1.85% over sub5 with a 2.2 MB image and 5.6× smaller files (§9.7.6) |
| The memory work of sub8 and sub9 gained nothing on the host | sub9: −0.8% against sub7 (§9.8.2) |
| Building the trace in final order during the run is a large gain on the host | sub11 → sub16: +7.6% (§9.9.4) |
| The latency helper thread helps on the host | Same binary with and without it: 203,394 against 185,818 (§9.9.8) |
| sub18's engine is faster on the host than sub16's at equal helper setting | Both with the helper off: 193,962 against 185,818 (§9.9.8) |
| Writer threads during the run are a small gain on the host on the sub17 binary | 199,285 against 196,165 (§9.9.8) |
| The 29 negative-latency fuzz cases are handled by the launcher since sub15 | `lab/quick_checks.sh`, with no Python reachable (§9.8.15) |
| The laptop's unit folders add 10 to 20 ms per run | System-call trace (§9.9.3) |
| Hardware counters on one thread repeat to ±0.00% (instructions), under 0.5% (branch misses), 0.5–2% (cycles) | §9.9.3 |
| The upload limits are 5 per day and 23 per person | CodaBench competition API (§9.9.1) |
| The full reproduction kit runs end to end against sub4 | `repro/out/full_run_sub4.log`, attempt 3 (§12.7) |

**Partly verified**

| Claim | What is missing |
|---|---|
| sub16, the best-scoring build, is correct beyond the public units | Everything passed; the fuzz replay stopped at 200 of 1,318 in the validation run and gave 1,318 of 1,318 in a separate run on the same image (that the tag was unchanged rests on the image's creation time) |
| sub19a and sub19b are correct | Both byte-identical to sub16 on 65/65 units; sub19a passed the full validation (fuzz 1,318 of 1,318) and the scratch image checks, is pushed and has a host score. sub19b passed the full validation in its full image |
| The sensitivity-flag fix of §9.9.10 | Byte-identical on 65/65 with the helper on and off; in no image; not fuzz-replayed |
| Why the count of declined fuzz cases varies (helper look-ahead) | Consistent with a launcher-only pass; no targeted test |
| Helper thread is safe with fewer than 2 CPUs | Gate and inline mode tested; no run in a container actually limited to 1 CPU |
| `log`-sensitivity detection makes glibc's `log` safe | Triggered on 4 stored fuzz cases, where the fallback reproduced the reference; the 16-ulp bound rests on documentation; scored uploads on the host are consistent with it; no direct comparison on an AVX-512 machine |
| Launcher declines correctly on odd inputs | The 22 to 27 declined fuzz cases pass through the Python path in the full image. In a scratch image a declined case exits with status 127 by design |
| Run-to-run variation on the host is small | Stated by the organizers (one dedicated machine) and by another team (0.1%); we have no repeat upload of one digest. Our 1.6% is from two uploads not checked to be identical |
| The CPU quota does not throttle our threads | 0 throttled periods locally (§9.7.3, §9.8.5); not readable on the host |
| Parallel Parquet encoding is faster | Identical output shown; speed difference inside laptop noise |
| The verifier does not need reference-identical bytes | True of the public scorer and harness and of Development scoring; the Final scorer is not public |
| The writer is correct beyond the public data | Paths listed in §11.1 were never exercised |
| The uploads carried the digests this report names | sub4: taken from the submission record, not checked independently (§9.4). Later uploads: the descriptor is sealed with the digest by `sub/build_submission.py`; the zips are built and uploaded by the team |

**Not verified / not done**

| Item | Note |
|---|---|
| The fixed cost per container on the host | At most 0.471 s from the leader's score; per-unit results were never obtained; the organizers' calibration post had not appeared |
| Why sub17 scored 3.6% below sub16 | By elimination its changed helper start-up; mechanism not established, the placement explanation is a guess (§16.14) |
| Which of sub13's five changes cost 2.6% | Not isolated (§9.8.15) |
| Whether the branch-free heap step is a gain on the host by itself | Not scored alone (H77) |
| sub18 with its own sleeping helper on the host | Pushed, never uploaded |
| Scores of sub19a and sub19b | None when §9.9 was written |
| The gap to the leader (203,394 against 231,024) | Unexplained. No public code from the leading teams (§9.9.6) |
| Scores of sub3, sub6, sub8, sub12, sub14, sub15 | Never uploaded |
| The 22-case fuzz re-check through `recheck_launcher.py` | Never run; replaced by the 1,318-case replay |
| A fresh fuzz campaign against the current engine and writer | Not done since the sub1 campaign |
| The filesystem behind `/output` | Known to be a bind mount of a host directory; nothing more |
| Behaviour of numpy's `log` on an AVX-512 host, measured directly | No such hardware here |
| The Final's 5-run protocol | Not rehearsed with `throughput/timer.py`; the organizers' rehearsal was postponed |
| Sealed units | Unknown by definition; the Final image (scratch or full) is undecided |
| A measurement on native Linux | Never made |
| Engine ideas of the last engine review that were not implemented (bottom-up pop, noise-trader draws on the helper thread, prefetching, lazy passive receipts) | Estimates only (§9.9.6) |
