# Agenthon 2026 · Track 3 (Accelerated Market Simulation): engineering report and reproduction guide

**Author:** Shashwat Srivastava (Independent Researcher) · **Team:** S2WISH (team 36)
**Track verbs:** `simulate`, `simulate-batch`
**Ranked metric:** events/sec, gated on exact semantics
The previous version is kept as `docs/report_src/REPORT_v1.md`. A shorter, illustrated version for publication is in `paper/` (`zenodo_report.pdf`, built by `paper/make_figures.py` and `paper/build_report.py`).

This document records what we built, why each decision was made, every measured result (including the experiments that failed), what was investigated and what it explained, the hypotheses tested and their outcomes, the limitations, and exactly how to reproduce the results. Numbers come from runs in this project, except where a source is named: the organizers' statements and calibration, other teams' reports, and the decision model's probabilities. One result has no number: sub16t's score was not recorded (§9.10.1). Anything not measured or not yet done is labelled as such. The reproduction kit lives in [`repro/`](repro/) and is described step by step in **§12**.

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
9. [Submission rounds: sub1 to the Final](#9-submission-rounds-sub1-to-the-final) (9.1–9.3: sub1 to sub3 under the old rule; 9.4–9.6: sub4 to sub6 under the new rule; 9.7: after sub5 was scored, sub7 to sub9; 9.8: sub9 to sub13 on the host, sub14 to sub16 built; 9.9: sub16 on the host, sub17, sub18, sub19 and five more scores; 9.10: the last Development upload and the Final)
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

### 0.1 Current status (after the Final)

Details and sources are in §9.9 and §9.10.

- **The Final is submitted and scored: 1,755,232.6496** (upload 993712, status Finished; events per second under the Final metric). The run summary listed no problems; it shows no per-unit outcomes, so this is not a unit-by-unit proof that every sealed scenario passed. The Final board is hidden until results are published: **no rank is known**. The Final score is not comparable with Development scores, because the Final times a different window (about 0.46 s per unit less, §9.10.2).
- **The Final image:** `slashalpha/agenthon-track3:native-final`, `sha256:44f825eb7b8a5e0276baea84aafe3c344bdbb927500dac2a6ac0782e05e93487`. It is sub16's engine, launcher and writer with two fixes found while preparing the Final (the last-resort ABIDES path crashed on the read-only root; the hand-over decision could depend on thread timing), in the full image with the exact Python fallback, with the memory and writer settings of the 203,394 run (§9.10.3, §9.10.4). It passed the full validation, including a fuzz replay of 1,318 of 1,318 and the forced reference path under the Final's restrictions. Choosing the full image over the scratch image was a risk decision, not a measured one: correctness on the sealed scenarios is all-or-nothing, and in a scratch image a scenario the launcher declines scores zero. The full image's timing on the host was never measured. Decision round 8 chose it with probability 0.97.
- **Best Development score: 203,394.4709** (sub16, scratch image `native-v16m`, upload 975649), **rank 10 of 50 teams** on the last board the team recorded (the board keeps a team's best score; the leader, fuzz, is at 231,024.2407; §1.1).
- **Uploads used: all 23 Development uploads (5 per day, 23 per person, read from the CodaBench competition API) and the one Final upload.** The 23rd Development upload, sub16t (the sub16 binary with writer threads on), scored below sub16; its exact score was not recorded (§9.10.1).
- **What remains:** the organizers' verification and the publication of results (rank, Final board), and the publication of this record. Nothing more can be uploaded.
- **A caution on noise:** another team reported identical images scoring up to 14% apart on the Development board (issue #37, §9.10.2). Every conclusion in this record that rests on one Development upload per side and a difference of a few percent is therefore **not established**; the observed scores stand. A 0.1% gap between two uploads means nothing.

**What this means for reading the report:**

| Part | Status |
|---|---|
| Correctness work (§7.1–7.3, §8) | Fully relevant: outputs must still match the reference exactly |
| Simulation-loop throughput numbers (§1.3, §7.4, §9.1–9.3) | Real measurements, but of a quantity that is no longer ranked |
| End-to-end container time (§7.6, §7.8, §7.9, §9.4–9.6) | The quantity that is ranked now |
| "Byte-identical" in §1.2, §7, §8, §9.1–9.4, §12.4 | Applies to sub1–sub4 and to the Python paths of every image. sub5 and later are checked by table equality (§9.5) |
| "10M" goal mentioned in older sections | Obsolete |
| Conclusions from one upload per side that differ by a few percent: the helper thread's +9.5% (sub16 against sub16 helper off), sub18's engine +4.4% (helper-off pair), writer threads +1.6% (sub17 pair), sub17's −3.6% and the reading "by elimination, its helper start-up", sub19a's −2.1% and +2.6%, sub16t "below sub16", sub10's +2.9%, sub11's +0.2%, sub13's −2.6%, sub9's −0.8%, sub7's +1.85% (§9.7–§9.10, §15) | One upload per side; within the reported noise; not established. Hypotheses confirmed or refuted only by such a pair are marked **Not established (one upload per side, within the reported noise)** in §15. The larger gaps (sub16 over sub11, +7.6%; sub5 over sub4, +18%) are kept as observed, one upload per side |
| "Image shape and output size are minor factors on the host" (§9.7.6) | Not verified: one bundled pair (sub5 → sub7, +1.85%) that also changed output encoding, inside the reported noise. The full image's timing on the host was never measured |
| Score-model fits and projections (§9.5, §16.10, and the three projections of §9.9.8) | Refuted by scores |
| The 0.471 s bound on the fixed per-container cost (§9.8.7) and the organizers' calibration (§9.10.2) | The calibration's 0.630–0.643 s is above the bound; the most likely reading is given once, in §9.10.2 |
| Laptop whole-process times taken from the unit folders (the `fig_*.json` files and the totals of §9.8.15) | Include 10–20 ms per run of input-mount time that the host does not have (§9.9.3) |
| "Shared host" and "busy host" as explanations of score differences (§1.1, §9.4, §9.8.2) | Written before the organizers' statement that the Track 3 host takes only Track 3 runs, one submission at a time (§9.9.2). Not established for the uploads concerned |
| Upload total of 20 (§9.8.7, §9.8.12, §9.8.14) | Wrong: 23 (§9.9.1) |
| Per-section experiment and hypothesis tables in §9.7–§9.10 | Replaced by pointers: §10 is the single experiment log and §15 the single hypothesis register, each with the latest result and status. Failure tables stay in their sections |
| Statements that the Final had not run, that uploads remained, or that the Final image was undecided | Superseded by §9.10 |

### 0.2 Earlier status, kept for the record

The status as written at earlier points, condensed; each item points to where it is told in full.

- **At the end of Development** six uploads after sub16 scored below it (scores in §1.1). At the time their scores were read as establishing that the latency helper thread is worth +9.5% on the host, that sub18's engine is 4.4% better than sub16's at equal helper setting, that writer threads gained 1.6% on sub17, and that sub17's 3.6% loss against sub16 was, by elimination, due to its changed helper start-up. Each of these rests on one upload per side and a difference within the reported noise: **none is established** (§9.9.8, §15). The combination those readings pointed to, **sub19a** (sub18's engine with sub16's helper code), scored 199,057.7311 (upload 977400), 2.1% below sub16; the reading that the helper code is worth 9.5% on sub16's engine but 2.6% on sub18's is likewise one upload per side and not established (§9.9.16). sub19a is byte-identical to sub16's output on 65/65 single units, passed the full validation (fuzz replay 1,318 of 1,318: 1,296 through the launcher, 22 handed to the Python path) and its scratch image passed its own checks (`native-v19a`, §9.9.9). sub19b (the older, branching heap step) passed the full validation and was never uploaded.
- **The host, as the organizers describe it** (§9.9.2, §9.10.2): a single machine that takes only Track 3 runs, one submission at a time, also used for the Final; the Final gives five runs per unit (a warm-up and four counted), 300 s per run, 4 CPUs, 16 GiB.
- **Local measurement** (§9.8.5, §9.9.3): the host runs each unit once in a fresh container, while we had timed warm repeated runs (fresh containers are two to five times slower on the laptop, whose Docker VM has under 3 GB of memory); the unit folders are a slow Windows mount that adds 10–20 ms per run. Hardware counters on one thread became the local instrument. Laptop timing did not predict the host: three score projections made from it were all wrong (§9.9.8).
- **A correctness finding, fixed in the Final image** (§9.9.10, §9.10.3): the number of fuzz cases handed to the Python path varies between builds (22 to 27) and, on one build, between a full replay and a launcher-only pass (22 against 23). In a scratch image such a case exits with an error and the unit scores zero; no public unit is affected. A fix for sub18's engine stayed in the source only; a fix for sub16's engine ships in the Final image.
- **Decisions open at the end of Development:** the last upload went to sub16t (§9.10.1); the Final image is the full image (§9.10.4); the fix above is in it; our own fixed per-container cost on the host was never measured (per-unit host results were never obtained), and the organizers' calibration is discussed in §9.10.2.
- **The scoring change** (§2.2): until then the board ranked self-reported simulation-loop events/sec, capped at 10,000,000 per unit, and sections 5–9.3 were written under that rule (we went 4,862 → 4,260,093 → 8,340,072, now history). Since then it ranks the verified event count divided by the container time from creation to removal, one run per unit. When sub4 was uploaded the leader stood at 212,671; nobody can approach 10M under this rule.
- **sub4 to sub6** (§9.4–§9.6): sub4 scored 153,825 (rank 9 of 17 scored teams; an earlier upload the same day scored 151,387). sub5 scored 181,496 (+18% over sub4, one upload per side; below our estimate of 185–220K) by replacing Arrow's Parquet encoder with a built-in writer (§7.9); its files are no longer byte-identical to the reference but read back as the same tables, and the organizers' regression passes 65/65 (risk in §11.1). sub6 was built and validated and never pushed. The asked-for 300,000 lies beyond the ceiling of the score model of the time (§9.5, §16.10); that model was later shown to be wrong (§9.8.7: the leader's 231,024 requires a fixed container cost of at most 0.47 s, not the fitted 0.55 s).
- **sub7 to sub13** (§9.7, §9.8): the scratch image (sub7, 2.2 MB, no Python) scored 184,858; the stored fuzz corpus was replayed, 1,318 of 1,318 (§9.7.2). sub8 and sub9 cut page faults by 66% and laptop process time by 12.5% and 12.1%; sub9 scored 183,420, sub10 (no ledger on the six units whose card does not require it) 188,687 and sub11 (huge pages and up-front buffer population off, which costs about 70% on the laptop) 189,018. sub13 (five bundled changes) scored 184,047. The differences between these uploads are within the reported noise (§0.1). sub14 and sub15 were built locally (§9.8.9, §9.8.10); sub16 put sub15's engine behind sub11's writer and scored 203,394 (§9.9.4).
- **Upload budget:** first planned with the daily limit only, then taken as 20 in total from `toolkit-v2.5.1/docs/DEVELOPMENT-RUNTIME.md`, and finally read as 23 per person from the competition API (§9.9.1).
- **This document lives at `docs/REPORT.md`**; some output directories cited in earlier sections were deleted to free disk space (§9.8.11).

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
| **sub16t (scratch)**: the sub16 binary with writer threads on (`T3_TRAIL=1`, §9.10.1); the last Development upload | `native-v16t`, `sha256:b0478b41…03f32602` | below sub16; exact score not recorded |

Last Development board the team recorded (50 teams; the board keeps a team's best score):

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

Uploads used: all 23 Development uploads (5 per day); the last was sub16t.

Final (one upload per person; public and sealed units; five runs per unit, rate from the median of the four after the warm-up, each timed `StartedAt → FinishedAt`; §9.10):

| Submission | Image digest | Final score |
|---|---|---|
| **Final**: sub16's engine, launcher and writer with the two fixes of §9.10.3, in the full image with the exact Python fallback | `native-final`, `sha256:44f825eb…05e93487` | **1,755,232.6496** (upload 993712, Finished, no problems listed). Rank unknown until results are published. Not comparable with Development scores |

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
| Scratch image: binary identical, batch 6/6, regression 65/65, no-ledger units 6/6 | yes (`sub16m`) | yes (`sub17n`, `sub17t`) | yes (`sub18n`, `sub18h0`) | yes (`native-v19a`, §9.9.9) |

sub19b is byte-identical to sub16's output on 65/65 single units; its full validation passed later (§9.9.16).

Correctness of the Final image (`native-final`, §9.10.4):

| Check | Final |
|---|---|
| Output against the sub16 binary, 65 single units, helper on and off | Byte-identical |
| Tables, 65 scenarios | 65/65 |
| Same bytes in three repeated runs | 65/65 |
| Batch units under the runtime restrictions | 6/6 |
| Organizer's regression | 65/65 (and again on the image with the memory settings) |
| No-ledger units | 6/6 |
| Fuzz replay of 1,318 stored cases | 1,318/1,318 (1,296 launcher, 22 Python path) |
| Forced reference path under the Final's restrictions | Single unit equal to the reference tables (604 and 664 rows); batch unit completed |
| Pushed image pulled back by digest, one unit under the restrictions | Tables equal to the reference (71,932 and 63,287 rows) |
| Final run summary (upload 993712) | No problems listed; per-unit outcomes not shown |

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

In a later, slower session the same measurement gave sub16 2.228 s, sub17 (writer threads off) 2.152 s and sub18 1.876 s, so only ratios within one session mean anything. On the host the order was different: sub16 scored above both sub17 variants, one upload each and within the reported noise (§0.1, §1.1).

---
