# Agenthon 2026 · Track 3 (Accelerated Market Simulation): engineering report and reproduction guide

**Author:** Shashwat (Independent Researcher) · **Team:** S2WISH (team 36)
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
## 2. The competition contract: what counts

| Rule | Consequence for us |
|---|---|
| **Tier-A gate**: exact event count, exact fill sequence (order_id, price, size), exact coverage, timestamps within ±1 µs, Kendall-τ ≥ 0.999 | Any reordering, RNG drift or dropped event zeroes the unit. |
| **Tier-B gate**: return-distribution KS and average-spread thresholds | Statistical realism must be preserved. |
| **Stylized facts**: KS ≤ 0.08, ACF(\|r\|) RMS ≤ 0.12, Hill ≤ 1.5, depth-JS ≤ 0.10 | Same. |
| **Message ledger** (`message_trace.parquet`) where the scenario card requires it | Message-level causality must match. |
| **Score = mean over all units**; a failed unit contributes 0 | One broken sealed unit costs more than any speedup. |
| **Dev board until the scoring change**: self-reported `wall_clock_sec`, consistency-checked against `n_events` | Our timing scope must be honest and well defined (§2.1). |
| **Dev board since the scoring change**: events ÷ container time measured by the harness | The whole process is timed (§2.2). |
| **Final**: Docker `State.StartedAt → FinishedAt`, five runs per unit, median of the four counted (§2.2) | Container start-up and imports also matter (§7.6). |

**Our correctness standard is stricter than the gate:** byte-identical outputs against the baseline image. With identical bytes, every Tier-A, Tier-B, stylized-fact and ledger check passes by construction, whatever the hidden thresholds are.

### 2.1 Timing scope under the old rule (honesty rule)

The reference adapter (`abides_fork/simulate.py`) times only `abides.run(config)`:

```
build_config(scenario)   # untimed: config parsing, RNG seeding chain, agent construction
t0 = perf_counter()
end_state = abides.run(config)      # TIMED
wall = perf_counter() - t0
extract_trace(...), to_parquet(...) # untimed: output assembly and writing
```

We mirror this exactly with a three-call engine API: `t3_create` (untimed) → `t3_simulate` (**timed**) → `t3_finish` (untimed). For batch units, each worker simulates all its sub-scenarios first and writes outputs afterwards. The reported wall time is the real elapsed time of the parallel simulation phase. If any sub-scenario falls back to ABIDES, the whole batch is timed end to end instead (§7.5).

### 2.2 The scoring change

Source: organizer post on `Agenthon-2026/track3-simulation-public` issue #2 and the README at upstream commit `bffb572` ("On the Development board your score is measured by the organizers' harness…"). Both were read directly; the leaderboard at agenthon.net was fetched the same day.

| Item | Old rule (until the scoring change) | New Development rule | Planned Final |
|---|---|---|---|
| Numerator | Self-reported `n_events` | Verified row count of the trace (batch: total over markets) | Same |
| Denominator | Self-reported `wall_clock_sec` (our scope: the event loop) | Container time measured by the harness, **create → remove** | Docker `State.StartedAt → FinishedAt` |
| Runs per unit | 1 | 1. The organizers state that Track 3 Development runs on a single machine that takes only Track 3 runs, one submission at a time, and that the Final is timed on the same machine (issue #34; §9.9.2). This table first said "on a shared host" | 5; first discarded; median of 4 |
| Cap | 10M per unit | None in the published scorer (not relevant at these magnitudes) | Plan value not published |
| Self-reported rate | Ranked | Only consistency-checked (±5% of `n_events ÷ wall_clock_sec`; refused above 1e9 per market) | Same |
| Event count | Tier-A exact | Must equal the reference **exactly on every unit, Tier B included** | Same |
| Resources | — | 4-CPU quota (`--cpus=4`, not pinned), 16 GiB, `runc`, read-only root, 64 MiB noexec `/tmp`, uid 65534, 256 PIDs | Dedicated Xeon Platinum 8570 host, 300 s per run |
| Output | — | Each file and the total ≤ 256 MiB | Same |
| Image | Interface label | Interface label; must stay pullable | Additionally no Docker `VOLUME` |

Consequences:

1. **Fixed per-run cost dominates.** For a 10,669-event unit, every 100 ms of start-up is worth more than the entire simulation (about 4 ms). Interpreter start-up plus numpy and pyarrow imports were the largest cost we controlled (§7.8).
2. **Everything in the process is timed** — config parsing, buffer set-up, simulation, output assembly, Parquet encoding, hashing, file writes and exit. The earlier split into timed and untimed phases (§2.1) no longer buys anything on the board; it remains only in the self-reported `wall_clock_sec`, which still follows the reference adapter's scope.
3. **The score is a plain mean of per-unit rates**, so units with many events and a short run time weigh the most.
4. **The container overhead is common to all teams** and we cannot measure it locally.

The local rules checkout used for §5–§9.3 was at commit `4cc7882`. Comparing it with upstream `bffb572`: the 65 scenario files and the 6 batch units are unchanged; one example unit (`t3-EXAMPLE-vectorized-matching`) was removed (72 → 71 units); the reference adapter's only code change is `date_ns = int(pd.to_datetime(_DATE).value)` instead of `.to_datetime64()`, which yields the same nanosecond value with pandas 1.5.3. Earlier validation therefore remains valid.

---

## 3. Architecture of the submission

*(This section describes sub4 to sub6. From sub7 on, the uploaded images are scratch images that hold only the launcher: the two Python layers shown below are absent from them and a declined scenario exits with status 127 (§9.7.4). The full image with all three layers is still built and is the one every long validation runs on. Later changes to the engine and the writer are in §9.7 to §9.9.)*

sub4 (the first image scored under the new rule), with the sub5/sub6 differences marked:

```
docker run <image> simulate --config /input/scenario.json --out /output/trace.parquet
        │
        ▼
 /usr/local/bin/simulate            (C++ launcher, native/engine/launcher.cpp; no Python)
        │  1. parse the scenario JSON (own strict parser)
        │  2. build the engine config: the same expressions as abides_fork/config.py
        │  3. engine: t3_create → t3_simulate → t3_finish        (engine.cpp compiled in)
        │  4. write trace.parquet and message_trace.parquet in two threads
        │       sub4:      libarrow/libparquet from the pyarrow wheel, pyarrow's writer settings
        │       sub5/sub6: built-in writer (pq_fast.hpp); output assembly split per file (§7.9)
        │  5. SHA-256 (sub4: libcrypto; sub5/sub6: sha256.hpp), events.json, one JSON line on stdout
        │
        └─ if it is not certain about ANYTHING  ──►  exec  python -m t3native.cli   (sub3 path)
                                                          │
                                                          └─ on any exception ──► abides_fork.simulate
                                                                                  (original ABIDES)
```

`simulate-batch` is the same binary under a second name: it runs the sub-scenarios on up to 4 threads in one process and writes `batch_events.json`; if any sub-scenario needs the Python path, the whole batch is handed to `python -m t3native.batch`.

Three layers, each slower than the one above. All three produce the same tables; the two Python layers also produce the reference's exact file bytes, and so does the launcher in sub4:

| Layer | Used when | Start-up cost |
|---|---|---|
| Launcher (C++) | Plainly typed scenario inside the certified numeric domain (and, in sub5/sub6, outputs below 240 MiB) | sub4: a dynamic load of libarrow/libparquet/libcrypto. sub5/sub6: none (static binary) |
| Python native path (`t3native`, ctypes → `libt3engine.so`) | Launcher declines (list in §7.8) | Python + numpy + pyarrow imports |
| ABIDES reference (`abides_fork`) | Engine declines or raises | Additionally pandas + ABIDES |

Components:

- **`engine.cpp`** (`native/engine/`, 1,503 lines in sub4; 1,519 in sub5, 1,549 in sub6) reimplements the kernel, exchange, order book, the four agent types, the oracle, the latency model, the message ledger and the trace row ordering.
- **`np_random.hpp`** (`native/rng/`) reproduces numpy 1.26 `RandomState` draw for draw.
- **`launcher.cpp`** (`native/engine/`, 785 lines in sub4, 789 in sub5/sub6) is the entry point described above.
- **`pq_fast.hpp`** and **`sha256.hpp`** (`native/engine/`, sub5 onward) are the built-in Parquet writer and SHA-256 (§7.9).
- **`t3native/`** (Python) and **`abides_fork/`** are unchanged from sub3 and serve as the fallback layers.

The image is built by a two-stage `sub/Dockerfile`:
1. Build stage: `g++` compiles `libt3engine.so` and the launcher (`-O2 -std=c++17 -ffp-contract=off -pthread`); the launcher links `libparquet.so.1500`, `libarrow.so.1500` (from `pip install --no-deps pyarrow==15.0.2`) and `libcrypto.so.3`, with an rpath to the pyarrow directory. From sub5 the launcher is compiled `-static` with no external libraries, and the build stage no longer installs pyarrow.
2. Runtime stage: `python:3.11-slim` with the pinned ABIDES stack, our overlays, `t3native`, the `.so`, precompiled bytecode, and the launcher installed as both `simulate` and `simulate-batch`.

Before sub4 (sub1–sub3), `simulate` was a shell shim running `python -m t3native.cli`, and `simulate-batch` used 4 worker processes.

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

| 4 | | Next step under the new scoring: ship the launcher / cut large-unit time / cut small-unit fixed cost / refresh the stale rules checkout; which units drive the mean; is shipping before refreshing an acceptable risk? | Values: ship 2.67, large units 1.69, small-unit cost 1.02, refresh 0.52. **First step: refresh, 47%** (ship 40%). Acceptable risk: 0.38. Mean driven by small units: 0.95 | Refreshed the checkout (unchanged scenarios), validated with the upstream harness, then pushed sub4. We did not adopt the "small units drive the mean" answer (§15, H31) | 1,349 / 157 |

The first four rounds together used about 6,600 tokens; rounds 5 to 7 are in §9.7.5 and §9.9.6.

H7 was revived later because the ~10M target made it the only viable route. It went ahead under the same hard gate, with a proven-exact RNG and differential fuzzing as safeguards.

### 4.3 Orchestration
Parallel agents were used only for **independent, verifiable** pieces with a crisp acceptance test. The critical path stayed with one integrator.

| Agent | Deliverable | Acceptance test and result |
|---|---|---|
| RNG | `native/rng/np_random.hpp` + test suite | 478,741,698 draws + 12,955 full-state checks vs numpy 1.26.4: **0 mismatches** |
| Reference dump | `native/refdump/` instrumented ABIDES + `first_divergence.py` | Instrumented runs byte-identical to plain runs on 6 scenarios |
| Fuzzer | `native/fuzz/` | 2,416 differential cases; 2 bug classes found and fixed (§8) |
| Rules and leaderboard research | Report on the live board, the scoring rules in the upstream repositories, the reference timing code, and which techniques are allowed | Its headline finding (scoring changed partway through the Development phase; local checkout stale) was confirmed by reading the organizer post, the upstream README and the board directly (§2.2, §16.5) |
| Low-latency code review (read-only) | Ranked list of exact-output-preserving optimisations and a bug check of the rewritten engine | No bug found; the blocked-queue equivalence was derived independently (§7.7) |

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
| 9 | `np.log` | The latency μ = `np.log(mean_ns)` stays numpy's own (Python paths only; the launcher uses glibc's `log` with a guard, §7.8) (SIMD log on AVX-512 hardware may differ from libm) |
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

### 7.6 End-to-end container time (sub1–sub3 measurements; since the scoring change also the Development metric)

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

### 7.9 Output pipeline rewrite: built-in Parquet writer (sub5) and delta encoding (sub6)

