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
