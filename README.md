# A bit-exact native reimplementation of the ABIDES market simulator

This repository holds a C++ reimplementation of the [ABIDES](https://github.com/jpmorganchase/abides-jpmc-public) agent-based market simulator, as pinned by the Agenthon 2026 Track 3 (simulation) benchmark. For every scenario of that benchmark it produces the same order trace and message ledger as the Python reference, row for row and value for value, and it does so in a single static binary that starts in a few milliseconds.

It was written as a competition entry by Shashwat (Independent Researcher, team S2WISH). The work is described in the report in [paper/](paper/), and every experiment, including the failed ones, is recorded in [docs/REPORT.md](docs/REPORT.md).

## The problem

Agenthon 2026 Track 3 asks participants to make the ABIDES market simulator faster without changing what it computes.

- **Input:** a scenario file (agents, order flow, latency model, seed), alone or in a batch of several markets.
- **Required output:** the order trace, and on most units the message ledger, as Parquet files whose tables equal the Python reference exactly: same rows, same order, same values. The event count must match the reference on every unit.
- **Score:** for each unit, verified events divided by the time the organizers' harness measures for the whole container, from creating it to removing it. The score is the mean over 71 public units (65 single scenarios and 6 batches). Each unit runs once in a fresh container limited to 4 CPUs and 16 GiB, with no network and a read-only file system.
- **What this makes hard:** container start-up, parsing, simulation, Parquet encoding, hashing and exit are all inside the measured time, so a fast event loop alone is worth little. Exactness rules out any shortcut that changes a random draw, a rounding or the order of two events.

The Final phase of the competition times one submission per team on the same machine, on units that are not public, five runs per unit.

## Results

**Best result: 203,394 events per container-second** (build sub16), rank 10 of 50 teams on the Development (practice) board at its last reading, when the leader stood at 231,024. The starting point under this rule, a native engine behind the reference packaging, scored 153,825. In the simulation loop alone, which an earlier scoring rule measured, the engine reported 8.34 million events per second against 4,862 for the unmodified Python reference.

The best solution in brief (sub16):

- **One static binary in a 2.3 MB single-layer image.** No interpreter and no shared libraries to load, so almost none of the measured time goes to start-up.
- **A bit-exact C++ engine.** Kernel, exchange, order book, agents and NumPy's legacy random streams are reimplemented so that every draw, rounding and event order matches the Python reference.
- **The trace is built in its final order while the simulation runs.** Nothing is merged, sorted or indexed afterwards.
- **A helper thread draws the latency stream ahead of the event loop,** which takes the most expensive arithmetic out of the main thread.
- **An own Parquet writer** emits dictionary and delta-encoded columns straight from the engine's records, on two to four threads, with a built-in SHA-256.
- **No unneeded output.** The message ledger is skipped on units whose card does not require it.
- **A profile-guided build,** trained on the public scenarios.

Every scored upload, in order:

| Build | What changed | Score |
|---|---|---:|
| sub4 | Native engine, launcher without Python, Arrow Parquet writer, 773 MB image | 153,825 |
| sub5 | Own Parquet writer and SHA-256, static launcher | 181,496 |
| sub7 | Delta-encoded integers, direct ledger encoding, 2.2 MB single-layer image | 184,858 |
| sub9 | Memory work: fewer page faults and passes over memory | 183,420 |
| sub10 | No message ledger on the six units whose card does not require one | 188,687 |
| sub11 | Profile-guided build, earlier exit, huge pages and buffer pre-population off | 189,018 |
| sub13 | Output streamed in row groups, pooled threads | 184,047 |
| **sub16** | Trace built in its final order during the run; no merge, sort or index pass afterwards | **203,394** |
| sub17 | Branch-free event-queue step; helper thread started earlier | 196,165 |
| sub17, writer threads on | The same, with both files written during the run | 199,285 |
| sub16, helper off | The sub16 binary with its latency helper thread switched off, to measure it | 185,818 |
| sub18, helper off | Leaner engine (compact trace rows, less bookkeeping), helper thread off | 193,962 |
| sub19a | sub18's engine with sub16's helper-thread code | 199,058 |

What the scores established:

- **Output, not simulation, was the first bottleneck.** In sub4 the event loop was 7–15% of a unit's process time and Parquet encoding through Arrow 50–63%. Replacing it raised the score by 18%.
- **A helper thread that draws latencies ahead of the event loop is worth 9.5%** on sub16's engine (same binary, one setting apart), but only 2.6% on the faster sub18 engine. The two gains did not add up, and why is not established.
- **Laptop timings did not predict the scoring host.** They gave the wrong sign for four of nine steps between scored builds. Uploads that change one setting were the only reliable instrument.
- **The gap to the leader is not explained.** No model of fixed container cost plus process time fits our own scores, and the host returns one number per upload with no per-unit detail.

Correctness is checked before speed on every build:

- **Public scenarios:** all 65 produce tables equal to the reference, and the organizers' regression suite passes 65 of 65.
- **Batch units:** all 6 pass under the benchmark's runtime restrictions.
- **Differential fuzzing:** 1,318 stored cases with recorded reference hashes all reproduce.
- **Determinism:** three repeated runs of every scenario give byte-identical files.

## How it works

- **Engine** ([native/engine/engine.cpp](native/engine/engine.cpp)): the discrete-event kernel, exchange, order book and agents. Floating-point results match CPython and NumPy bit for bit, so the build uses `-ffp-contract=off` and never `-ffast-math`.
- **Random numbers** ([native/rng/np_random.hpp](native/rng/np_random.hpp)): NumPy's legacy `RandomState` streams, reproduced exactly.
- **Launcher** ([native/engine/launcher.cpp](native/engine/launcher.cpp)): the `simulate` and `simulate-batch` commands, the scenario parser and the output threads.
- **Parquet writer** ([native/engine/pq_fast.hpp](native/engine/pq_fast.hpp)): a small writer that emits dictionary and delta-encoded columns directly from the engine's records.
- **Fallback:** the full image also carries the reference Python stack. A scenario the launcher declines is handed to it, so the output is always the reference's. The scratch image has no fallback.

## Repository layout

| Path | Contents |
|---|---|
| [native/engine/](native/engine/) | Engine, launcher, Parquet writer, SHA-256, and the table and timing check tools |
| [native/rng/](native/rng/) | NumPy-compatible random number generation and its tests |
| [native/fuzz/](native/fuzz/) | Differential fuzzer, stored corpus and replay tools |
| [native/refdump/](native/refdump/) | Tools that dump reference state to find the first divergence |
| [native/pkg/](native/pkg/) | Python package that drives the engine as a shared library (fallback path) |
| [sub/](sub/) | Submission image: Dockerfiles, reference adapter and patches |
| [repro/](repro/) | Reproduction kit: baseline against candidate, identity and regression steps |
| [lab/](lab/) | Validation and benchmark scripts, measurement data, source snapshots of scored builds |
| [paper/](paper/) | Illustrated report (Markdown, HTML, PDF), figures and the scripts that build them |
| [docs/](docs/) | Full laboratory record and the parts it is assembled from |

## Getting started

You need Docker and a POSIX shell (Git Bash works on Windows). The benchmark's scenarios and harness are not redistributed here; fetch them first.

```sh
sh scripts/fetch_upstream.sh          # organizer repositories, pinned
sh lab/sync_sub.sh                    # copy native sources into the image build context
docker build -t agenthon-track3:dev-native sub/
```

Run one scenario the way the benchmark does:

```sh
docker run --rm --network none --read-only --user 65534:65534 --cpus 4 \
  -v "$PWD/track3-upstream/regression_suite/scenarios:/input:ro" \
  -v "$PWD/out:/output" \
  agenthon-track3:dev-native \
  simulate --config /input/mp07_heavy_flow_oldest.json --out /output/trace.parquet
```

Build the minimal image (launcher only, no Python fallback) from a full image:

```sh
docker build -f sub/Dockerfile.min --build-arg BASE=agenthon-track3:dev-native \
  -t agenthon-track3:dev-native-scratch sub/
```

## Validation

```sh
bash lab/validate_image.sh <tag>      # for the image agenthon-track3:<tag>
```

This runs the table comparison on all 65 scenarios, the repeat-run byte check, the 6 batch units under runtime restrictions, the forced-fallback run, the organizers' regression suite and the fuzz replay. It takes about 35 minutes on a laptop. `bash lab/check_skip.sh <tag>` covers the units that need no message ledger.

The reference outputs that the comparisons read are produced by the reproduction kit; see the header of [repro/repro.sh](repro/repro.sh).

## Rebuilding the report

```sh
python paper/make_figures.py          # figures from the data in lab/bench/
python paper/build_report.py          # HTML, and PDF through a headless Chromium-based browser
python docs/report_src/assemble_1.py && python docs/report_src/assemble_2.py   # docs/REPORT.md
```

## Limitations

- **Scope:** only the scenario features used by the Track 3 benchmark are implemented natively. Anything else is declined and handled by the reference stack.
- **Timing:** all local timings come from one laptop under Docker Desktop and are noisy. Leaderboard scores are the only measurements from the scoring host, and they come without per-unit detail.
- **Floating point:** the launcher derives one latency parameter with glibc's `log` where the reference uses NumPy's. A guard declines any run in which the difference could change a rounding; it has not been tested on AVX-512 hardware by us.
- **Declined inputs:** the launcher hands a scenario it is not certain about to the reference stack. The scratch images used for scoring have no reference stack, so such a scenario fails there. None of the 71 public units is declined.
- **Byte identity:** outputs equal the reference as tables. The Parquet files themselves are not byte-identical to the reference's.
- **Status:** these are Development-phase results. The competition's Final phase had not been run when this was written.

## Licence and attribution

The code in this repository is released under the [Apache License 2.0](LICENSE). Files derived from the organizers' baseline keep their original licence; see [NOTICE](NOTICE). ABIDES, the benchmark scenarios and the organizers' toolkit are not part of this repository.

To cite this work, see [CITATION.cff](CITATION.cff).
