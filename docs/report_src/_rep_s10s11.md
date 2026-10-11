| E23 | Re-profile the sub3 engine (perf, 4 scenarios, by function and by source line) | Flat: loop 36%, normal 14%, send 13%, ledger 9%, book 12% | Basis for the rewrite (§7.7) |
| E24 | Cold versus warm run in one process (`bench.cpp`, first vs best of 5–9) | Mean first 4.25–4.32M, best 5.30–5.45M | No warm-up trick pursued |
| E25 | Cycle/instruction counters in the benchmark | Repeatable to about 1% | Adopted as the engine metric |
| E26 | Rewrite A: compact message, ledger record, raw-cursor buffers, split heaps, hole trick, inline rounding | 65/65 identical; 1,010 → 773 instructions/event, 559 → ~455 cycles/event | Kept (sub4) |
| E27 | Loop instrumentation (`-DT3_STATS`): iterations, requeues, heap sizes | Requeues are 73% of iterations on `mr_deep_book`, 68% on `fastlob_core` | Led to E28 |
| E28 | Rewrite B: per-agent blocked queues, send-time blocking | 65/65 identical; 761 instructions/event; requeue-heavy units no longer slowest | Kept (sub4) |
| E29 | Instruction-level profile after A+B | RNG + latency ≈ 45% of simulate instructions | Led to E30 |
| E30 | Rewrite C: latency helper thread with wait-free hand-over and CPU gate | 65/65 identical × 3; 437 → 352 cycles/event (470 with the thread forced off) | Kept (sub4) |
| E31 | Read-only review of the rewrite by a second agent | No bug found; 10 further ideas, 1–8% each (estimates) | Ideas not implemented |
| E32 | Rules and leaderboard research by a research agent, then direct verification | Scoring changed partway through the Development phase (§2.2) | Changed the whole plan |
| E33 | Whole-process timing and import timing inside the sub3 image | ~800 ms per small unit, simulation < 1% | Led to the launcher |
| E34 | Link test against pyarrow's bundled Arrow | Works with CXX11 ABI 1 | Build recipe fixed |
| E35 | Launcher for `simulate` | 65/65 identical, 0 fallbacks; 50–250 ms per small unit | Kept (sub4) |
| E36 | Parallel column encoding | Identical bytes; speed difference not resolvable here | Kept (harmless) |
| E37 | Phase timing in the launcher | Small units: encode + write dominate; largest unit: pre-fault, assembly and encode each ≥ simulation | Open work |
| E38 | Native `simulate-batch` (threads) | 6/6 units identical; 148–1,192 ms per unit | Kept (sub4) |
| E39 | Diff of the local rules checkout against upstream | Scenarios/units unchanged; 1 example unit removed | Earlier validation stands |
| E40 | Decision round 4 | Ship has the highest value; refresh rules first | Followed |
| E41 | Image sub4; `docker run` A/B vs sub3 (4 scenarios × 3) | 2.58 vs 6.19 s, 2.20 vs 5.08 s, 4.97 vs 8.02 s, 12.36 vs 19.30 s | sub4 preferred |
| E42 | sub4 under the organizers' runtime flags | Single, batch and forced fallback all succeed | — |
| E43 | Official regression on sub4 (4th attempt; 3 harness-environment failures before it) | 65/65 pass | sub4 pushed |
| E44 | Upload sub4 (twice) | 151,387 and 153,825; rank 9 of 17 | First score under the new rule |
| E45 | Full reproduction kit against sub4 (`repro/run_resilient.sh`, about three hours) | All steps exit 0: identity 65/65, batch 6/6, RNG matrix pass, official 65/65. The baseline step needed 6 tries (Docker died 4 times) | §12.7 |
| E46 | Re-read the scoring formula in the upstream README | Score is the arithmetic mean of per-unit rates; 8 largest public units hold 55% of all events | Work aimed at whole-process time of every unit, large ones first |
| E47 | First phase timing in the sub4 image (2 runs of 2 scenarios) | `st01` warm: 154 ms, of which Parquet write 96 ms, simulate 10 ms | Led to E48 |
| E48 | Read the upstream scorer for what it requires of the files | Tables compared through pandas; declared hash compared with our own file; 256 MiB cap. No comparison of file bytes with the reference | A different, valid Parquet encoding is allowed |
| E49 | Built-in Parquet writer + `writev` + OpenSSL static link | Link failed (`ZSTD_*` undefined in `libcrypto.a`) | OpenSSL dropped |
| E50 | Built-in SHA-256 (SHA instructions + portable) | Hashes equal Python's `hashlib` on every checked file; portable path forced on 4 scenarios × 2 images: 8/8 | Kept |
| E51 | First sub5 build: 4-scenario table check | 4/4 identical tables; `st01` 154 → 47 ms, `mr_deep_book` 563 → 348 ms (single runs) | Continue |
| E52 | Single-run phase timing of the first sub5 build, 5 runs | Same unit 272 ms and 574 ms; `gb_mega` write 985 ms and 6,604 ms | Single runs unusable; wrote `bench_units.py` (best of N, outputs on `/dev/shm`) |
| E53 | Best-of-5 on the 10 largest units, sub4 vs first sub5 build | `gb_mega` 1,230 → 563 ms; `st01` 98 → 45 ms | Kept |
| E54 | Split `t3_finish`; trace and ledger chains on separate threads; no engine teardown before exit | `gb_mega` 563 → 530 ms; `st01` 45 → 30 ms; `mr_deep_book` 126 → 102 ms | Kept (sub5) |
| E55 | Best-of-3 on all 65 units, sub4 and sub5; fit of the overhead model to sub4's score | Sum of process time 10.20 s → 3.87 s; model: sub5 182–214K, ceiling 221–324K (first fit; refined in E61) | 300K judged at or beyond the ceiling; sub5 worth shipping to get a second data point |
| E56 | sub5 table check on all 65 scenarios | 65/65, 0 handed to Python | — |
| E57 | sub5 batch units under the runtime-restriction flags | 6/6 identical tables; exit 0 | — |
| E58 | Official regression on sub5 | 65 passed, 0 failed, 0 errored (first attempt) | sub5 pushed after the team's go-ahead |
| E59 | sub6: delta-encoded integers, 2 encode threads per file, uninitialised columns, threaded ledger fill | 10/10 then 65/65 tables, 6/6 batch, official 65/65; `gb_mega` 530 → 485 ms; output 758.7 → 135.8 MB over 65 units | Built; not pushed |
| E60 | Best-of-3 on all 65 units for sub6 | 5.65 s against sub5's 3.87 s: sub6 apparently slower | Not believed (contradicted E59's 10-unit run); led to E61 |
| E61 | Two more interleaved runs of each image (4 repeats per unit) | sub5 3.64 and 4.13 s; sub6 3.57 and 3.58 s. Per-unit minima: 3.41 s vs 3.28 s; median ratio 1.007 | E60's run was machine noise. sub6 ≈ 4% less total time than sub5 |
| E62 | `--out` given a directory (re-test of the hang seen before E47) | Launcher hands over to Python, which exits 1 with `IsADirectoryError` | Misuse, not a harness case; documented in §7.9 |
| E63 | sub5 and sub6: one `simulate` under the restriction flags; the same with `T3_NO_LAUNCHER=1` | 4/4 runs exit 0 with correct declared hashes | — |
| E64 | sub5 and sub6: every scenario 3 times, SHA-256 of both files compared across runs | 65/65 units byte-identical across runs, both images | Stable-output requirement of the Final met on this machine |
| E65 | Upload sub5 | 181,496 (+18.0%); below the modelled 185–220K | Model re-fitted: k = 0.50, overhead 0.551 s, ceiling 208,565, which the leader exceeds; model incomplete (§9.5) |
| E66 | Read the public timing harness | `docker run --rm` timed as a whole; GPU flags on units that declare a GPU; `/output` bind mount | Output-size theory downgraded |
| E67 | Replay 1,318 stored fuzz cases on sub6 | 1,318 OK; launcher declined 960 | Led to E68 |
| E68 | Histogram of decline reasons | 941 float-typed whole numbers, 19 non-boolean flag | `as_int` mirrors `int()` |
| E69 | Ledger encoded from records; faster packer; async pre-fault; two-thread trace merge | 65/65 tables; speed vs sub6 not resolvable | First two kept; last two off by default after E71 |
| E70 | A/B of the switches while the fuzz replay was running | Spread of 30% between identical runs | Discarded |
| E71 | A/B of the switches on a quiet machine (4 units × 9 rounds) | No variant clearly better; sums 920–1,013 ms | Conservative defaults |
| E72 | CPU-quota throttling check | 0 throttled periods on 4 units | Thread counts left as they are |
| E73 | Scratch image: 65 + 6 under the full restriction set | All exit 0, tables identical | Pushed on request |
| E74 | Four parallel agents | §9.7.5 | Scratch upload; memory work |
| E75 | Decision round 5 | Upload first 0.64; fuse 0.92 | Followed |
| E76 | Upload of the scratch image | 184,857.72 (+1.85%) | Image shape and output size are minor |
| E77 | Resource survey | System time ≈ user time; buffers at most 58–68% used | sub8 |
| E78 | First `\u` fix (decline) | 6 of 65 public units declined | Replaced by decoding |
| E79 | sub8 | −48% faults; −12.5% process time; fully validated | Built |
| E80 | sub9 | −34% further faults; −12.1% process time; 65/65 tables | Built and fully validated (tables 65/65, repeat-run bytes 65/65, batch 6/6, official regression 65/65, fuzz replay 1,318/1,318); not pushed |
| E81 | Figures and Zenodo report | `paper/` | — |
| E82 | sub9 scratch image on the host | 183,420 (−0.8% against sub7) | Memory work does not pay on the host |
| E83 | Read the scorer and README for the ledger rule; count cards | 12 of 71 cards say `false`; 6 usable | Implement the skip |
| E84 | sub10: six no-ledger units, skip against full | 6/6 correct; −11.9% process time on them | Validate, push |
| E85 | sub10 on the host | 188,687 (+2.9%) | Removing real work pays about twice the model's estimate |
| E86 | Profile-guided `-O3` build | −1.9% on six units; tables 65/65 | Keep |
| E87 | Memory switches, warm, largest unit | Both off: +70% | Ship switched off once, as a host experiment |
| E88 | Fresh-container timing (`lab/cold_runs.sh`) | 2–5 times slower than warm; set-up phase 33–429 ms; VM has 2.97 GB | Local memory and thread timings are not evidence about the host |
| E89 | Throttling counters in fresh containers | `nr_throttled 0` in 6 of 6 | Quota is not the cause locally |
| E90 | sub11 (memory switches off) on the host | 189,018 (+0.2%) | Switches cost nothing on the host; keep them off |
| E91 | Organizers' repository checked for new commits | None since the scoring change | Rules unchanged |
| E92 | Upload limits read in the runtime guide | 5 per day, 20 in total (the toolkit document's figure; the competition page allows 23: E129) | Bundle validated changes; no upload for small predicted gains |
| E93 | sub12: streaming writer | Fully validated; peak memory 92 → 88 MB | Folded into sub13 |
| E94 | sub13: pooled threads, scratch reuse, allocator settings, thread cap, agent layout | Fully validated; uploaded | Scored 184,046.62 (E98) |
| E95 | sub14: trace in final order during the run | 65/65 first time; −6.8% warm on seven units; 89 → 66 MB | Full validation |
| E96 | sub15: writer threads during the run | Correct and byte-stable; speed not yet measured | Measured in E103 (laptop, inconclusive) and E116, E117 (host) |
| E97 | Toolkit v2.4.0 against v2.5.1 descriptor sealing | Identical digests | Scripts repointed |
| E98 | sub13 on the host | 184,047 (−2.6% against sub11) | Do not build further on sub13's writer until understood |
| E99 | Six builds, 65 units, warm (`lab/measure_builds.sh`) | Totals 3.48–3.86 s; rounds of one build differ by up to 14% | Laptop time cannot rank these builds |
| E100 | Breakdown of sub14's fuzz replay | 29 cases fell to the reference path | Investigate before any scratch image of sub14 |
| E101 | Reason and common feature of the 29 | Negative latency; rows out of time order | Restore exact handling |
| E102 | `repair_trace` and file restart | 29 of 29 handled by the launcher, tables equal to sub13's | Keep |
| E103 | sub15 with 4,096-row groups, three timing comparisons | −13.7%, +4.4%, +12.5% | Inconclusive; do not upload sub15 first |
| E104 | sub16: sub15's engine with sub11's writer | Built; validated; the fuzz replay stopped at 200 of 1,318 in the validation run and completed in a separate one (§9.9.16) | Uploaded (E105) |
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

E66 to E81 are also listed, with the context of those days, in §9.7.9; E82 to E104 in §9.8.12 and §9.8.15; E105 to E133 in §9.9.12; E134 to E136 in §9.9.16. Where a row above differs from its first appearance, the row above carries the later result.

---

## 11. Limitations, risks and open work

State at the time §9.9 was written. Points that earlier versions of this section listed as open and that have since been answered are kept, with the answer.

### 11.1 Correctness

- **Sealed scenarios.** Exactness is established on the 65 public scenarios, the 30 batch sub-scenarios, 2,416 fuzz cases for the sub1 engine, and the 1,318 stored fuzz cases replayed on later builds (third item). Sealed scenarios may combine features in ways none of these do. Residual risk: a *silent* divergence in the native engine on an untested combination.
- **The uploaded images since sub7 have no fallback.** They are scratch images that hold only the launcher (§9.7.4). A scenario the launcher declines exits with status 127 and the unit scores zero; in the full image the same scenario is handed to the Python path and passes. All 71 public units are handled by the launcher in every run made. Of the 1,318 stored fuzz cases, 22 to 27 are declined, depending on the build (fourth item). Whether the Final gets a scratch image or the full image is undecided (§9.9.15).
- **Fuzz coverage by build.** The replay of the 1,318 stored cases (`native/fuzz/recheck_stored.py`, §9.7.2) gave 1,318 of 1,318 on sub6, sub7, sub8, sub9, sub10, sub11, sub12, sub13, sub14, sub17 and sub18. **sub16's replay is not in its validation log** (a separate run on the same image gave 1,318 of 1,318, §9.9.16): there it stopped at 200 of 1,318 when Docker failed and was not repeated (§9.9.4); sub17 and sub18, which are built on sub16, pass. sub15 was not replayed in full. sub19a's replay gave 1,318 of 1,318 (1,296 through the launcher, 22 handed to the Python path). sub4 and sub5 were never replayed. The 22-case re-check through `native/fuzz/recheck_launcher.py`, planned since sub4, was never run; the 1,318-case replay took its place.
- **The number of declined fuzz cases differs between builds and between runs.** Handed to the Python path: 22 (sub9), 23 (sub10 to sub13, and a launcher-only pass on sub16, sub17 and sub18: 19 with a non-boolean `protocol_enforcement`, 4 with a latency draw sensitive to the `log` implementation), 25 (full replay of sub17 and of the first sub18), 27 (full replay of sub18). The explanation, not confirmed by a targeted test, is that the helper thread draws latencies ahead of the event loop and a draw the run never consumes can still raise the sensitivity flag (§9.9.10). In a scratch image such a case scores zero. A fix exists in the source only (`native/engine/engine.cpp`, snapshot `lab/bench/engine_sub19_wip.cpp`): byte-identical on 65/65 units with the helper on and off, in no image, not fuzz-replayed. sub19a and sub19b carry sub16's helper code and therefore sub16's look-ahead, not the fix.
- **Negative latencies** make trace rows arrive out of time order. sub14 failed such runs (29 stored fuzz cases); since sub15 `repair_trace` handles them natively (§9.8.15). No public unit has a negative latency.
- **32-bit fields in the trace row (sub18 and later).** `row_fits` checks every value before it is stored; a value that does not fit stops the run, which sends the scenario to the fallback path, and in a scratch image that is a zero for the unit. All 71 public units pass, and a launcher-only pass over the stored fuzz cases on sub18 declined the same 23 as on sub16 (§9.9.10), so none of them stops for this reason.
- **From sub5 on, the output files are not byte-identical to the reference files.** They are valid Parquet files that read back as the same tables (§9.5), and the published scorer compares tables and our own declared hash (§7.9). If a sealed check compared file bytes or file hashes with the reference, every unit would fail. We found no such check in the public scorer, the README or the regression harness; the official regression passes on every validated build and every upload since sub5 has received a score.
- **Readers other than pyarrow/pandas were not tried.** The files were read with pyarrow 15.0.2 and pandas 1.5.3 only (the versions in the image and, per the upstream pins, in the scorer).
- **The writer was validated on the data we have.** Paths never exercised by any public unit: a dictionary with more than 16 entries (8-bit indices), an empty ledger, a nullable column consisting only of nulls, delta blocks whose width reaches 64 bits. A file above 2²⁰ rows *is* covered (`gb_mega_throughput`: 1,168,360 trace rows; 1,420,862 ledger rows when the ledger is written).
- **Built-in SHA-256.** Correct on every file checked (compared with `hashlib`), in both the hardware and the portable variant. A wrong hash would fail the unit, not corrupt data.
- **Event count must match exactly on every unit, Tier B included** (§2.2).
- **`log` implementation (launcher only).** The launcher uses glibc's `log` for the log-normal μ and relies on detecting sensitive draws (§7.8). The assumption that numpy's value is within 16 ulps has not been checked by a run on AVX-512 hardware. What supports it: documentation found puts the difference at about 1 ulp (§9.7.5, H52); every scored upload since sub4 computed μ with glibc on the scoring host and was scored. What to weigh against it: another team's public notes say numpy 1.26's `np.log` on AVX-512 CPUs differs from libm on about 27% of inputs (§9.9.6). A difference in many inputs is what the guard is built for; a difference larger than its margin is what it could not catch.
- **Reference traces were generated on this laptop** (no AVX-512). If the organizers' reference had been generated differently, units would fail on the host; the scores are the evidence that they do not.
- **The ledger is skipped only on the card's word.** `card_skips_ledger()` returns true only for the exact line `requires_message_ledger = false` in `/input/card.toml` (§9.8.3). The organizers confirmed that the official runner mounts the whole unit folder, so the file is present, and that writing the ledger everywhere is always safe (issue #35, §9.9.2). Batch units always get a ledger.
- **GPU device.** The organizers ask images not to set `NVIDIA_VISIBLE_DEVICES` (issue #34). We never set it. The scratch image was never run locally on a host with a GPU runtime (§9.7.4); it runs on the scoring host.
- **Packing limits.** More than 65,535 agents, more than 2³² messages in one run, or (launcher) more than 60,000 agents → fallback.
- **Typing in the launcher.** Since sub7 a whole number written as a float is accepted where an integer is expected (§9.7.2). A non-boolean `protocol_enforcement` is still declined.

### 11.2 Performance

- **What we know about the host comes from scores only.** Thirteen uploads have been scored under the new rule (§1.1, §9.8.1, §9.9.1). Per-unit results from the platform were never obtained: they need the team's login, which was asked for several times (§9.9.14). The fixed cost per container on the host is therefore still unknown. It is bounded above by 0.471 s by the leader's score (§9.8.7); a participant reports "roughly half a second" (§9.9.2), which agrees with that bound only roughly. The organizers' calibration post had not appeared when this was written.
- **Run-to-run variation on the host.** Earlier versions of this report called the host shared and its scores noisy to about 1.6%. The organizers state that Development runs on a single machine that takes only Track 3 runs, one submission at a time, and another team reports two runs agreeing to within 0.1% (§9.9.2). Our 1.6% comes from two sub4 uploads that were never checked to carry the same image (§9.4). This report records no second upload of one known digest, so we have no measurement of our own.
- **Laptop timing does not predict the host.** Memory work measured at −12.5% and −12.1% on the laptop was worth nothing there (§9.8.2); a model "fixed cost + k × laptop process time" cannot reproduce the ranking of our own builds (rms residual 3.2%, maximum 6.3%, §9.9.6); three score projections for sub17 made from laptop timing were all wrong (§9.9.8). Only ratios within one laptop session mean anything: sub16 measured 1.895 s in one session and 2.228 s in another (§9.9.3).
- **Whole-process figures measured from the unit folders include the input mount.** On this laptop the unit folders are a Windows-backed mount that adds 10 to 20 ms per run which the host does not have. This affects the figures of §9.8.3 and §9.8.15 and the `fig_*.json` files (§9.9.3). `lab/true_p.py` copies the inputs to memory first.
- **Hardware counters are the stable local instrument** (instructions ±0.00%, branch misses under 0.5%, cycles 0.5–2% on one thread, §9.9.3). They describe the simulation thread and say nothing about thread placement on the host.
- **Threads on the host.** The latency helper thread is worth 9.5% of score on the sub16 binary (same binary, one environment variable; §9.9.8). Writer threads during the run were worth 1.6% on the sub17 binary. Why sub17, whose helper starts at engine creation, scored 3.6% below sub16 although its engine is better is **not established**; the placement explanation in §9.9.8 is an untested guess. sub18 with its own sleeping helper was never uploaded.
- **The 4-CPU quota.** It is a CFS quota, not pinned cores. Locally no throttled period was counted (§9.7.3, §9.8.5). On the host this cannot be read.
- **Where the time goes now.** On the largest unit, one thread, sub17 test build: `Engine::run` with inlined handlers 21.7% of cycles, latency draws about 27.5%, output encoding and SHA-256 about 20%, `sift_down` 5.8% (§9.9.3). The engine review's remaining ideas are listed in §9.9.6; the largest ("lazy passive receipts", its estimate 20–28%, 12–20 hours, high risk) was not attempted.
- **Where `/output` lives.** It is a bind mount of a host directory, per the toolkit's DEVELOPMENT-RUNTIME document and the public harness (§9.7.1, §9.9.6). The filesystem behind it is not known. Output size was not a major term in the one test we have (sub7, §9.7.6).
- **Output size.** Since sub10 the 65 public units write about 95 MB in total (§9.8.15); sub5's uncompressed files (758.7 MB) are history.
- **How high the score can go.** With zero process time the score is 108,853 ÷ c for a fixed cost of c seconds per container (§9.8.7); c is not known. From sub16's score, 220,000 needs the host process time cut by 27% (if c is 0.36 s) to 46% (0.44 s), and 230,000 by 41% to 68% (score-model agent, §9.9.6). The leader has stood at 231,024 since sub4 was scored. The 300,000 asked for is not in sight.
- **Machine noise** (§16.4): a "calibration" run was thrown away because the laptop was two to three times slower than in the earlier session and two rounds of one binary differed by up to 45% (§9.9.3).
- **The Final differs from Development in what is timed**: Docker's `State.StartedAt → FinishedAt` instead of create → remove, five runs per unit (a warm-up and four counted), 300 s per run, 4 CPUs, 16 GiB, on the same machine (§2.2, §9.9.2). The organizers' rehearsal was postponed. We have not rehearsed the five-run protocol with the upstream `throughput/timer.py`; repeat-run byte stability (three runs of every scenario) is part of every validation.

### 11.3 Process

- **Upload budget.** 5 per day and 23 per person in total (competition page; the 20 in §9.8.7 was a toolkit document's figure). After upload 977400 (sub19a) the team had used 22: one remained (§9.9.16). A held upload still consumes an attempt (issue #20). The last Development runs must start by the Development deadline and the Final takes one submission (§9.7.5).
- **Changes were bundled into single uploads more than once** (sub11, sub13, sub17), and each time the score could not be attributed (§9.8.14, §9.8.15, §9.9.14).
- **No native Linux machine was used for measurement** (§9.7.1, point 6).
- **Image digests are not bit-reproducible.** Rebuilding gives a different image ID. Reproducibility is defined by output hashes (§12.6).
- **The reproduction kit was hardened because it failed**: twice the Docker VM died mid-run (§16.6). On a machine with more memory `repro.sh all` should suffice; on this one `repro/run_resilient.sh` was needed.
- **Some raw output directories cited in older sections were deleted** (§9.8.11); their summary logs remain in `lab/bench/`.
- **Old sections describe an obsolete target.** §5–§9.3 are kept as the record of the work under the old rule.

### 11.4 Open work, in the order we would do it

1. sub19a (sub18's engine with sub16's helper) is validated and pushed (§9.9.9): upload it and read the score. sub19b: validation, if it is to be used.
2. Decide the Final image: scratch (a declined scenario scores zero) or full (exact Python fallback, slower start).
3. Put the sensitivity-flag fix of §9.9.10 into an image and replay the fuzz corpus on it; complete a fuzz replay for whichever build goes to the Final.
4. Obtain per-unit host results through the team's login, to fix the per-container cost.
5. Establish why a helper thread started at engine creation is worth less on the host than one woken at run start.
6. Rehearse the Final protocol with the upstream `throughput/timer.py` (5 runs, same seed, byte-identical outputs across repeats).
7. A fresh fuzz campaign against the current engine, the launcher's declining paths and the writer (random tables against pyarrow's reader). Not done since the sub1 campaign.
8. A direct comparison of numpy's and glibc's `log` on an AVX-512 machine.
9. Engine ideas not implemented: bottom-up pop, noise-trader draws on the helper thread, prefetching, lazy passive receipts (§9.9.6).

---

