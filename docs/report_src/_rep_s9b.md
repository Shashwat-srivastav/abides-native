### 9.5 sub5 → 181,496 (+18% over sub4)

Image `slashalpha/agenthon-track3:native-v5`, `sha256:eb90d781431939ce0357290851f4b08f178dfd654d5de2e53feaefa4f117ab06` (773 MB). Contents: §7.9. The team approved the push ("lets submit sub5 in parallel"); `sub/submission.json` was updated to this digest. Building `submission.zip` and uploading are the team's steps (§12.9).

**Score.** Submission 969765 finished with **181,495.8931** (CodaBench). That is +18.0% over sub4's 153,825 (one upload per side; larger than the spread reported between identical images, §9.10.2, but not repeated). It is **below the 185–220K range our model gave beforehand** (the "Estimate" paragraph further down, kept as written). The board was not re-fetched after this upload, so the new rank is not recorded here; against the board fetched earlier that day the score would sit just under the then 8th place (181,826).

**Re-fit with two scores.** With sub4 = 153,825 and sub5 = 181,496 the two-parameter model has one solution: host-speed factor k = 0.50 (their host runs our process about twice as fast as this laptop) and fixed overhead 0.551 s per container. With those values the model gives sub6 = 183,095 and a zero-process-time ceiling of **208,565**.

**That ceiling is below the leader's 231,024, so the model is incomplete.** Something it does not contain matters. Candidates, none tested:

| Candidate | What it would mean | How to test |
|---|---|---|
| Output size costs container time on their host (slow `/output` volume, or the harness handling the files before it removes the container) | sub5 lost part of its gain to files 2.6× larger than sub4's; sub6 (5.6× smaller than sub5, 2.1× smaller than sub4) would gain clearly more than the modelled 1% | Upload sub6 |
| The scored roster differs from the 65 public units (6 batch units, other sizes) | Per-unit weights in the model are wrong | Cannot be tested from here |
| The overhead is not one constant (it varies by unit, or teams with smaller images or fewer layers start faster) | Part of the "fixed" cost is ours to reduce | Image-size experiment (e.g. a much smaller runtime image) |
| Run-to-run variation on the shared host | The two scores are each a single run; our two sub4 uploads differed by 1.6% | Re-upload the same image |

*(What became of these candidates: output size and image shape were never isolated. The sub7 scratch upload scored 1.85% above sub5, but it was one bundled pair (it also changed the output encoding and process time), one upload per side, inside the reported noise (§9.7.6, §9.10.2); the full image's timing on the host was never measured, so neither factor is shown to be minor. The fitted model itself was shown to be wrong (§9.8.7); on run-to-run variation see the note in §9.4, which also applies to "the shared host's run-to-run variation" in the last paragraph of this section.)*

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