**Why.** The team asked for a score of 300,000. Before changing anything we re-read how the score is formed and measured where a unit's time goes.

*The formula.* The upstream README ("How throughput is measured") states that ranking is by the **arithmetic mean of the per-unit rates** over the roster, each rate being verified events ÷ container time. A mean of rates is dominated by the units with the most events, and for every unit the denominator contains a fixed container cost that we do not control. For the 65 public single scenarios: 7,465,846 events in total, 114,859 per unit on average, and the 8 largest units hold 4,135,440 of them (55%).

*Where the time went in sub4.* Phase timing (`T3_PHASES=1`) inside the sub4 image, best of 5 runs per unit, 4 CPUs, outputs on `/dev/shm`:

| Unit | Events | Process total | parse | create | simulate | finish | Parquet write |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gb_mega_throughput` | 1,168,360 | 1,230 ms | 5.2 | 60.2 | 173.7 | 234.9 | 677.4 |
| `gb_pop_horizon_scale` | 725,591 | 746 ms | 3.2 | 20.8 | 101.2 | 133.4 | 416.3 |
| `gb_horizon_240s` | 555,032 | 588 ms | 4.3 | 16.4 | 83.3 | 104.4 | 329.5 |
| `gb_highfreq_40hz_60s` | 500,530 | 526 ms | 3.8 | 14.1 | 70.8 | 99.6 | 292.6 |
| `mr_cancel_replace_churn` | 322,007 | 336 ms | 4.4 | 7.8 | 29.3 | 50.4 | 206.4 |
| `mr_deep_book_state_size` | 319,488 | 362 ms | 3.6 | 9.0 | 39.2 | 52.3 | 219.1 |
| `gb_pop_128_agents` | 303,603 | 391 ms | 4.4 | 11.3 | 56.7 | 58.4 | 219.8 |
| `mp05_cancel_churn_newest` | 240,829 | 287 ms | 4.2 | 5.9 | 25.0 | 37.7 | 180.1 |
| `mr_checkpoint_cadence_fine` | 161,055 | 211 ms | 3.5 | 4.1 | 14.8 | 24.9 | 133.2 |
| `st01_liquidity_churn_baseline` | 72,034 | 98 ms | 3.8 | 3.8 | 7.4 | 11.5 | 49.0 |

The Parquet write was 50–63% of the process on every one of these units; the event loop was 7–15%. The remainder of each total (process start, loading libarrow/libparquet, exit) was 20–80 ms.

A first, cruder look gave the same picture: two single runs of `st01` in sub4 took 1,581 ms (cold) and 154 ms (warm), the warm one with write 95.7 ms, finish 12.0 ms, simulate 10.4 ms.

**What the verifier requires of the files.** Read from the upstream scorer (`qfbench2_track_simulation/scoring.py`, `batch.py`):

- the trace and the ledger are loaded with `pd.read_parquet` and compared as tables;
- the event count is the Parquet footer's row count;
- `trace_sha256` in `events.json` is compared with the SHA-256 of *the file we wrote* (`_sha256_file(trace_path)`), not with the reference file's hash;
- outputs are capped at 256 MiB per file and in total (`limits.py`, `MAX_OUTPUT_BYTES`).

Nothing compares our file bytes with the reference's. sub1–sub4 produced pyarrow's exact bytes because that was the simplest way to be certain of equality, not because the rules ask for it. The Final's "stable outputs" rule (same bytes across repeats of our own image) is met by any deterministic writer.

**sub5: design.**

| Part | What it is |
|---|---|
| `native/engine/pq_fast.hpp` (292 lines in sub5) | Parquet writer for exactly our two tables. Thrift compact protocol written by hand for `FileMetaData`, `SchemaElement`, `RowGroup`, `ColumnChunk`, `ColumnMetaData`, `PageHeader`, `DataPageHeader`, `DictionaryPageHeader`, `KeyValue`. Row groups of at most 2²⁰ rows (the same split as before), one V1 data page per column chunk, every column OPTIONAL (as pyarrow writes them), format version 2, `created_by` "t3native version 1.0.0", codec UNCOMPRESSED, no statistics, no page index |
| Integer columns | PLAIN. The page is written straight from the engine's column buffer with `writev`; no copy into an intermediate buffer |
| String columns (`msg_type`, `side`, ledger `msg_type`) | One dictionary page holding all names (6, 2 and 13 entries), then RLE_DICTIONARY indices as a single bit-packed run, 4 bits per value (8 bits if a dictionary had more than 16 entries). Written from the engine's integer codes; the engine no longer expands them into strings for the launcher (`g_want_utf8 = false`) |
| Nullable columns (ledger `t_send_ns`, `order_id`, `causal_parent`) | Definition levels as one bit-packed run of width 1, which is the same LSB-first bitmap Arrow uses; only the present values are stored |
| Columns without nulls | Definition levels as one RLE run of ones (3–5 bytes) |
| Key-value metadata | The same `pandas` JSON string as before (this is what makes pandas restore the nullable `Int64` dtypes). The `ARROW:schema` entry is not written; pyarrow derives the same Arrow types from the Parquet schema |
| `native/engine/sha256.hpp` (121 lines) | SHA-256 with the CPU's SHA instructions when present, portable code otherwise (`T3_SHA_PORTABLE=1` forces the portable one). Hash and file write of each file run on two threads in a single run |
| Launcher binary | Linked `-static`, no libarrow/libparquet/libcrypto. 1,403,784 bytes (sub4's was 228,520 bytes plus 61 MB of shared libraries to map) |
| Output stage | `t3_finish` split into `finish_trace` and `finish_ledger`; in a single run each file's assemble → encode → hash + write chain runs on its own thread. In a batch, each market does the two chains one after the other on its worker thread |
| Exit | A single run no longer destroys the engine before `_exit` (freeing several hundred MB only to exit) |
| Size guard | If the two files together exceed 240 MiB the launcher hands the unit to the Python path, which writes snappy-compressed files |

The Python paths are unchanged: `t3native.cli` / `t3native.batch` and the ABIDES reference still write through pyarrow.

**What went wrong on the way (sub5).**

| Problem | Cause | Resolution |
|---|---|---|
| First phase-timing container ran for more than 5 minutes at about 113% CPU and 2.0 of 2.76 GiB before it was killed | The command passed `--out /output` (a directory). The launcher treats `--out` as the trace file path, could not open it, and handed over to the Python path, which was then running `gb_mega_throughput` through Python on a host that was swapping | Passed a file path. Re-tested afterwards with a small scenario: the Python path ends with `IsADirectoryError`, exit code 1, after having written `message_trace.parquet` next to the directory. The harness always passes a file path (the official regression passes), so this is a property of misuse, recorded here because it cost time |
| Static link against OpenSSL failed (`undefined reference to ZSTD_decompress`, …) | Debian's `libcrypto.a` depends on zstd and zlib | Dropped OpenSSL; wrote `sha256.hpp`. Its output is checked on every validated unit, because the checker recomputes each file's hash with Python's `hashlib` and compares it with the declared one |
| Two compile failures, "missing terminating \" character" | Patch scripts sent through a shell here-document turned `\n` inside a string literal into a real line break (the same tool behaviour as in §16.6) | Fixed with the file editor; later patches were written to files first |
| One `bash` command with two here-documents failed to parse | Tool quoting | Wrote the patch script and its payload to files |

**sub5: measured effect.** Best of 5, same conditions as the table above (ms):

| Unit | sub4 total | sub5 total | parse | create | simulate | output stage (wall) | trace: finish / build / emit | ledger: finish / build / emit |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `gb_mega_throughput` | 1,230 | 530 | 3.6 | 41.7 | 197.9 | 252.0 | 105.6 / 3.0 / 55.6 | 112.3 / 46.0 / 92.3 |
| `gb_pop_horizon_scale` | 746 | 318 | 3.8 | 21.5 | 111.1 | 153.2 | 55.2 / 1.6 / 31.6 | 70.1 / 24.4 / 57.0 |
| `gb_horizon_240s` | 588 | 232 | 3.4 | 18.3 | 79.3 | 109.9 | 45.5 / 1.3 / 21.1 | 51.3 / 16.8 / 41.1 |
| `gb_highfreq_40hz_60s` | 526 | 217 | 4.4 | 16.1 | 79.1 | 98.5 | 43.4 / 1.2 / 18.7 | 46.0 / 15.6 / 36.2 |
| `mr_cancel_replace_churn` | 336 | 117 | 3.4 | 8.6 | 37.4 | 54.7 | 29.5 / 0.9 / 14.0 | 23.5 / 9.7 / 20.6 |
| `mr_deep_book_state_size` | 362 | 102 | 3.8 | 7.5 | 36.0 | 45.0 | 23.7 / 0.6 / 11.9 | 18.0 / 8.1 / 17.6 |
| `gb_pop_128_agents` | 391 | 130 | 5.0 | 10.6 | 43.6 | 57.7 | 24.1 / 0.7 / 11.2 | 26.0 / 8.5 / 22.2 |
| `mp05_cancel_churn_newest` | 287 | 77 | 3.4 | 5.8 | 25.3 | 34.1 | 19.7 / 0.5 / 9.5 | 14.6 / 5.4 / 13.3 |
| `mr_checkpoint_cadence_fine` | 211 | 57 | 3.8 | 4.8 | 17.1 | 24.2 | 12.2 / 0.3 / 5.6 | 10.2 / 4.3 / 9.0 |
| `st01_liquidity_churn_baseline` | 98 | 30 | 3.3 | 2.9 | 6.7 | 12.8 | 5.7 / 0.2 / 2.9 | 5.5 / 1.8 / 4.7 |

The step from the first sub5 build (writer replaced, output still sequential) to the final one (parallel output chains) was measured separately on `gb_mega_throughput`: 563 ms → 530 ms; sequentially the phases were finish 171.0, build 30.2, write 100.2 ms.

After sub5 the largest remaining items on a big unit are the event loop (about 37% on `gb_mega`), the ledger chain (the longer of the two output chains) and engine creation including buffer pre-faulting.

**sub6: design.** Three changes on top of sub5 (`pq_fast.hpp` 369 lines, `engine.cpp` 1,549 lines):

1. **Integer columns DELTA_BINARY_PACKED** (blocks of 128 deltas in 4 miniblocks of 32, the layout parquet-cpp itself writes; deltas wrap in the column's own width). Nullable columns encode their present values after the bitmap.
2. **Column chunks encoded on two threads per file** (a shared counter over the row-group × column tasks), then laid out sequentially.
3. **Output columns left uninitialised** (`Raw<T>` instead of `std::vector`, which zero-filled every page before the values were written), and the ledger columns filled on two threads when there are at least 65,536 rows.

Reason for the encoding change: sub5's uncompressed files are large, and every byte is hashed and written inside the timed window. Output size, both files, summed over the 65 scenarios: sub4 289.2 MB (largest unit 45.2 MB), sub5 758.7 MB (largest 126.6 MB), sub6 135.8 MB (largest 22.2 MB).

**sub6: measured effect.** Best of 5 on the ten units (ms): `gb_mega` 485, `gb_pop_horizon_scale` 290, `gb_horizon_240s` 209, `gb_highfreq_40hz_60s` 194, `mr_cancel_replace_churn` 97, `mr_deep_book_state_size` 100, `gb_pop_128_agents` 124, `mp05` 77, `mr_checkpoint_cadence_fine` 51, `st01` 30. For `gb_mega`: output stage 167.4 ms (sub5 252.0); trace chain 104.9 / 40.0 / 21.8, ledger chain 51.1 / 86.0 / 25.8. The ledger's fill halved and both emits fell to about a quarter; encoding costs more than before (build 86 ms against 46 ms on the ledger).

All 65 units, three benchmark runs per image (3, 4 and 4 repeats per unit inside each run), sum of the best time per unit:

| | sub4 (one run, 3 repeats) | sub5 | sub6 |
|---|---:|---:|---:|
| Sum of best process times over 65 units | 10.20 s | 3.41 s | 3.28 s |
| Per-run sums | 10.20 | 3.87, 3.64, 4.13 | 5.65, 3.57, 3.58 |
| Median over units of sub6 ÷ sub5 | | | 1.007 |

The first sub6 run (5.65 s) was 60% slower than the other two and, on its own, suggested sub6 was slower than sub5 (for example `gb_horizon_240s` 485 ms against 247 ms). The same unit had measured 209 ms in the 5-repeat run an hour earlier, so both images were re-run back to back twice more; those runs agree with each other and with the earlier one. The 5.65 s run is kept in the table as an example of what this laptop does under memory pressure (§16.4). Conclusion: sub6 is about 4% faster than sub5 in total and indistinguishable on the median unit; its main benefit is the 5.6-fold smaller output.

**Validation of both images** is in §9.5.

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

## 9. Submission rounds: sub1 → sub19

### 9.1 sub1 → 4,260,093
First native submission. Correct on everything, but it paid page faults inside the timed loop, timed its own trace assembly, and under-reported batch units.

### 9.2 sub2 → 8,340,072 (+96%)
1. **Pre-faulted output buffers** (the biggest win, ~1.5–2×).
2. **Timing scope equal to the reference** (create / simulate / finish).
3. **4-ary heap and no per-dispatch message copy.**
4. **Batch units timed like single units.**

### 9.3 sub3 → pushed, never uploaded (projection of 8.7–8.8M applied to the old rule)
- **Model check.** Local rates × 1.28, capped per unit at 10M, predicted 8.16M for sub2 against the actual 8.34M.
- **Remaining headroom** is concentrated in the slowest units: `eq_deterministic_baseline` 1.74M, large GB units 2.5–4.8M, `mr_deep_book` 4.13M, `partialfill` 4.18M, `fastlob` 4.60M.
- **Change:** branch-free event heap.
- **Interleaved image A/B** (3 rounds × 61 scenarios through the real CLI path): sub3 was faster in every round (+14%, +4%, +1%; about +6%), byte-identical every time.
- **Official gate:** 65/65 pass, 0 hash mismatches, mean 6.21M, median speedup 1,029×.

### 9.4 sub4 → 153,825 (rank 9 of 17)

Built for the new rule (§2.2). Contents: the rewritten engine (§7.7) and the no-Python launcher for both verbs (§7.8); the Python native path and the ABIDES reference path are unchanged from sub3 and remain in the image as fallbacks.

Validation performed on the image `agenthon-track3:sub4` (= `slashalpha/agenthon-track3:native-v4`, `sha256:697ae5de6d95b1fce2bd467375060a10f4f343a04a00d00a989b38e5869d85c7`):

| Check | Result |
|---|---|
| Official regression, upstream harness `bffb572` + toolkit v2.5.1, reference traces from the local checkout, 1 worker | **65 passed, 0 failed, 0 errored** (8 minutes) |
| Trace files written by that run, re-hashed from disk | 65/65 equal to the baseline image's hashes; the ledger hashes sub4 reports also equal the baseline's 65/65 (this harness version does not keep the ledger file, so the ledger was not re-hashed from disk in this run) |
| Organizers' runtime restrictions (`--read-only`, `--user 65534:65534`, `--pids-limit 256`, `--cpus 4`, 64 MiB noexec `/tmp`, `--network none`) | `simulate` on `mp07` succeeded and wrote all three files; `simulate-batch` on `t3-gbatch-homog-8` succeeded with per-sub hashes equal to the verified sub2 outputs; the Python fallback (`T3_NO_LAUNCHER=1`) succeeded |
| Host `docker run` time vs sub3, 4 scenarios × 3 interleaved rounds | sub4 faster on all 4 (§1.4), same hashes |
| Image metadata | Label `qfbench2.interface_version=2.0` present; no `VOLUME` |
| Registry | Anonymous manifest fetch by digest returned HTTP 200 |

Three earlier attempts at the official regression produced no verdict, for reasons unrelated to sub4 (§16.6): the upstream harness needs toolkit v2.5.1 (`cannot import name 'digest_members'` with the older copy); a fresh upstream checkout has no `reference_traces` directory; and the harness worker process died when the host ran out of memory (`OpenBLAS error: Memory allocation still failed`). The successful run limited BLAS threads to 1.

**Score.** Two uploads (CodaBench): submission 968635 → **151,386.9550**, submission 968642 → **153,825.0187**. The board then showed S2WISH 9th of 17 scored teams, between 181,826 (8th) and 129,722 (10th); the leader was at 231,024. The team reports both as uploads of the sub4 submission; which digest each zip carried was not independently checked by us.

*(Later note: later sections read the 1.6% between these two uploads as the host's run-to-run variation (§9.5, §9.8.2, §9.8.4, §9.8.15). The organizers have since stated that Development runs on one machine that takes only Track 3 runs, one submission at a time, and another team reports two runs agreeing to within 0.1% (issue #34, §9.9.2). Because the two zips were never checked to carry the same image, the 1.6% is not evidence of noise of that size.)*

Reading the score: it sits above the cluster at 127–130K and below the cluster at 182–231K. We have no per-unit breakdown from the platform, so we cannot say from the score alone which units cost us the gap to the leaders; §7.8 and §11.2 list the candidates (large-unit output pipeline, library load time), none of them confirmed as the cause.

What was *not* done for sub4 before pushing: the 6 batch units were not all run through the image (all 6 through the launcher binary in the dev container, 1 through the image); the differential fuzz corpus was not re-run against the rewritten engine before the push (a re-check was planned for afterwards and has still not been run); no interleaved multi-round timing of all 65 scenarios.

*(Superseded later: the stored corpus of 1,318 cases was replayed on sub6 and on later builds, 1,318 of 1,318 each time (§9.7.2). sub4's own image was never replayed.)*

### 9.5 sub5 → 181,496 (+18% over sub4)

Image `slashalpha/agenthon-track3:native-v5`, `sha256:eb90d781431939ce0357290851f4b08f178dfd654d5de2e53feaefa4f117ab06` (773 MB). Contents: §7.9. The team approved the push ("lets submit sub5 in parallel"); `sub/submission.json` was updated to this digest. Building `submission.zip` and uploading are the team's steps (§12.9).

**Score.** Submission 969765 finished with **181,495.8931** (CodaBench). That is +18.0% over sub4's 153,825. It is **below the 185–220K range our model gave beforehand** (the "Estimate" paragraph further down, kept as written). The board was not re-fetched after this upload, so the new rank is not recorded here; against the board fetched earlier that day the score would sit just under the then 8th place (181,826).

**Re-fit with two scores.** With sub4 = 153,825 and sub5 = 181,496 the two-parameter model has one solution: host-speed factor k = 0.50 (their host runs our process about twice as fast as this laptop) and fixed overhead 0.551 s per container. With those values the model gives sub6 = 183,095 and a zero-process-time ceiling of **208,565**.

**That ceiling is below the leader's 231,024, so the model is incomplete.** Something it does not contain matters. Candidates, none tested:

| Candidate | What it would mean | How to test |
|---|---|---|
| Output size costs container time on their host (slow `/output` volume, or the harness handling the files before it removes the container) | sub5 lost part of its gain to files 2.6× larger than sub4's; sub6 (5.6× smaller than sub5, 2.1× smaller than sub4) would gain clearly more than the modelled 1% | Upload sub6 |
| The scored roster differs from the 65 public units (6 batch units, other sizes) | Per-unit weights in the model are wrong | Cannot be tested from here |
| The overhead is not one constant (it varies by unit, or teams with smaller images or fewer layers start faster) | Part of the "fixed" cost is ours to reduce | Image-size experiment (e.g. a much smaller runtime image) |
| Run-to-run variation on the shared host | The two scores are each a single run; our two sub4 uploads differed by 1.6% | Re-upload the same image |

*(What became of these candidates: output size and image shape were tested by the sub7 scratch upload and found to be minor (§9.7.6); the fitted model itself was shown to be wrong (§9.8.7); on run-to-run variation see the note in §9.4, which also applies to "the shared host's run-to-run variation" in the last paragraph of this section.)*

Under the fitted model alone, 300,000 is out of reach; because the model is contradicted by the leader's score, that conclusion is not firm either.

**What "correct" means for sub5 and sub6.** Through sub4 the check was byte identity of both Parquet files with the baseline image. sub5 and sub6 write different bytes on purpose (§7.9), so the check is now: both files, read back with pyarrow and with pandas, equal the stored sub4 files, which are themselves byte-identical to the baseline's (§12.7, `identity` step: 65/65). The checker (`native/engine/check_fast.py`; `check_batch_tables.py` for batch units) requires, per file:

1. the same column names in the same order;
2. the same Arrow type per column;
3. the same `pandas` metadata string;
4. `pyarrow.Table.equals` (values and nulls);
5. the same pandas dtype per column and `DataFrame.equals`;

and per unit: the `trace_sha256` and `message_trace_sha256` declared in `events.json` equal the SHA-256 of the files on disk recomputed with Python's `hashlib`; `n_events` equals the Parquet footer row count; the launcher did not hand over to the Python path. For batch units additionally: the aggregate file has the stored keys, counts and sub list, and `events_per_sec` is within 5% of `total_events ÷ wall_clock_sec`.

| Check | sub5 | sub6 |
|---|---|---|
| First smoke check, 4 scenarios (`eq_deterministic_baseline`, `mp07_heavy_flow_oldest`, `mr_deep_book_state_size`, `st01_liquidity_churn_baseline`), first build | 4/4 | — |
| 10 largest-unit check before the full run | — | 10/10 |
| All 65 single scenarios (`lab/bench/check_fast_all.log`, `check_fast_all6.log`) | **65/65**, 0 handed to the Python path | **65/65**, 0 handed to the Python path |
| 6 batch units (30 sub-scenarios), each run with `--network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 --tmpfs /tmp:size=64m,noexec` | **6/6**, every container exit code 0, empty stderr | **6/6**, every container exit code 0, empty stderr |
| Official regression: upstream harness `bffb572`, toolkit v2.5.1, 1 worker (`lab/bench/official_sub5.log`, `official_sub6.log`) | **65 passed, 0 failed, 0 errored** | **65 passed, 0 failed, 0 errored** |
| One `simulate` (`mp07_heavy_flow_oldest`) under the same restriction flags | exit 0, three files, 72,036 events, both declared hashes equal the files' | same |
| The same run with `T3_NO_LAUNCHER=1` (forced Python path, pyarrow writer) | exit 0, stderr `t3launch: using the Python path (launcher disabled)`, hashes correct; files 2,314,479 + 656,218 bytes | same, identical file sizes |
| Portable SHA-256 path forced with `T3_SHA_PORTABLE=1` (this laptop's CPU, a Ryzen 5 5500U, has the SHA instructions, so all other runs used the hardware path), 4 scenarios including `gb_mega_throughput` | 4/4 | 4/4 |
| Same bytes on repeated runs (3 runs of every scenario, SHA-256 of both files; the Final's stable-output rule) | 65/65 units identical across runs | 65/65 units identical across runs |
| Image label `qfbench2.interface_version=2.0`, no `VOLUME` | yes | same Dockerfile |
| Anonymous manifest request by digest | HTTP 200 | not pushed |

The official regression is the strongest of these: it is the organizers' own gate code reading our files. It passed on the first attempt for both images.

Not done for sub5/sub6: the 22-case fuzz corpus (§11.1); a run of all 6 batch units through the forced Python fallback in these images (the Python files are unchanged from sub4).

*(Superseded later: the stored corpus of 1,318 cases was replayed on sub6, 1,318 of 1,318 (§9.7.2). sub5 was not replayed.)*

**Timing.** §7.9 has the per-phase tables. Summary, whole-process time inside the container, best of 5:

| Unit | Events | sub4 | sub5 | sub6 |
|---|---:|---:|---:|---:|
| `gb_mega_throughput` | 1,168,360 | 1,230 ms | 530 ms | 485 ms |
| `gb_pop_horizon_scale` | 725,591 | 746 ms | 318 ms | 290 ms |
| `mr_deep_book_state_size` | 319,488 | 362 ms | 102 ms | 100 ms |
| `mp05_cancel_churn_newest` | 240,829 | 287 ms | 77 ms | 77 ms |
| `st01_liquidity_churn_baseline` | 72,034 | 98 ms | 30 ms | 30 ms |
| Sum over all 65 units (best per unit) | 7,465,846 | 10.20 s | 3.41 s | 3.28 s |

Batch units, `wall_clock_sec` reported by the launcher for the whole batch (single runs, under the restriction flags): sub5 0.058–0.131 s, sub6 0.062–0.120 s; host `docker run` time for the same sub5 runs on this laptop 1.18–2.03 s, i.e. container start and stop cost more than ten times the work.

**Estimate of the score (a model, not a measurement).** Model: score = mean over units of events ÷ (overhead + k × local best process time), where *overhead* is the fixed container time on the organizers' host and *k* is how much slower (k > 1) or faster (k < 1) their host runs our process than this laptop. One equation is available (sub4 scored 153,825), so the model was solved for the overhead at several assumed k:

| Assumed k | Fitted overhead | sub5 | sub6 | Zero process time |
|---:|---:|---:|---:|---:|
| 0.6 | 0.521 s | 186,426 | 188,264 | 220,660 |
| 0.8 | 0.466 s | 196,005 | 198,243 | 246,380 |
| 1.0 | 0.418 s | 205,455 | 208,008 | 274,681 |
| 1.3 | 0.355 s | 219,856 | 222,765 | 323,529 |

Reading it: sub5 should land somewhere around 185–220K; sub6 about 1% above sub5; and **300,000 is reachable only if the fixed overhead is at the low end and our process time goes to nearly zero**. The leader's 231,024 exceeds the k = 0.6 ceiling, so k is probably above about 0.7. In the model the 8 largest units supply 42–49% of sub5's score.

What the model leaves out: the 6 batch units (not in the 65); any difference between the public roster and the one Development scores; the shared host's run-to-run variation (our two sub4 uploads differed by 1.6%); and a single overhead value for all units. A sub5 score gives a second equation, so overhead and k can then both be fitted.

### 9.6 sub6 → built and validated locally, not pushed

Local image `agenthon-track3:sub6` (image ID `67e474a28959`). Validation and timing are in the tables above; design in §7.9. It has not been pushed because pushing needs the team's approval each time and the measured gain over sub5 is small (about 4% of total process time, about 1% of modelled score). The case for shipping it is robustness: its largest public output is 22.2 MB against sub5's 126.6 MB, which keeps a larger sealed unit away from the 240 MiB hand-over to the slow path and reduces exposure to a slow output volume.

*(sub6 was never pushed. Its changes reached the host as part of sub7: §9.7.6.)*

### 9.7 After sub5: review, research, sub7 → sub9

This section records everything done after sub5 was scored. It keeps its own experiment, hypothesis and failure tables (numbered on from §10 and §15) so that the record of these two days is in one place.

#### 9.7.1 Self-review and fix list

After the sub5 score the whole project was reviewed critically (rating given: 5.5/10). The points, and what became of each:

| # | Criticism | Outcome |
|---|---|---|
| 1 | Days were spent on the engine while the Parquet encoder dominated; sub4 was shipped without profiling the whole process | Acknowledged; §16.8 |
| 2 | The timing harness had not been read | Read: `throughput/run_unit.py` builds `docker run --rm --cidfile … --network=none --cpus=N --memory=M [--gpus … -e NVIDIA_DRIVER_CAPABILITIES=…] -v in:/input:ro -v out:/output IMAGE simulate …` and `timer.py` times the whole subprocess with `time.monotonic` |
| 3 | The "output size costs time" theory was weak (`/output` is a bind mount; nothing in the public harness touches the files inside the timed window) | Later not supported by the sub7 score (§9.7.6) |
| 4 | The fitted ceiling was below the leader's score | Still unexplained |
| 5 | No per-unit data from the platform | A route was found (`…/api/submissions/<id>/get_details/` → `detailed_result`); the team reports "Program logs are withheld from participant output". Not obtained |
| 6 | No native Linux measurement | Not fixed |
| 7 | Fuzz re-check deferred three times; `log` margin unverified; untested writer paths | Fuzz closed (§9.7.2); `log` margin now supported by documentation, still not by a run (§9.7.5); writer paths unchanged |
| 8 | Process slips (stale image benchmarked, here-document escapes) | Builds stop on failure; `lab/validate_image.sh` runs the whole suite; patches are written to files |

#### 9.7.2 Fuzz corpus replay (`native/fuzz/recheck_stored.py`)

The stored fuzz logs contain, per case, the scenario and the SHA-256 of both reference files. 1,318 distinct cases have an OK reference (197 records without one are skipped). The tool replays each case twice inside an image, without running ABIDES:

1. `T3_NO_LAUNCHER=1 simulate` (Python + native engine, pyarrow writer): both files must have exactly the recorded reference hashes;
2. `simulate` (launcher): its files must read back as the same tables as step 1's, and its declared hashes must be the files' hashes.

| Image | Result | Launcher handled / handed to Python | Duration |
|---|---|---|---|
| sub6 | 1,318 OK, 0 bad | 358 / 960 | 2,228 s |
| sub7 (first build) | 1,318 OK, 0 bad | 1,295 / 23 | 1,345 s |
| sub7 (final build) | 1,318 OK, 0 bad | 1,295 / 23 | 1,533 s |
| sub8 | 1,318 OK, 0 bad | 1,295 / 23 | 1,539 s |

`native/fuzz/decline_reasons.py` (launcher only, `PATH` emptied so a hand-over exits at once) gave for sub6: 941 "non-integer where int expected", 19 "protocol_enforcement is not a bool", 358 handled. The 941 are whole numbers written as floats (`"threshold_ticks": 2.0`, `"max_ns": 5000000.0`, `"count": 5.0`; a survey of 400 cases found such values in 25 different fields). `native_sim.py` applies `int()` at every one of those sites, so `as_int` in the launcher now parses the token with `strtod` and truncates toward zero, declining values outside ±9.0e18. After the change: 1,295 handled, 19 non-boolean flag, 4 "latency rounding sensitive to the log implementation". The last line is the first time the `log`-sensitivity guard (§7.8) was seen to fire.

#### 9.7.3 sub7

Changes relative to sub6: `as_int` as above; the ledger is encoded straight from the engine's 40-byte delivery records through per-column callbacks (`pqf::Col::custom`), so `finish_ledger` and its 13 column arrays are not built on the launcher path; a faster bit packer for widths up to 56 bits; tuning switches (`T3_ASYNC_PF`, `T3_TRACE_THREADS`, `T3_LEDGER_ENC_THREADS`, `T3_TRACE_ENC_THREADS`).

Two changes were built, measured and left **off by default**: populating the output buffers from helper threads while the simulation runs, and a two-thread trace merge. The interleaved A/B (`native/engine/ab_knobs.py`, 4 units × 9 rounds, variants alternated within each round) did not show a gain for either; the differences were inside the run-to-run spread. A first A/B, taken while the fuzz replay was running on the same machine, was discarded (identical runs differed by 30%).

Speed against sub6 could not be established: two interleaved runs gave 4.32 and 4.65 s for sub7 against 5.35 and 4.77 s for sub6, in a session in which sub6 itself was a third slower than in the previous session.

Validation of the final sub7 build (`lab/bench/validate_sub7.log`): tables 65/65; identical bytes across 3 runs 65/65; batch 6/6 under the runtime restrictions; single run and forced fallback under the restrictions, exit 0; official regression 65 passed, 0 failed, 0 errored; fuzz 1,318/1,318. CPU-quota check: `nr_throttled 0`, `throttled_usec 0` in `/sys/fs/cgroup/cpu.stat` after three runs of each of four units with `--cpus 4`.

#### 9.7.4 The scratch image (`sub/Dockerfile.min`)

`FROM scratch`, one layer, 2.16 MB: the static launcher at `/usr/local/bin/simulate`, a symlink `simulate-batch`, empty `/etc`, `/run`, `/tmp`, `/input`, `/output`, library directories, and a two-line `passwd` and `group`; `ENV PATH=/usr/local/bin`; the required label; no entrypoint; `CMD ["simulate","--help"]`. There is no Python and therefore no fallback layer: a declined unit exits with status 127.

Validation (`lab/bench/val_sub7s/`): all 65 scenarios and all 6 batch units run with `--network none --read-only --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --ulimit nofile=1024 --cpus 4 --memory 16g --tmpfs /tmp:size=64m,noexec`; every container exited 0 with empty stderr; tables 65/65 and 6/6 identical. Not done before the upload: a run on a host with a GPU runtime.

Pushed as `slashalpha/agenthon-track3:native-v7s`, `sha256:2b97366d097cf6a68e6aefb3a148940ae1517de55c6945d7dc43f64e6b3e4cf0`, after the team asked for its score.

#### 9.7.5 Four parallel research and review agents

| Agent | Findings we rely on | Marked by the agent as |
|---|---|---|
| Competition intelligence | The leading team's public image is a single layer of about 1.2 MB built `FROM scratch`; at least three other teams ship sub-2 MB images; one team identified with a native engine inside a Python image scored about 154K. Development scores the 71 public units (65 single + 6 batch); no sealed units were found for Development. Every unit attaches one GPU by UUID. Runtime is runc. Applied limits also include cap-drop ALL, no-new-privileges, nofile 1024. `/input` is the whole unit directory. Organizers state they have no published start-up figure; a participant reports "roughly half a second" fixed cost with 0.1% run-to-run agreement. Last Development runs must start by the Development deadline; the Final takes one submission. Board: 231,024 / 221,088 / 209,558 / 201,094 / 198,767 / 188,230 / 185,937 / 185,889 / 184,047 / 181,496 (us, 10th of 20) | Facts from repositories, issue threads, the CodaBench API and registry metadata; the production runner code is not public |
| Container start-up engineering | Published warm `docker run` 554–568 ms for 5–155 MB images (within 2.5%); image environment cannot disable the GPU hook (Docker appends its own variables after the image's); the hook runs `ldconfig` over the image's library directories (estimated 5–30 ms for a Python image, 1–3 ms for an empty one); exit cost about 18 ms per GB of resident memory; no published per-step timing of the GPU hook exists | Measured-by-source for the Docker figures; estimates for the hook |
| Literature | numpy's scalar `log` on AVX-512 builds goes through a vector library; documented differences from the C library are about 1 ulp (numpy issues #22904, #23523). At queue sizes of hundreds to thousands, 4-ary heaps are as good as published alternatives. DELTA_BINARY_PACKED writers reach about 1.7 ns/value | Source reading, not a run |
| Code review (read-only) | About 430 MB of fresh memory touched on `gb_mega_throughput` to write 22 MB (190 MB pre-faulted buffers of which 98 MB used; 78 MB trace assembly; 44 + 118 MB encoder scratch, zero-filled to worst case); trace finish at about 125 ns/row is too slow for computation; reservations 1.63×–2.6× actual; `\u` escapes kept verbatim in the JSON parser; `std::terminate` instead of fallback if a thread throws; `as_int` truncation matches `int()` at every site; no uninitialised read in the raw column buffers. Ratings: correctness 7.5, whole-process performance 5.5, measurement discipline 5 | Estimates from code reading and our phase logs |

**Decision round 5** (1,467 / 187 tokens): values — upload the scratch image and read per-unit results 1.41; A/B both image shapes 0.74; implement the fused output stage first 1.63; rent a Linux machine 0.35. First step: upload, 0.64. P(image shape worth more than 5%) = 0.36. P(240,000 reachable by the Development deadline) = 0.31. Best next code change: fuse trace assembly and encoding, 0.92.

#### 9.7.6 Score of the scratch image

Upload finished with **184,857.7235** (the submission number ends in 70091; "Program logs are withheld from participant output"). Against sub5's 181,495.89 that is **+1.85%**, and this step also contains sub6's and sub7's process-time changes. Estimates given before the upload: 183–190K if image shape did not matter, 200–225K if it did. The result is in the first range. With the board fetched earlier that day the score would be 9th (above 184,047); the board was not re-fetched.

What this rules out for our case: image size, layer count and the absence of system libraries as a major term of the fixed cost, and output size as a major term (sub7's files are 5.6× smaller than sub5's).

#### 9.7.7 sub8: memory

Instrumentation added to the launcher's `T3_PHASES` output: `getrusage` minor and major faults, user and system CPU time, peak resident memory, and reserved versus used rows of the three engine buffers (`native/engine/res_units.py` collects them per unit).

First survey (sub7 logic, 59 units — see the failure table for the missing six): 366,725 minor faults; user time 5,046 ms and **system time 4,482 ms**; rows used as a fraction of rows reserved: order rows 0.22–0.58 (median 0.42), quotes 0.20–0.58 (0.49), ledger 0.28–0.68 (0.54).

Changes:

| Change | Where |
|---|---|
| `delta_pack_fn` writes into an uninitialised worst-case buffer (`__resize_and_overwrite`) instead of a zero-filled one | `pq_fast.hpp` |
| The temporary for present values of a nullable column is uninitialised | `pq_fast.hpp` |
| Engine buffers are populated to 64% (order rows, quotes) and 74% (ledger) of the reservation; the rest is faulted on demand | `engine.cpp`, `Buf::prefault(frac)` |
| Column arrays of 4 MiB or more are 2 MiB-aligned and advised for huge pages | `engine.cpp`, `Raw<T>::resize` |
| `\uXXXX` escapes are decoded to UTF-8 (surrogate pairs combined; lone surrogates declined) | `launcher.cpp` |

| Quantity (same 59 units) | sub7 | sub8 |
|---|---:|---:|
| Minor page faults | 366,725 | 190,828 |
| Sum of peak resident memory | 2,348 MB | 1,651 MB |
| `gb_mega_throughput`: faults / peak memory | 54,029 / 359 MB | 20,568 / 226 MB |

Timing, two interleaved runs per image, 4 repeats per unit, all 65 units: sub8 3.751 and 3.745 s; sub7 4.324 and 4.408 s; sum of per-unit minima 3.559 against 4.067 s (**−12.5%**); median per-unit ratio 0.915. Largest unit 663 → 474 ms. Single-run user and system times from the survey are not used for comparison (they moved in opposite directions between two single runs).

Validation (`lab/bench/validate_sub8.log`): tables 65/65; repeat-run bytes 65/65; batch 6/6; single and forced fallback under restrictions exit 0; official regression 65 passed, 0 failed, 0 errored; fuzz 1,318/1,318 (1,295 by the launcher).

#### 9.7.8 sub9: index-based trace output

`trace_index` (engine.cpp) replaces the body of `finish_trace`: it marks final fills, builds the quote rows, and merges order rows and quotes into one array `src` of 4 bytes per output row (an order-row index, or a flagged quote index). Equal-time runs of order rows are contiguous in the merged order and are sorted in place where they land, so the separate `ord` array is gone. `finish_trace` (Python path) now materialises its seven columns from that index, so the Python path exercises the same index code. The launcher encodes each trace column straight from `src` through accessor pairs (one for a quote row, one for an order row) and never builds the seven arrays. The hashing thread is started only for files of 4 MiB or more.

| Quantity | sub7 | sub8 | sub9 |
|---|---:|---:|---:|
| Minor page faults, 59 units | 366,725 | 190,828 | 125,051 |
| Sum of peak resident memory, 59 units | 2,348 MB | 1,651 MB | 1,456 MB |
| `gb_mega_throughput`: faults / peak memory | 54,029 / 359 MB | 20,568 / 226 MB | 15,892 / 189 MB |

Timing, two interleaved runs per image: sub9 3.724 and 3.640 s; sub8 4.235 and 3.896 s; sum of per-unit minima 3.237 against 3.684 s (**−12.1%**); median per-unit ratio 0.905. Eight largest units (sub8 → sub9, ms): 508 → 471, 309 → 272, 251 → 211, 263 → 188, 116 → 99, 122 → 106, 149 → 125, 89 → 75.

Validation so far: tables 65/65 (first build and after the hashing-thread change). The full suite (`lab/validate_image.sh sub9`) was started; see `lab/bench/validate_sub9.log` for its result.

Neither sub8 nor sub9 has been pushed or scored. In the fitted model each is worth about 2% of score.

*(Superseded later: sub9's full validation passed (`lab/bench/validate_sub9.log`: tables 65/65, repeat-run bytes 65/65, batch 6/6, official regression 65 passed, fuzz replay 1,318 of 1,318 with 1,296 handled by the launcher and 22 handed to the Python path), and its scratch image scored 183,419.75 (§9.8.2). sub8 was never uploaded.)*

#### 9.7.9 Experiments of these two days

| ID | Experiment | Result | Decision |
|---|---|---|---|
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

#### 9.7.10 Hypotheses of these two days

| ID | Hypothesis | Test | Outcome |
|---|---|---|---|
| H44 | The rewritten engine (sub4 onward) still reproduces the fuzz corpus | E67 | **Confirmed**, 1,318/1,318 |
| H45 | The launcher handles most inputs itself | E67, E68 | **Refuted** for the corpus (27%); 98.3% after the fix |
| H46 | Part of the fixed container cost depends on image shape | E76 | **Refuted as a major effect** (+1.85% including other changes) |
| H47 | Output size costs container time on the scoring host | E76 | **Not supported** |
| H48 | Asynchronous pre-faulting helps | E71 | **Not shown**; inside noise |
| H49 | A two-thread trace merge helps | E71 | **Not shown**; inside noise |
| H50 | Our threads are throttled by the CPU quota | E72 | **Refuted** on the units checked |
| H51 | Memory handling dominates remaining process time | E77, E79, E80 | **Confirmed**: halving faults twice gave −12.5% and −12.1% |
| H52 | numpy's `log` on the Final's CPU type is within the guard's 16-ulp margin | Documentation found by the literature agent (about 1 ulp) | **Supported, not measured** |
| H53 | 240,000 is reachable before the Development deadline | Model; decision model 0.31 | **Open; doubtful** |

*(The current status of every hypothesis is in §15. H51 was refuted for the scoring host the next day: §9.8.2.)*

#### 9.7.11 Failures of these two days

| Failure | Cause | Resolution |
|---|---|---|
| The first `\u` fix made 6 public scenarios unusable for the launcher | Their free-text descriptions contain `\u` escapes; the fix declined any escape | Caught by the next measurement (59 of 65 units reported); escapes are now decoded |
| A/B numbers taken during the fuzz replay were meaningless | Two heavy jobs on one machine | Timing only on a quiet machine; validation and timing no longer overlap |
| sub7 could not be shown faster than sub6 | The machine was a third slower in that session than in the previous one | Reported as unresolved; later builds measured with interleaved runs that agree |
| Compile error in the writer (`cannot bind rvalue reference`) | Explicit template argument defeated forwarding | One-line fix |
| Two status-file and patch commands failed on `\u` inside Python source passed through the shell | Python parsed `\u` as an escape | Written through files |
| A wait loop expired before the job it was watching | 9.5-minute limit of the waiting command | The job's own log is read, not the waiter's status |
| Prediction "200–225K if image shape matters" was the favoured case in our plan | Over-weighted indirect evidence (what leaders ship) against direct evidence (published Docker timings) | Recorded; H46 |

### 9.8 After the scratch image: three more scores, a wrong model, and output moved into the run

This section records everything done after the scratch image had scored 184,858. Where a result was still pending when this was written, the text says so.

#### 9.8.1 Scores of the day

| Build | Image (Docker Hub `slashalpha/agenthon-track3`) | Upload | Score | Against the previous score |
|---|---|---|---:|---:|
| sub7 (scratch) | `native-v7s`, `sha256:2b97366d…6b3e4cf0` | number ends in 70091 | 184,857.72 | |
| sub9 (scratch) | `native-v9s`, `sha256:9e8206c3…ce61d3a57` | 970940 | **183,419.75** | −0.8% |
| sub10 (scratch) | `native-v10s`, `sha256:3b27783e…34254a441` | 971069 | **188,687.15** | +2.9% |
| sub11 (scratch, memory switches off) | `native-v11m`, `sha256:47c37844…d7cfe8128` | 971164 | **189,018.28** | +0.2% |
| sub13 (scratch, memory switches off) | `native-v13m`, `sha256:1ca74d1c…3784f86f0` | 971360 | **184,046.62** | −2.6% |

Each score arrived 45 to 60 minutes after its upload.

*(Later, results arrived much faster than this: §9.9.1.)*

The top of the board at that point (29 teams): fuzz 231,024.24; abc123 221,088.30; Yan Su 210,016.36; Proof of Alpha 209,558.04; IMAnonymous 206,925.97. The first two were unchanged from the previous fetch; the other three had moved or appeared since. Six teams were above 200,000 a few hours later.

#### 9.8.2 sub9 on the host: the memory work was worth nothing there

sub9 carried the two rounds of memory work of §9.7.7 and §9.7.8, measured locally at −12.5% and −12.1% process time. The fitted model of §9.5 predicted about 190,000. The host returned 183,420, below the 184,858 of the build without that work.

- **Size of the miss:** two identical uploads once differed by 1.6% (§9.4), so the drop of 0.8% is inside the noise. The predicted gain of about 3% is clearly absent.
- **Reading at the time:** either the host rewards process-time savings much less than modelled, or the huge-page requests and the up-front population of buffers cost time on a busy shared host that they do not cost on a fresh laptop VM.
- **Reading after §9.8.5 and §9.8.6:** page-fault costs that dominate laptop timings barely register on the host. The laptop's "23% faster" was a property of the laptop.

*(Later note on "inside the noise", here and in §9.8.4 and §9.8.15: the 1.6% comes from two uploads that were never checked to carry the same image (§9.4). The organizers state that the host is a single machine taking only Track 3 runs, one submission at a time, and another team reports two runs agreeing to within 0.1% (§9.9.2). Differences of 0.2% to 0.8% between two of our builds may therefore be real.)*

Hypothesis H51 of §9.7.10 ("memory handling dominates remaining process time") was confirmed on the laptop and is **refuted for the scoring host**.

#### 9.8.3 sub10: no message ledger where the card does not require one

**The rule.** A read-only investigation agent (§9.8.7) found, and we then confirmed by reading the code ourselves, that six of the heaviest units do not need `message_trace.parquet`:

- `qfbench2_track_simulation/limits.py:152–157`: `requires_message_ledger(card)` returns the card's declared value.
- `qfbench2_track_simulation/scoring.py:693–694`: `if not policy.requires_message_ledger: return GateResult(True)`. On those units the scorer never opens our ledger file.
- `limits.py:197–199`: for a single-market unit the required stable outputs are `trace.parquet` alone when the ledger is not required.
- `README.md:144–148` and `:199`: "don't write `message_trace.parquet` on units whose card has `requires_message_ledger = false`".
- `README.md:159–160`: batch units are not exempt; every sub-scenario needs a ledger whatever the card says.
- Of the 71 public cards, 12 say `false`: the six single `gb_*` units and the six batch units. Only the six single units can use it.
- `card.toml` reaches the container: the Development dataset strips only `trace.parquet`, `events.json`, `message_trace.parquet` and reference directories from `/input` (`toolkit-v2.5.1/common/qfbench2_common/dataset.py`, `STRIP_FILES`).
- The scorer's required `events.json` keys (`scoring.py:96–103`) are `scenario_id`, `n_events`, `wall_clock_sec`, `events_per_sec`, `seed`, `trace_sha256`. `n_messages` and `message_trace_sha256` are not among them.

*(Confirmed by the organizers in issue #35: the official runner mounts the unit's input folder at `/input` as a whole, so `/input/card.toml` is present; batch units need a ledger for every sub-scenario whatever the card says; `scenario_family` must not be used as a stand-in for the flag: §9.9.2.)*

The six units hold 3,321,467 of the 7,728,572 public events, and about 37% of our modelled score.

**The change.**

- `launcher.cpp`, `card_skips_ledger()`: reads `card.toml` beside the scenario and returns true only for the exact line `requires_message_ledger = false` under `[scoring.params]`. A missing file, a missing key, any other value, or a repeated key means the ledger is written. Only the single-scenario command uses it; `simulate-batch` never does.
- `engine.cpp`: `Engine::skip_ledger`. Delivery records go to one scratch record, the ledger buffer is reserved at one record, and it is not populated.
- `events.json` omits `n_messages` and `message_trace_sha256` when no ledger is written.
- `T3_LEDGER=1` writes the ledger regardless of the card, for comparison runs.

**Checks** (`lab/check_skip.sh`, `native/engine/check_skip.py`): each of the six units is run the way the harness mounts it (`/input` = the unit directory) once reading the card and once with `T3_LEDGER=1`. Per unit: no `message_trace.parquet` in the first run; trace table equal to the unit's reference (`Table.equals` and `DataFrame.equals`); trace bytes equal to the second run's; `events.json` declares the file's hash and row count and has no ledger keys. A unit whose card requires the ledger (`t3-mr-deep-book-state-size`) still gets all three files. Result: 6 of 6, on the full image, on the scratch image, and on the image pulled back from Docker Hub by digest.

**Full validation of sub10:** tables 65/65, repeat-run bytes identical 65/65, batch 6/6, single run and forced fallback, official regression 65/65, fuzz replay 1,318/1,318 (23 cases handed to the Python path, 1,295 handled by the launcher; sub9 had 22 and 1,296, and the one case that moved has not been traced yet).

*(A likely cause was found and has not been confirmed by a targeted test: the helper thread draws latencies ahead of the event loop, and a draw the run never consumes can still raise the `log`-sensitivity flag: §9.9.10.)*

**Local timing, sub9 against sub10** (whole process, best of 5 in each of two interleaved rounds, `native/engine/bench_unit_dirs.py`, results in `lab/bench/gb_sub9_*.json` and `gb_sub10_*.json`):

| Unit | sub9 (ms) | sub10 (ms) | Change |
|---|---:|---:|---:|
| t3-gb-mega-throughput | 331.9 | 280.6 | −15.5% |
| t3-gb-pop-horizon-scale | 202.4 | 173.3 | −14.4% |
| t3-gb-horizon-240s | 150.5 | 130.3 | −13.4% |
| t3-gb-highfreq-40hz-60s | 125.1 | 123.9 | −1.0% |
| t3-gb-pop-128-agents | 89.2 | 81.6 | −8.5% |
| t3-gb-base-30agent-30s | 26.3 | 25.7 | −2.3% |
| Sum | 925.4 | 815.4 | −11.9% |

*(Caveat found later: `bench_unit_dirs.py` reads the inputs from the unit folders, which on this laptop are a Windows-backed mount that adds 10 to 20 ms per run which the scoring host does not have. This applies to every whole-process figure of §9.8 that was measured from the unit folders: §9.9.3. The figures are left as measured.)*

**On the host:** 188,687, +2.9% over sub9. The investigation agent had estimated +2.1K to +3.0K; the result was +5.3K. Removing real work on heavy units paid about twice what the model said.

#### 9.8.4 sub11: profile-guided build, earlier exit, and two memory switches

Three changes on top of sub10, none of which alters a table:

- **Profile-guided build** (`sub/Dockerfile`, build argument `T3_PGO`, default 1). An instrumented `-O3` build runs the scenarios in `native/engine/pgo_train/` (14 scenarios with a ledger, 4 unit directories without), then the real `-O3` build uses the counts. The launcher leaves through `_exit`, so the instrumented build flushes its counters itself (`leave()` in `launcher.cpp`, under `T3_PGO_GEN`). Floating-point options are unchanged (`-ffp-contract=off`, no `-ffast-math`).
- **Earlier exit.** A single run now prints its result line and leaves inside `run_one`, before the encoded files, the scenario tree and the engine's buffers would be freed.
- **Memory switches** read from the environment by the engine: `T3_HUGE=0` stops the huge-page requests, `T3_PREFAULT=0` stops the up-front population of output buffers. `sub/Dockerfile.min` takes both as build arguments and puts them in the image's environment, so one validated binary can be shipped in either memory mode.

Local measurements:

| Measurement | Result |
|---|---|
| sub10 → sub11, six `gb_*` units, best of 5 × 2 rounds | 803.2 → 787.8 ms (−1.9%) |
| Tables, sub11 | 65/65; also 65/65 with both switches off |
| Largest unit, warm, phases (parse + create + sim + out, ms), default | 3.0 + 12.4 + 166.5 + 49.8 |
| Same, `T3_PREFAULT=0` | 3.0 + 1.1 + 190.3 + 54.7 |
| Same, `T3_HUGE=0` | 4.2 + 49.7 + 190.0 + 57.0 |
| Same, both off | 3.9 + 1.3 + 247.4 + 145.6 |

So on the laptop, warm, both switches off cost about 70% on the largest unit.

**Full validation of sub11:** tables 65/65, repeat-run bytes 65/65, batch 6/6, official regression 65/65, fuzz replay 1,318/1,318. The scratch image with both switches off (`sub11m`) has a byte-identical binary and passes official regression 65/65, batch 6/6 and the six no-ledger units.

**On the host, with both switches off:** 189,018, against sub10's 188,687 (+0.2%, inside the noise). The switch that costs 70% on the laptop costs nothing measurable on the host. What this upload cannot say is whether the profile-guided build helped: a small compiler gain and a small memory loss would cancel to the same number. It bundled two things, which §9.8.7 criticises.

*(On "inside the noise" see the note in §9.8.2.)*

#### 9.8.5 The measurement method was wrong: warm loops against cold containers

All local timing up to this day ran `simulate` repeatedly inside one running container and took the best of N. The scoring host starts one fresh container per unit and runs once.

A run of the sub11 scratch image as a fresh container under the runtime restrictions reported an event-loop time of 0.727 s for a unit whose warm event loop takes 0.04 s. That led to `lab/cold_runs.sh`: one fresh `docker run` per measurement, runtime restrictions, `/input` = the unit directory, the launcher's phase line captured.

Fresh-container phases (ms), output on an in-memory mount (`COLD_OUT=tmpfs`):

| Unit, build | parse | create | sim | out |
|---|---:|---:|---:|---:|
| deep-book (320K rows), default memory mode, 4 runs | 13–25 | 52–145 | 75–190 | 39–113 |
| deep-book, both switches off, 4 runs | 14–29 | 1–2 | 217–377 | 62–89 |
| mega (1.17M rows), default, 3 runs | 16–18 | 34–326 | 281–499 | 112–237 |
| mega, both switches off, 3 runs | 8–35 | 3–4 | 651–749 | 171–287 |
| tiny (10K rows), default, 3 runs | 7–24 | 5–9 | 6–14 | 7–10 |

For comparison, warm: deep-book 3 + 7 + 37 + 22, mega 3 + 12 + 167 + 50.

What this shows and what it does not:

- **A fresh container is two to five times slower than a warm loop on this laptop, and the spread between runs is as large as the mean.** The buffer set-up phase alone ranged from 33 to 429 ms on the largest unit.
- **The laptop's Docker VM has 2.97 GB of memory** (`docker info`), and `/input` is a Windows-backed mount. Much of the cold cost here is this machine: memory reclaim in a small VM, the mount, and WSL2's expensive page faults.
- **CPU-quota throttling is not the cause:** `cpu.stat` in the container's cgroup shows `nr_throttled 0` on every one of six fresh runs (largest unit 5 to 17 periods, mid-size unit 3 to 4).
- **Conclusion:** local timings of anything related to memory or threads are not evidence about the host, in either direction. The only trustworthy instrument is an upload.

*(From §9.9 on, hardware counters on one thread are the local instrument for instruction and branch-miss counts (§9.9.3). They say what the simulation thread does and still nothing about how the host treats threads.)*

#### 9.8.6 What the host has told us so far

| Step | Kind of change | Laptop, warm | Host |
|---|---|---:|---:|
| sub4 → sub5 | Python interpreter and Arrow encoder removed | −67% process time | +18.0% |
| sub5 → sub7 | Smaller files, direct ledger encoding, 2.2 MB image | a few percent | +1.9% |
| sub7 → sub9 | Fewer page faults, fewer passes over memory | −23% | −0.8% |
| sub9 → sub10 | Ledger not recorded or written on six heavy units | −11.9% on those units | +2.9% |
| sub10 → sub11 | Profile-guided build, earlier exit, memory switches off | −1.9% then about +70% on the largest unit | +0.2% |

The host pays for removed instructions and removed output work. It does not pay for avoided page faults, and it does not charge for restoring them.

#### 9.8.7 Two read-only reviews by agents

Both were forbidden to use Docker, to modify sources, or to push anything. Their numbers are estimates from reading code and our measurement files, not measurements.

**First review ("find a way to 240K").** Scratch scripts in `lab/agent240/` (not tracked in the repository).

- Found the ledger rule of §9.8.3. This was the most valuable single finding of the week and we had missed it for nine days although the README states it.
- Refitted the score model to three scores and showed that the split between fixed cost and process cost cannot be identified: any speed factor from 0.3 to 1.2 fits within the noise.
- Read the harness: the official launcher is not in either public checkout, so what lies inside the timed window is known only from the README's wording ("from creating your container to removing it").
- Found nothing in the image configuration that can shorten the GPU hook or the container lifecycle.
- Ranked remaining work; its realistic range for the full plan was 198–213K, and its estimate for 240K by the deadline was under 10%.

**Second review (a deliberately harsh critique, persona of a low-latency systems engineer).**

- **The fitted model of §9.5 is wrong.** The total of 7,728,572 rows over 71 units puts the score with zero process time at 108,853 ÷ c for a fixed cost of c seconds. The leader's 231,024 therefore requires c ≤ 0.471 s. More plausibly c is 0.30–0.42 s and our process runs 1.5 to 2.4 times slower on the host than the warm laptop numbers.
- **The laptop has been contradicted by the host twice** (sub9 and sub10, in opposite directions).
- **Small units matter.** The 58 units under 100,000 rows carry 45–50% of the score, so fixed per-run milliseconds count on all of them: thread creation, allocation churn.
- **Upload budget.** `toolkit-v2.5.1/docs/DEVELOPMENT-RUNTIME.md` caps Track 3 at **5 uploads per day and 20 in total** for the Development phase. We verified this in the document. We had been planning with the daily limit only.
- **Scorer reading.** Tier A cards compare fills exactly and the rest as a multiset with a rank-correlation threshold; Tier B cards require the exact row count and statistical checks; the ledger is checked for self-consistency and coverage, never row by row. It found no large legitimate saving beyond the ledger skip, and it listed three things near a rule boundary that we will not do (a null trace hash, a truncated ledger, an all-null ledger column).
- **Specific waste in the code:** a fresh 512 KB block per nullable column chunk in the encoder; threads created per batch; five busy threads against a quota of four; the 2.5 KB random-generator state sitting between the hot fields of each agent; the trace re-walked three times after the run.
- **Its probabilities by the deadline:** 200K about 50%, 210K about 18%, 220K about 6%, 240K 1–2%.
- **Its verdict on method:** "three days of optimisation against a proxy … that the scoring host had already contradicted", and uploads spent on bundles of changes instead of first measuring the host's cost model.

*(Corrected later: the competition page itself allows 5 uploads per day and 23 per person in total. The 20 is the toolkit document's figure: §9.9.1.)*

We accept the criticism of the method. §9.8.5 is our own evidence for it.

#### 9.8.8 sub12 and sub13: streamed files and per-run overheads

**sub12 = sub11 + streaming writer.** `pq_fast.hpp` no longer builds a whole file as a list of segments. Row groups hold at most 2^16 rows (previously 2^20); they are encoded in batches into two sets of reused buffers, and one batch is hashed and written (`FileSink` in `launcher.cpp`, one `writev` per group) while the next is encoded. The file bytes differ from sub11's because there are more row groups; the tables are equal. Fully validated (tables 65/65, repeat-run bytes 65/65, batch 6/6, official regression 65/65, fuzz replay 1,318/1,318). Peak memory on the largest unit fell only from 92 to 88 MB, because most of it is the engine's row buffers. Not uploaded.

**sub13 = sub12 + five changes aimed at per-run overheads** named by the second review:

| Change | Where |
|---|---|
| Helper threads started once per file and reused for every batch; none for a file of one row group | `pq_fast.hpp` |
| One scratch block per thread for nullable columns, not a fresh one per column chunk | `pq_fast.hpp`, `put_nullable_i64` |
| Freed blocks stay in the heap (`mallopt`: mmap threshold 32 MiB, trim threshold 1 GiB) | `launcher.cpp`, `main` |
| At most four busy threads during output: two per file, or four on the trace when no ledger is written | `launcher.cpp` |
| Hot fields of `Agent` together, random-generator state last | `engine.cpp` |

Fully validated (tables 65/65, repeat-run bytes 65/65, batch 6/6, official regression 65/65, fuzz replay 1,318/1,318); six repeated runs of three scenarios byte-identical. The scratch image with both memory switches off has a byte-identical binary and passes official regression 65/65, batch 6/6 and the six no-ledger units; pulled back from Docker Hub by digest under the full runtime restrictions it writes three files for a ledger-required unit and two for the largest no-ledger unit. No speed measurement was taken: the machine was busy and warm timing had lost its standing. Uploaded as the fifth upload of the day; score pending when this was written.

*(Score: 184,046.62, §9.8.15.)*

#### 9.8.9 sub14: the trace is built in its final order during the run

Until sub13 the engine logged order-lifecycle rows and best-quote snapshots into two buffers, and after the run `trace_index` walked them three times: a backward pass to find each order's final fill, a monotonicity check, and a merge of quotes and order rows with a sort inside every equal-time run.

Every handler logs at the kernel's dispatch time, and dispatch times never decrease (the next event is the minimum over the two heaps and the blocked queues, and nothing can be scheduled in the past). So rows arrive in nondecreasing time and can be put in final order at once:

- All rows of one timestamp form a bucket. A bucket's quote rows come first: at most one per side, holding the last value logged at that time, in order of first appearance. Then its order rows, sorted stably by (order id, owner).
- A bucket is closed by the first row of a later time (`Engine::trace_at`, `close_bucket`). Short buckets use a stable insertion sort; they are usually already in order.
- `last_fill[order_id]` holds the index of the order's latest executed row. When the run ends, those rows become final fills (`finish_trace_rows`).
- A row with an earlier time than the open bucket sets a flag and the run fails, which sends the scenario to the fallback path. It has never been observed.

*(It was observed the same day, in 29 stored fuzz cases with a negative latency: §9.8.15.)*

The quote log, the merge index (`TraceIndex`, `TraceQ`), the three passes and their threads are removed. The launcher encodes columns straight from `Engine::trace`, with no per-row branch between quote and order sources.

Results:

| Check | Result |
|---|---|
| Tables | 65/65 on the first build |
| Six no-ledger units | 6/6 |
| Peak memory, largest unit (warm, default memory mode) | 89 → 66 MB |
| Full validation | tables 65/65, repeat-run bytes 65/65, batch 6/6, fallback run and official regression 65/65 passed; fuzz replay in progress when this was written |

Interleaved warm timing, sub13 against sub14 (best of 5 in each of three rounds, `lab/bench/ot_sub13_*.json`, `ot_sub14_*.json`):

| Unit | sub13 (ms) | sub14 (ms) | Change |
|---|---:|---:|---:|
| t3-gb-mega-throughput | 358.3 | 343.8 | −4.0% |
| t3-gb-pop-horizon-scale | 219.2 | 197.4 | −9.9% |
| t3-mr-deep-book-state-size | 99.1 | 88.9 | −10.3% |
| t3-mp05-cancel-churn-newest | 70.5 | 65.0 | −7.8% |
| t3-mr-cancel-replace-churn | 99.4 | 92.9 | −6.5% |
| t3-eq-deterministic-baseline | 20.4 | 20.2 | −1.0% |
| t3-as01-base-mix | 26.2 | 24.0 | −8.4% |
| Sum | 893.1 | 832.2 | −6.8% |

A first, non-interleaved comparison had shown sub14 slower (it ran second, on a machine that had warmed up); the interleaved one is the one to trust, and it is still warm laptop timing.

#### 9.8.10 sub15: the files are written while the simulation runs

sub15 = sub14 + one writer thread per output file that encodes, hashes and writes finished rows during the run.

- **Writer** (`pqf::Stream` in `pq_fast.hpp`): `add_group(r0, k)` encodes and writes one row group and needs only the rows of that group; `finish()` writes any deferred columns for all groups and the footer. Row groups hold 2^14 rows.
- **What is final when.** A ledger record is final once written (`Engine::lrec_done`). A trace row is final once its bucket is closed (`Engine::trace_closed`), except for its `kind`, because a fill only becomes a final fill at the end. So the trace's `msg_type` column is deferred and written after all other chunks. Parquet locates each column chunk by its own offset, so the chunks of one row group need not be adjacent; pandas reads the files back as equal tables.
- **Buffers that move.** A row buffer that outgrows its reservation is copied to a new one. The old one is kept until the engine is destroyed (`Buf::keep_old`), and the current pointer is published atomically, so a reader holding an older pointer still sees valid, identical rows.
- **Threads.** During the run: the simulation, the latency helper, and one or two writers, which is within the quota of four. A writer sleeps 100 µs when it has nothing to do. When the run ends, a writer finishes the last partial group, the deferred column and the footer. A batch worker has no writer threads and writes after the run, as before.
- **Determinism.** Group boundaries depend only on the row index, so the bytes do not depend on thread timing.

Checks so far: tables 65/65; six no-ledger units 6/6; eight repeated runs of four scenarios byte-identical, and identical to the files written with `T3_TRAIL=0` (no writer threads). Speed had not been measured when this was written: one check run on a busy machine showed much higher process times than usual, and contention could not be told from a real cost. sub15 ships only if a quiet-machine comparison shows it is not slower than sub14 and the full validation passes.

*(sub15 was never uploaded. Its engine reached the host as sub16 (§9.9.4), and writer threads during the run were measured there by the two sub17 uploads (§9.9.8).)*

#### 9.8.11 Housekeeping on the same day

- **Docker's data moved off the system drive.** The C: drive had 12.4 GB free. Docker Desktop's disk (10.7 GB) was relocated to `E:\DockerData` by setting `CustomWslDistroDir`; Docker created a fresh data disk there, and the five images in use were reloaded from a `docker save` archive made beforehand (`docker_backup/track3_images.tar`). The build cache was lost, so the next image build downloaded its packages again. C: then had 23.7 GB free.
- **Repository made publishable.** Git initialised; `.gitignore`, `.gitattributes`, `README.md`, `LICENSE` (Apache-2.0), `NOTICE`, `CITATION.cff`, `scripts/fetch_upstream.sh`, `sub/README.md` added. This document moved to `docs/REPORT.md`, with its parts and assemblers in `docs/report_src/`. Machine-specific absolute paths were removed from nine scripts and the two report assemblers. The organizers' checkouts, generated outputs, binaries and the submission descriptor are not tracked.
- **Deleted to free space** (about 1.9 GB, all regenerable outputs): `lab/e2e`, `lab/ab1`, `lab/reg_*`, `lab/batch_*`, `lab/rt`, `repro/out_sub5` to `out_sub8`, `repro/out_smoke`, validation output directories of sub7 and sub8, and old scratch outputs. **Earlier sections cite some of these directories as the location of raw outputs; those directories no longer exist.** Their summary logs and the JSON timing files in `lab/bench/` remain.
- **Two workspace directories removed.** `sub/build_submission.py` and `lab/run_reg.sh` loaded the organizers' toolkit from them (v2.4.0). Both now load `toolkit-v2.5.1`. Before the switch we checked that both versions seal a descriptor to the same digest, including the digest stored in the current `submission.json`; the first real run of the script after the switch produced the sub13 zip.
- **Author recorded** in this report and in the paper: Shashwat, Independent Researcher.

#### 9.8.12 Experiments of this section

| # | Experiment | Result | Decision |
|---|---|---|---|
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
| E92 | Upload limits read in the runtime guide | 5 per day, 20 in total | Bundle validated changes; no upload for small predicted gains |
| E93 | sub12: streaming writer | Fully validated; peak memory 92 → 88 MB | Folded into sub13 |
| E94 | sub13: pooled threads, scratch reuse, allocator settings, thread cap, agent layout | Fully validated; uploaded | Score pending |
| E95 | sub14: trace in final order during the run | 65/65 first time; −6.8% warm on seven units; 89 → 66 MB | Full validation |
| E96 | sub15: writer threads during the run | Correct and byte-stable; speed not yet measured | Measure on a quiet machine, then validate |
| E97 | Toolkit v2.4.0 against v2.5.1 descriptor sealing | Identical digests | Scripts repointed |

*(Later results: E92, the total is 23, not 20 (§9.9.1); E94, sub13 scored 184,046.62 (E98); E96, see E103 and, for the host, E116 and E117.)*

#### 9.8.13 Hypotheses of this section

| ID | Hypothesis | Test | Outcome |
|---|---|---|---|
| H54 | The memory work of sub8 and sub9 is worth about 3% on the host | E82 | **Refuted** (−0.8%) |
| H55 | The scorer does not need a ledger on units whose card says so | E83, E85 | **Confirmed** in the code and by a valid score |
| H56 | The ledger skip is worth 2–3K | E85 | **Exceeded** (+5.3K) |
| H57 | Huge-page requests and up-front population cost time on the host | E90 | **Not supported**: switching them off changed nothing measurable |
| H58 | Switching them off costs time on the host, as it does on the laptop | E90 | **Refuted** |
| H59 | The CPU quota throttles our threads | E89 | **Refuted locally**; unknown on the host |
| H60 | The fixed cost per container is about 0.55 s (§9.5) | Leader's score; second review | **Refuted**: it must be at most 0.47 s |
| H61 | Warm best-of-N timing predicts the direction of a host score | E82, E85, E90 | **Refuted** for memory-related changes; held for removed work |
| H62 | Per-run overheads (threads, allocation) are visible on the host | E94 | **Open** (sub13 pending) |
| H63 | Building the trace in order during the run removes real work | E95 | **Supported locally** (−6.8% warm, −26% peak memory); host unknown |
| H64 | Writing the files during the run is a net gain | E96 | **Open** |
| H65 | 210,000 is reachable by the Development deadline | Second review: about 18% | **Open** |
| H53 | 240,000 is reachable by the Development deadline | Second review: 1–2% | **Open; very doubtful** |

*(The current status of every hypothesis is in §15. H64 and H68 are one hypothesis under two numbers.)*

#### 9.8.14 Failures of this section

| Failure | Cause | Resolution |
|---|---|---|
| Three days of optimisation against warm laptop timing | The method was never checked against how the host runs a unit | `lab/cold_runs.sh`; uploads treated as the instrument; this section |
| The ledger rule was missed for nine days | The README section on `message_trace.parquet` was read for the output format, not for what may be omitted | Found by the first review; implemented the same day |
| Planning assumed only a daily upload limit | The total of 20 is in a toolkit document, not in the Track 3 README's summary | Found by the second review; plan changed |
| sub11's score cannot be attributed | It bundled a compiler change with a memory-mode change | Later uploads are described by what single question they answer |
| A first sub13-against-sub14 comparison showed sub14 slower | Not interleaved; the second image ran on a warmer machine | Interleaved rounds |
| A `sed` edit of a script failed and the measurement ran with the old script | `#` used both as the delimiter and inside the replacement | Edited through files; the run was repeated |
| A patch script stopped on its last assertion after rewriting two of three files | The assertion matched a comment | Files restored from the snapshot taken before the patch; assertion fixed; re-applied |
| "Is the submission stuck?" asked 14 and 30 minutes after an upload | Scores take 45–60 minutes | Checked the clock before answering; no upload was spent |

