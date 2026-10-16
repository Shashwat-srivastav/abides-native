### 9.7 After sub5: review, research, sub7 → sub9

This section records everything done after sub5 was scored. It keeps its own experiment, hypothesis and failure tables (numbered on from §10 and §15) so that the record of this section is in one place.

#### 9.7.1 Self-review and fix list

After the sub5 score the whole project was reviewed critically (rating given: 5.5/10). The points, and what became of each:

| # | Criticism | Outcome |
|---|---|---|
| 1 | Days were spent on the engine while the Parquet encoder dominated; sub4 was shipped without profiling the whole process | Acknowledged; §16.8 |
| 2 | The timing harness had not been read | Read: `throughput/run_unit.py` builds `docker run --rm --cidfile … --network=none --cpus=N --memory=M [--gpus … -e NVIDIA_DRIVER_CAPABILITIES=…] -v in:/input:ro -v out:/output IMAGE simulate …` and `timer.py` times the whole subprocess with `time.monotonic` |
| 3 | The "output size costs time" theory was weak (`/output` is a bind mount; nothing in the public harness touches the files inside the timed window) | Not tested in isolation; the sub7 score (§9.7.6) is one bundled upload inside the reported noise and neither supports nor rules it out |
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

What this does and does not show: at the time we read it as ruling out image size, layer count, the absence of system libraries and output size (sub7's files are 5.6× smaller than sub5's) as major terms of the fixed cost. That reading is **not established**. It rests on one upload per side, and the pair bundled the image change with sub6's and sub7's output-encoding and process-time changes, so a gain from one could hide a loss from another; +1.85% lies within the noise later reported between identical images (§9.10.2). The full image's timing on the host was never measured. The choice of the full image for the Final (§9.10.4) was a risk decision (all-or-nothing correctness on sealed scenarios), not a measured one.

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

#### 9.7.9 Experiments of this section

The experiments of this section are E66 to E81 in §10.

#### 9.7.10 Hypotheses of this section

The hypotheses of this section are H44 to H53 in §15, which holds the current status of each. *(H51 was then tested on the scoring host by one upload per side, which showed no gain; within the reported noise, so not established either way: §9.8.2.)*

#### 9.7.11 Failures of this section

| Failure | Cause | Resolution |
|---|---|---|
| The first `\u` fix made 6 public scenarios unusable for the launcher | Their free-text descriptions contain `\u` escapes; the fix declined any escape | Caught by the next measurement (59 of 65 units reported); escapes are now decoded |
| A/B numbers taken during the fuzz replay were meaningless | Two heavy jobs on one machine | Timing only on a quiet machine; validation and timing no longer overlap |
| sub7 could not be shown faster than sub6 | The machine was a third slower in that session than in the previous one | Reported as unresolved; later builds measured with interleaved runs that agree |
| Compile error in the writer (`cannot bind rvalue reference`) | Explicit template argument defeated forwarding | One-line fix |
| Two status-file and patch commands failed on `\u` inside Python source passed through the shell | Python parsed `\u` as an escape | Written through files |
| A wait loop expired before the job it was watching | 9.5-minute limit of the waiting command | The job's own log is read, not the waiter's status |
| Prediction "200–225K if image shape matters" was the favoured case in our plan | Over-weighted indirect evidence (what leaders ship) against direct evidence (published Docker timings) | Recorded; H46 |

