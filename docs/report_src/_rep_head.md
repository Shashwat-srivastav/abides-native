# Agenthon 2026 · Track 3 (Accelerated Market Simulation): engineering report and reproduction guide

**Author:** Shashwat Srivastava (Independent Researcher) · **Team:** S2WISH (team 36)
**Track verbs:** `simulate`, `simulate-batch`
**Ranked metric:** events/sec, gated on exact semantics
The previous version is kept as `docs/report_src/REPORT_v1.md`. A shorter, illustrated version for publication is in `paper/` (`zenodo_report.pdf`, built by `paper/make_figures.py` and `paper/build_report.py`).

This document records what we built, why each decision was made, every measured result (including the experiments that failed), what was investigated and what it explained, the hypotheses tested and their outcomes, the limitations, and exactly how to reproduce the results. Every number comes from a run in this project; anything not measured or not yet done is labelled as such. The reproduction kit lives in [`repro/`](repro/) and is described step by step in **§12**.

---

## Contents

0. [Read this first: status](#0-read-this-first-status)
1. [Results at a glance](#1-results-at-a-glance)
2. [The competition contract: what counts](#2-the-competition-contract-what-counts)
3. [Architecture of the submission](#3-architecture-of-the-submission)
4. [Method: how decisions were made](#4-method-how-decisions-were-made)
5. [Baseline reconnaissance](#5-baseline-reconnaissance)
6. [Phase A: exact speedups inside Python ABIDES](#6-phase-a-exact-speedups-inside-python-abides)
7. [Phase B: the bit-exact native engine](#7-phase-b-the-bit-exact-native-engine) (7.7 engine rewrite, 7.8 no-Python launcher, 7.9 built-in Parquet writer)
8. [Robustness: differential fuzzing](#8-robustness-differential-fuzzing)
9. [Submission rounds: sub1 → sub19](#9-submission-rounds-sub1--sub19) (9.7: after sub5 was scored, sub7 to sub9; 9.8: sub9 to sub13 on the host, sub14 to sub16 built; 9.9: sub16 on the host, sub17, sub18, sub19 and five more scores)
10. [Complete experiment log](#10-complete-experiment-log)
11. [Limitations, risks and open work](#11-limitations-risks-and-open-work)
12. [Reproduction guide](#12-reproduction-guide)
13. [File map](#13-file-map)
14. [Appendix: pinned versions, checksums, glossary](#14-appendix-pinned-versions-checksums-glossary)
15. [Hypothesis register](#15-hypothesis-register)
16. [Investigations: what was looked into and what it explained](#16-investigations-what-was-looked-into-and-what-it-explained)
17. [Evidence status: verified, partly verified, not verified](#17-evidence-status-verified-partly-verified-not-verified)

---

## 0. Read this first: status

**Where things stand** (details and sources in §9.9):

- **Best score: 203,394.4709** (sub16, scratch image `native-v16m`, upload 975649). It is +7.6% over the previous best, sub11's 189,018.28. **Board position: rank 10 of 50 teams**. The leader (fuzz) is at 231,024.2407 and nine teams are above 206,000. The board keeps a team's best score.
- **Five more uploads, none above sub16:** sub19a (sub18's engine with sub16's helper code) 199,057.7311; sub17 without writer threads 196,164.8389; sub17 with writer threads 199,285.2183; the sub16 binary with the latency helper thread switched off 185,818.3472; the sub18 binary with the helper off 193,962.2805.
- **What those scores established** (§9.9.8): the latency helper thread is worth +9.5% on the host (same binary, one environment variable); sub18's engine is 4.4% better than sub16's at equal helper setting; writer threads during the run gained 1.6% on sub17; sub17 lost 3.6% against sub16 although its engine is better, and by elimination the cause is its changed helper start-up. The mechanism is not established.
- **The combination the scores pointed to did not beat sub16: sub19a**, sub18's engine with sub16's helper code restored. It is byte-identical to sub16's output on 65/65 single units and has passed the full validation: tables 65/65, repeat-run bytes 65/65, batch 6/6, official regression 65/65, fuzz replay 1,318 of 1,318 (1,296 through the launcher, 22 handed to the Python path). Its scratch image is binary-identical to the validated build, passed its own checks and is pushed as `native-v19a`. It scored **199,057.7311** (upload 977400), 2.1% below sub16: the helper code that is worth 9.5% on sub16's engine is worth 2.6% on sub18's (193,962 → 199,058), so the two gains did not add up (§9.9.16). sub19b (the same with the older, branching heap step) passed the full validation in its full image and was never uploaded.
- **Upload budget: 5 per day and 23 per person in total** (read from the public CodaBench competition API). 22 are used. **One upload remains.** The total of 20 used in §9.8 came from a toolkit document and was wrong.
- **The host, as the organizers describe it** (§9.9.2): Track 3 Development runs on a single machine that takes only Track 3 runs, one submission at a time, and it is the machine the Final is timed on. The Final gives five runs per unit (a warm-up and four counted), 300 s per run, 4 CPUs, 16 GiB.
- **Measurement** (§9.9.3): the unit folders on this laptop are a slow Windows mount, so every "whole process" figure taken from them since sub4 includes 10–20 ms per run that the host does not have. Hardware counters on one thread are now the local instrument. Laptop timing did not predict the host: three score projections made from it were all wrong (§9.9.8).
- **A correctness finding whose fix has not shipped** (§9.9.10): the number of fuzz cases handed to the Python path varies between runs (23, 25, 27). In a scratch image such a case would exit with an error and the unit would score zero. No public unit is affected. A fix is in the source only and has not been fuzz-replayed.

**Open decisions:**

| Decision | State |
|---|---|
| The remaining upload | sub19a took the 22nd. For the last one an image of the sub16 binary with writer threads on (`T3_TRAIL=1`) was built and checked locally; not pushed or uploaded when this was written (§9.9.16) |
| Final image: scratch (a declined scenario scores zero) or the full image with the exact Python fallback | Undecided |
| The fix of §9.9.10 | In no image; not fuzz-replayed |
| Fixed per-container cost on the host | Unknown; at most 0.471 s (§9.8.7). Per-unit host results were never obtained |

The rest of this section is the status as it was written before sub16 was scored, kept where it is still true and corrected where it is not.

**The scoring rule changed, and it changes what the earlier results mean.**

- until the scoring change the Development board ranked a submission's *self-reported* events/sec for the simulation loop only, capped at 10,000,000 per unit. Sections 5–9.3 were written under that rule. Under it we went 4,862 → 4,260,093 → 8,340,072.
- Since **the scoring change** the board ranks, per unit, the **verified event count divided by the container time measured by the organizers' harness, from creating the container to removing it, one run per unit** (§2.2). Runs made before that time are not ranked. Our 8.34M is therefore history, not a current score.
- When sub4 was uploaded the Track 3 leader stood at **212,671**; nobody is near 10M and, with container start-up inside the measured time, nobody can be.
- **sub4, built for the new rule, scored 153,825 (rank 9 of 17 scored teams)**; an earlier upload the same day scored 151,387 (§9.4). The leader had meanwhile moved to 231,024.

- **sub5 scored 181,496**, +18% over sub4 and a little below our pre-upload estimate of 185–220K (§9.5). It replaces Arrow's Parquet encoder, which turned out to be 50–63% of each unit's process time, with a built-in writer (§7.9). On this laptop the 65 public units take 3.41 s of process time in total against sub4's 10.20 s. Fitting our overhead model to both scores gives a ceiling of about 209K, which the leader's 231,024 already exceeds, so the model is missing something; §9.5 lists the candidates (output size first). The model was later shown to be wrong (§9.8.7, §9.9.6).
- **sub5's output files are no longer byte-identical to the reference files.** They are valid Parquet files that read back as exactly the same tables, which is what the published scorer compares; the organizers' regression harness passes 65/65. The risk this leaves is stated in §11.1.
- **sub6** (smaller files through delta encoding; about 4% less process time than sub5) is built and validated locally and not pushed (§9.6).
- **The asked-for 300,000** is beyond the ceiling our model gives for this scoring rule (221–324K before sub5 was scored; about 209K when fitted to both scores, a fit the leader's score contradicts), because the fixed container start/stop time is in every unit's denominator (§9.5, §16.10).

- **The scratch image scored 184,858** (+1.9% over sub5). It is the sub7 program in a 2.2 MB single-layer image without Python. Image shape and output size are therefore minor factors on the scoring host (§9.7.6). The stored fuzz corpus was replayed at last: 1,318 of 1,318 cases reproduce the recorded reference (§9.7.2). sub8 and sub9 cut page faults by 66% and process time by a measured 12.5% and 12.1% (§9.7.7, §9.7.8); sub8 was never scored, and sub9 was scored later the same day (next item).

- **sub9 scored 183,420, sub10 188,687 and sub11 189,018** (§9.8). The memory work of sub8 and sub9 gained nothing on the scoring host. Leaving out the message ledger on the six units whose card does not require it (sub10) gained 2.9%, about twice the estimate. Switching huge pages and up-front buffer population off (sub11) changed nothing measurable there, although it costs about 70% on the laptop.
- **The local measurement method was wrong** (§9.8.5). The host runs each unit once in a fresh container; we had timed warm repeated runs inside one container. Timed as fresh containers, the same program is two to five times slower on the laptop with a spread as large as the mean, and the laptop's Docker VM has under 3 GB of memory. Local timings of anything related to memory or threads are not evidence about the host. Later the inputs were also found to sit on a slow mount (§9.9.3).
- **The fitted score model of §9.5 is wrong** (§9.8.7): the leader's 231,024 requires a fixed container cost of at most 0.47 s, not the 0.55 s the fit gave.
- **Development uploads are capped: 5 per day and 23 per person in total** (read from the CodaBench competition API). Earlier we took the total to be 20 from `toolkit-v2.5.1/docs/DEVELOPMENT-RUNTIME.md`; before that we had planned with the daily limit only.
- **sub13** (streamed output, pooled threads, less allocation churn) **scored 184,047**, 2.6% below sub11, for reasons we could not isolate: it bundled five changes (§9.8.15). **sub14** builds the trace in its final order during the run; its validation exposed 29 fuzz cases with a negative latency that it could no longer handle natively, repaired in **sub15**, which also writes the files during the run. **sub16** puts sub15's engine behind sub11's writer, to change one thing from what was then the best-scoring build; it scored 203,394 (§9.9.4). The reading of sub13 as "a streaming writer loses" is contradicted by sub17's two scores (§9.9.8).
- **This document now lives at `docs/REPORT.md`**; some output directories cited in earlier sections were deleted to free disk space (§9.8.11).

What this means for reading the report:

| Part | Status |
|---|---|
| Correctness work (§7.1–7.3, §8) | Fully relevant: outputs must still match the reference exactly |
| Simulation-loop throughput numbers (§1.3, §7.4, §9.1–9.3) | Real measurements, but of a quantity that is no longer ranked |
| End-to-end container time (§7.6, §7.8, §7.9, §9.4–9.6) | The quantity that is ranked now |
| "Byte-identical" in §1.2, §7, §8, §9.1–9.4, §12.4 | Applies to sub1–sub4 and to the Python paths of every image. sub5/sub6 are checked by table equality (§9.5) |
| "10M" goal mentioned in older sections | Obsolete |
| Laptop whole-process times taken from the unit folders (the `fig_*.json` files and the totals of §9.8.15) | Include 10–20 ms per run of input-mount time that the host does not have (§9.9.3) |
| "Shared host" and "busy host" as explanations of score differences (§1.1, §9.4, §9.8.2) | Written before the organizers' statement that the Track 3 host takes only Track 3 runs, one submission at a time (§9.9.2). Not established for the dates concerned |
| Upload total of 20 (§9.8.7, §9.8.12, §9.8.14) | Wrong: 23 (§9.9.1) |
| Score-model fits and projections (§9.5, §16.10, and the three projections of §9.9.8) | Refuted by scores |

---

## 1. Results at a glance

### 1.1 Leaderboard

Old rule (self-reported simulation rate, capped at 10M per unit; no longer ranked):

| Submission | Image digest | Dev score | Approx. rank at the time (of 38) |
|---|---|---:|---:|
| Original baseline (unmodified ABIDES) | `c4f8a635…` | 4,862 | 35 |
| **sub1**: native engine | `sha256:8d4db7f4…e030fe7b` | **4,260,093** | ~20 |
| **sub2**: page pre-faulting, timing scope, batch fix | `sha256:81e6fa40…acc2d7a` | **8,340,072** | ~15 |
| **sub3**: branch-free event heap | `sha256:67e3086d…fc60c7` | pushed, never uploaded | — |

New rule (events ÷ whole-container time), board as fetched before our upload:

| Rank | Score |
|---:|---:|
| 1 | 212,671 |
| 2 | 204,508 |
| 3 | 198,767 |
| 8 | 181,826 |
| 9 | 129,722 |
| 11 | 127,556 |
| 12 | 23,180 |
| 15 | 12,081 |

| Submission | Image digest | Score under the new rule |
|---|---|---|
| **sub4**: rewritten engine + no-Python launcher | `sha256:697ae5de…869d85c7` | **153,825** (upload 968642) and **151,387** (upload 968635), both on the same day; **rank 9 of 17** |

| **sub5**: built-in Parquet writer, static launcher, parallel output | `sha256:eb90d781…f117ab06` | **181,496** (upload 969765); pre-upload model estimate was 185–220K |
| **sub6**: sub5 + delta-encoded integers | local image `67e474a28959` | not pushed |
| **sub7 (scratch)**: sub6 + direct ledger encoding + float-typed integers accepted; 2.2 MB one-layer image, no Python | `sha256:2b97366d…6b3e4cf0` | **184,857.72** |
| **sub9 (scratch)**: sub7 + memory work (§9.7.7, §9.7.8) | `sha256:9e8206c3…ce61d3a57` | **183,419.75** (upload 970940) |
| **sub10 (scratch)**: sub9 + no ledger on the six units whose card does not require one | `sha256:3b27783e…34254a441` | **188,687.15** (upload 971069) |
| **sub11 (scratch)**: sub10 + profile-guided build + earlier exit, memory switches off | `sha256:47c37844…d7cfe8128` | **189,018.28** (upload 971164) |
| **sub13 (scratch)**: sub11 + streamed output, pooled threads, scratch reuse, thread cap | `sha256:1ca74d1c…3784f86f0` | **184,046.62** (upload 971360) |
| **sub14**, **sub15**: trace in final order during the run; files written during the run (§9.8.9, §9.8.10, §9.8.15) | local images | not pushed |
| **sub16 (scratch)**: sub15's engine with sub11's writer, memory switches off (§9.9.4) | `native-v16m`, `sha256:96856191…dfcdbd83` | **203,394.4709** (upload 975649); **best score** |
| **sub17 (scratch), writer threads off**: sub16 + branch-free heap step + changed helper start-up (§9.9.5) | `native-v17n`, `sha256:6d1a0d8f…0e03c192` | **196,164.8389** (upload 976478) |
| **sub17 (scratch), writer threads on** (`T3_TRAIL=1`) | `native-v17t`, `sha256:998c2f45…bb81ecd8` | **199,285.2183** (upload 976489) |
| **sub16 binary, latency helper thread off** (`T3_LAT_THREAD=0`); a host experiment | `native-v16-helper-off`, `sha256:31cb73d3…f8788f5c` | **185,818.3472** (upload 976768) |
| **sub18 binary, helper thread off**: sub17 + seven engine changes (§9.9.7); a host experiment | `native-v18-helper-off`, `sha256:b437b608…5feaf6ce` | **193,962.2805** (upload 976794) |
| **sub18 (scratch), helper sleeping** | `native-v18-helper-sleeping`, `sha256:2f9c4d39…fae38ea7` | pushed, never uploaded |
| **sub19a (scratch)**: sub18's engine with sub16's helper code (§9.9.9) | `native-v19a`, `sha256:abca67f1…53dcf434` | **199,057.7311** (upload 977400) |
| **sub19b**: the same with the branching heap step (§9.9.9) | local full image | full validation passed (fuzz 1,318 of 1,318); no scratch image, not pushed |

Latest board (50 teams; the board keeps a team's best score):

| Rank | Team | Score |
|---:|---|---:|
| 1 | fuzz | 231,024.2407 |
| 2 | VerityLovityFalsityCruelty | 222,058.1706 |
| 3 | abc123 | 221,088.2954 |
| 4 | IMAnonymous | 215,963.1445 |
| 5 | Yan Su | 214,393.6369 |
| 6 | "recently rejected" | 211,718.1931 |
| 7 | Proof of Alpha | 211,712.3699 |
| 8 | Cornfield Chase | 210,201.3605 |
| 9 | Warkop PuteraPrakoso | 206,152.3034 |
| **10** | **S2WISH** | **203,394.4709** |

Uploads used: 22 of 23 (5 per day); one remains.

Board when sub4 was scored (fetched after the upload): 1st 231,024; 2nd 212,671; 8th 181,826; **9th S2WISH 153,825**; 10th 129,722; 12th 127,556; 13th 31,733; 17th 12,081. The two uploads were made minutes apart and the team reports them as the sub4 submission; the 1.6% difference between them was read at the time as the run-to-run variation of a single run per unit on a shared host. That reading is not established: the organizers have since stated that the Track 3 host takes only Track 3 runs, one submission at a time, and a participant reports two runs agreeing to within 0.1% (§9.9.2). We made no numeric prediction for sub4 beforehand, because the container create/remove time on the organizers' host could not be measured here.

### 1.2 Correctness

| Check | sub1 | sub2 | sub3 | sub4 |
|---|---|---|---|---|
| Organizer's `run_regression.py` on the 65 public scenarios | 65/65 pass | 65/65 pass | 65/65 pass | **65/65 pass** (upstream harness `bffb572`, toolkit v2.5.1) |
| Byte-identical `trace.parquet` + `message_trace.parquet` vs baseline (SHA-256) | 65/65 | 65/65 | 65/65 | **65/65** (launcher binary; see §17 for which runs used the image) |
| Batch units: every sub-scenario byte-identical | 30/30 | 30/30 | 30/30 | **30/30** (launcher binary in the dev container); 1 unit re-checked through the image |
| Differential fuzzing, historical failures | 22/22 identical | — | — | not run |

Correctness of sub5 and sub6, which is judged differently (§9.5):

| Check | sub5 | sub6 |
|---|---|---|
| Both output files read back as the same tables as the byte-verified sub4 files; declared hashes are the files' real hashes; 65 scenarios | 65/65 | 65/65 |
| The same for the 6 batch units (30 sub-scenarios), run under the organizers' runtime restrictions | 6/6 | 6/6 |
| Organizer's regression (upstream harness `bffb572`, toolkit v2.5.1) | 65 passed, 0 failed, 0 errored | 65 passed, 0 failed, 0 errored |
| Same bytes in 3 repeated runs of each scenario | 65/65 | 65/65 |
| Byte-identical to the baseline's Parquet files | **No, by design** | **No, by design** |
| 22 stored fuzz cases | never run; replaced by the 1,318-case replay (sub6: 1,318/1,318, §9.7.2) | same |

Correctness of the builds (§9.9), judged as sub5 and sub6 are:

| Check | sub16 | sub17 | sub18 | sub19a |
|---|---|---|---|---|
| Tables, 65 scenarios | 65/65 | 65/65 | 65/65 | 65/65 |
| Same bytes in repeated runs | 65/65 | 65/65 | 65/65 | 65/65 |
| Batch units under the runtime restrictions | 6/6 | 6/6 | 6/6 | 6/6 |
| Organizer's regression | 65/65 | 65/65 | 65/65 | 65/65 |
| Fuzz replay of 1,318 stored cases | crashed at 200 in the validation run (Docker "unexpected EOF"); a separate replay on the same image gave 1,318/1,318 (1,296 launcher, 22 Python path; `lab/bench/val_sub16/fuzz.log`) | 1,318/1,318 (1,293 launcher, 25 Python path) | 1,318/1,318 (1,291 launcher, 27 Python path) | 1,318/1,318 (1,296 launcher, 22 Python path) |
| Scratch image: binary identical, batch 6/6, regression 65/65, no-ledger units 6/6 | yes (`sub16m`) | yes (`sub17n`, `sub17t`) | yes (`sub18n`, `sub18h0`) | not done when this was written |

sub19b is byte-identical to sub16's output on 65/65 single units and has not been validated further.

### 1.3 Simulation-loop throughput (self-reported, this laptop; the old ranked quantity)

| | Baseline | sub1 | sub2 | sub3 |
|---|---:|---:|---:|---:|
| 61 standard scenarios, mean events/s | ~6.1K | ~4.2M | 6.44M | 6.21M official run; 5.9–6.3M in A/B |
| Median speedup vs baseline (official harness) | 1× | — | 1,083× | 1,029× |
| Batch units | ~10–40K | ~10–46K | 2.3–19.8M | as sub2 |

For the sub4 engine the loop cost was measured with CPU counters instead of wall time (§7.7): mean over the 65 scenarios went from **559 to 352 cycles per event (−37%)** and from 1,010 to 576 instructions per event (−43%).

Absolute wall-clock numbers on this laptop move ±15–20% between runs (more under memory pressure), which is why §7.7 switched to cycle counts.

### 1.4 Whole-process time (the new ranked quantity, minus container overhead)

Time for one `simulate` process inside a running container on this laptop, same scenario, Python path versus the launcher (single runs; this machine is noisy):

| Scenario | Events | Python path (sub3-style) | Launcher (sub4) |
|---|---:|---:|---:|
| `s001_price_time_priority` | 604 | 1,369 ms | 33–45 ms |
| `eq_deterministic_baseline` | 10,669 | 1,523 ms | 55–206 ms |
| `mp07_heavy_flow_oldest` | 72,036 | 1,948 ms | 146–354 ms |
| `gb_horizon_240s` | 555,032 | 2,498 ms | 1,389–1,924 ms |
| `gb_mega_throughput` | 1,168,360 | 7,921 ms | 2,151–4,423 ms |

The table above is from single runs on a swapping machine. Later measurements use the best of 5 runs with outputs on `/dev/shm` (`native/engine/bench_units.py`), 4 CPUs:

| Scenario | Events | sub4 | sub5 | sub6 |
|---|---:|---:|---:|---:|
| `st01_liquidity_churn_baseline` | 72,034 | 98 ms | 30 ms | 30 ms |
| `mr_checkpoint_cadence_fine` | 161,055 | 211 ms | 57 ms | 51 ms |
| `mp05_cancel_churn_newest` | 240,829 | 287 ms | 77 ms | 77 ms |
| `gb_pop_128_agents` | 303,603 | 391 ms | 130 ms | 124 ms |
| `mr_deep_book_state_size` | 319,488 | 362 ms | 102 ms | 100 ms |
| `mr_cancel_replace_churn` | 322,007 | 336 ms | 117 ms | 97 ms |
| `gb_highfreq_40hz_60s` | 500,530 | 526 ms | 217 ms | 194 ms |
| `gb_horizon_240s` | 555,032 | 588 ms | 232 ms | 209 ms |
| `gb_pop_horizon_scale` | 725,591 | 746 ms | 318 ms | 290 ms |
| `gb_mega_throughput` | 1,168,360 | 1,230 ms | 530 ms | 485 ms |
| **All 65 units, sum of the best time per unit** | 7,465,846 | **10.20 s** | **3.41 s** | **3.28 s** |

Output size over the 65 units (both files): sub4 289.2 MB, sub5 758.7 MB, sub6 135.8 MB.

Host-measured `docker run` wall time, median of 3 interleaved runs, same hashes from both images:

| Scenario | Events | sub3 | sub4 |
|---|---:|---:|---:|
| `eq_deterministic_baseline` | 10,669 | 6.19 s | 2.58 s |
| `mp07_heavy_flow_oldest` | 72,036 | 5.08 s | 2.20 s |
| `mr_deep_book_state_size` | 319,488 | 8.02 s | 4.97 s |
| `gb_mega_throughput` | 1,168,360 | 19.30 s | 12.36 s |

These `docker run` times include Docker Desktop's Windows overhead (about 2 s per run, plus slow bind-mount writes for the large outputs). They show direction and ratio, not what the organizers' Linux host will measure.

Measurements (§9.9.3). A system-call trace showed that the unit folders are a slow Windows mount: 10–20 ms per run of every whole-process figure taken from them is input reading that the scoring host does not have. `lab/true_p.py` copies the inputs to memory first. Process time over all 71 units (65 single and 6 batch), best of 5, one session:

| Build | Total |
|---|---:|
| sub16 | 1.895 s |
| sub17, writer threads off | 1.627 s |
| sub17, writer threads on | 1.348 s |

In a later, slower session the same measurement gave sub16 2.228 s, sub17 (writer threads off) 2.152 s and sub18 1.876 s, so only ratios within one session mean anything. On the host the order was different: sub16 scored above both sub17 variants (§1.1).

---