*(The total of 20 in the third row is the toolkit document's figure; the competition page allows 23: §9.9.1.)*

#### 9.8.15 sub13's score, a gap in sub14, and a step back to sub11's writer

Written at the end of the same day. It supersedes the "pending" remarks in §9.8.8, §9.8.9, §9.8.10, §9.8.12 (E94) and §9.8.13 (H62).

**sub13 scored 184,046.62** (upload 971360), 2.6% below sub11's 189,018.

- It changed five things at once (§9.8.8) and went up without a timing comparison against sub11.
- First explanation: its writer parallelises across row groups of 65,536 rows, so any file below that size is encoded on one thread, where sub11 encoded a file's columns on several.
- The measurement taken afterwards does not support it: over the 27 units under 60,000 rows sub13 took 802 ms against sub11's 873 ms (table below).
- The drop is 1.6 times the difference once seen between two identical uploads (§9.4). It may be partly noise.
- **We do not know which of the five changes, if any, cost the 2.6%.**

*(Later note: still not known. On the sub17 binary, writer threads during the run scored 1.6% above the same binary without them (199,285 against 196,165), so "a streaming writer loses on the host" is not a safe reading of sub13 (§9.9.8). On "partly noise" see the note in §9.8.2.)*

**Laptop measurement of six builds** (`lab/measure_builds.sh 2 3 sub9 sub10 sub11:off sub13:off sub14:off sub15:off`: all 65 single-scenario units from their unit directories, so the launcher sees each card; two interleaved rounds of three runs; best run per unit; sub11 and later with the memory switches off, as shipped; results in `lab/bench/fig_<tag>_<round>.json`, log in `lab/bench/measure_fig.log`):

| Build | All 65 (ms) | 27 units under 60K rows | 29 units 60K–200K | 9 units over 200K | Page faults (thousand) | Peak memory, largest unit (MB) | Output (MB) |
|---|---:|---:|---:|---:|---:|---:|---:|
| sub9 | 3,564 | 704 | 1,058 | 1,803 | 131 | 188 | 135.4 |
| sub10 | 3,778 | 851 | 1,238 | 1,689 | 103 | 92 | 95.1 |
| sub11 | 3,856 | 873 | 1,274 | 1,709 | 189 | 68 | 95.1 |
| sub13 | 3,624 | 802 | 1,314 | 1,509 | 184 | 65 | 95.2 |
| sub14 | 3,484 | 771 | 1,281 | 1,432 | 167 | 54 | 95.2 |
| sub15 | 3,638 | 798 | 1,220 | 1,619 | 134 | 53 | 97.3 |

*(Caveat found later: these times were measured from the unit folders and include 10 to 20 ms per run of input-mount time that the scoring host does not have (§9.9.3). They are left as measured.)*

The two rounds of one build differed by up to 14% (sub10: 4,499 and 3,940 ms summed per round), which is more than any difference between builds in the table. Since sub5 the laptop total has not moved outside that spread. The counts are firmer than the times: peak memory on the largest unit fell from 188 to 53 MB, and output from 135 to 95 MB.

**A gap in sub14 that its validation exposed.** sub14's full validation passed (tables 65/65, repeat-run bytes 65/65, batch 6/6, official regression 65/65, fuzz replay 1,318/1,318). But the replay's breakdown had changed:

| Build | Handled by the launcher | Handed to the Python path, native engine | Handed down to the reference path |
|---|---:|---:|---:|
| sub10 to sub13 | 1,295 | 23 | 0 |
| sub14 | 1,266 | 23 | 29 |

- `native/fuzz/decline_reasons.py` gave the reason for the 29: "engine failed during simulation". `native/fuzz/dump_case.py` (new) wrote them to `lab/bench/failcases/`.
- All 29 have `latency_config` `uniform` with `min_ns` −1,000,000: a negative latency. A message can then be delivered before the current time, the kernel's dispatch time goes backwards, and trace rows do not arrive in time order.
- Until sub13 the trace assembly had a full-sort path for exactly this. Its comment said "never observed". Building the trace during the run (§9.8.9) replaced it by a failed run.
- In the full image the outputs stayed correct, through two fallbacks. In a scratch image those units would have exited with an error. No public unit has a negative latency; a sealed unit could.

**The repair (in sub15).** `Engine::repair_trace()` runs when a row has arrived with an earlier time. It takes the bucket array apart into quote rows (in logging order) and order rows, regroups consecutive quote rows of one time (one row per side, last value, order of first appearance), sorts the order rows stably by (time, order id, owner), merges with a quote row ahead of the order rows of its time, and rebuilds the final-fill index. The writer thread of the trace file restarts its file (`FileSink::restart`) when that has happened. `t3_simulate` now prints the engine's error message under `T3_PHASES`.

Check (`lab/quick_checks.sh`, new): each of the 29 cases is run by the launcher with no Python reachable (`PATH=/nonexistent`), by sub13 and by sub15 with and without writer threads. All 29 are handled by the launcher in all three, and all 29 give tables equal to sub13's. An earlier version of this check reported "equal 29" for a sub15 image that still failed those cases: Python was reachable, so both sides were the reference path's output. The check was corrected before the result above was taken.

**sub15, as rebuilt.** Row groups of 4,096 rows (was 16,384), so that little is left at the end of the run even on small units; the repair above. Fast checks: tables 65/65; six no-ledger units 6/6; six repeated runs of five scenarios byte-identical and equal to the files written without writer threads; the 29 cases as above. Its full validation was started and then stopped to take timings, and has not been run.

**Timing of the writer threads is inconclusive.**

| Comparison | Conditions | Result |
|---|---|---|
| sub14 against sub15 (16,384-row groups), 7 units, 3 interleaved rounds | memory switches on, quiet machine | sub15 −13.7% (sum 1,033 → 891 ms) |
| sub14 against sub15 (4,096-row groups), 65 units, 2 rounds | switches off | sub15 +4.4% (3,484 → 3,638 ms) |
| sub14 against sub15 (4,096-row groups), 16 units, 3 rounds | switches off; absolute times two to three times the usual, so the machine was loaded | sub15 +12.5% (2,804 → 3,155 ms) |
| sub15 with against without writer threads, same run | as the row above | +1.8% with them |

The last row says the writer threads themselves made no difference in that run; what separates sub15 from sub14 there is the smaller row groups and one encoding thread per file. None of this is evidence about the scoring host.

**sub16: one change from the best-scoring build.** The engine of sub15 (trace in final order during the run, repair for out-of-order rows, agent fields regrouped) with sub11's writer restored as the default: files built after the run in row groups of up to 2^20 rows, a file's columns encoded on two to four threads, hashing on its own thread for large files. The writer threads of sub15 remain available through `T3_TRAIL=1`. Built; its fast checks were running when this was written.

*(What followed: sub16's validation passed on tables 65/65, repeat-run bytes 65/65, batch 6/6, the fallback run and official regression 65/65; its fuzz replay stopped at 200 of 1,318 when Docker failed ("unexpected EOF") (`lab/bench/validate_sub16.log`); a separate replay on the same image completed with 1,318 of 1,318 (§9.9.16). Its scratch image with the memory switches off was uploaded and scored 203,394.47: §9.9.4.)*

**Figures.** `paper/make_figures.py` now covers builds through sub15 (per-unit time, totals, page faults and peak memory), marks the two figures of the first fit as refuted, and adds two: the laptop's prediction against the host's score for each step, and the bound on the fixed cost.

| # | Experiment | Result | Decision |
|---|---|---|---|
| E98 | sub13 on the host | 184,047 (−2.6% against sub11) | Do not build further on sub13's writer until understood |
| E99 | Six builds, 65 units, warm (`lab/measure_builds.sh`) | Totals 3.48–3.86 s; rounds of one build differ by up to 14% | Laptop time cannot rank these builds |
| E100 | Breakdown of sub14's fuzz replay | 29 cases fell to the reference path | Investigate before any scratch image of sub14 |
| E101 | Reason and common feature of the 29 | Negative latency; rows out of time order | Restore exact handling |
| E102 | `repair_trace` and file restart | 29 of 29 handled by the launcher, tables equal to sub13's | Keep |
| E103 | sub15 with 4,096-row groups, three timing comparisons | −13.7%, +4.4%, +12.5% | Inconclusive; do not upload sub15 first |
| E104 | sub16: sub15's engine with sub11's writer | Built | Validate; candidate for the next upload |

*(E104: uploaded, 203,394.47 (E105, §9.9.4).)*

| ID | Hypothesis | Test | Outcome |
|---|---|---|---|
| H62 | Per-run overheads (threads, allocation) are visible on the host | E98 | **Not supported**: the build that removed them scored lower |
| H66 | sub13 lost because small files are encoded on one thread | E99 | **Not supported by the laptop**; untested on the host |
| H67 | Trace rows always arrive in time order | E100, E101 | **Refuted** for negative latencies |
| H68 | Writer threads during the run are a net gain | E103 | **Open**; local timing contradicts itself |

*(H68 was answered on the host, in favour of the writer threads on the sub17 binary: §9.9.8, §9.9.13.)*

| Failure | Cause | Resolution |
|---|---|---|
| sub13 uploaded without a timing comparison, bundling five changes | Machine busy; warm timing just discredited; haste to use the day's last upload | Score cannot be attributed. sub16 changes one thing |
| A slow path believed unused was removed | The code's own comment said "never observed"; the fuzz corpus had 29 cases | Restored; the replay's breakdown, not only its verdict, is now read after every validation |
| A check reported success for an image that still failed | Python was reachable in the test container, so the fallback produced the output | The check runs with `PATH=/nonexistent` and counts launcher exits |
| A test ran against the previous image | The rebuild had been moved to the background and had not finished | Image identifier checked before testing |
| A full validation was started and then stopped | A timing question had to be settled first and cannot share the machine | Order fixed: fast checks, timing, then validation |

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

@@SEC12@@@@SEC13@@