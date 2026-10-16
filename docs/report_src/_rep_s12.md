## 12. Reproduction guide

The kit in [`repro/`](repro/) automates every step:
- `repro/repro.sh`: the driver, one step per invocation;
- `repro/run_resilient.sh`: runs a list of steps with retry, resume and Docker restart (for machines where Docker itself may die, §16.6);
- `repro/in_container_run.py`: runs all scenarios inside one container (the reference in one process per scenario; the submission through its real `simulate` command) and re-hashes every output file;
- `repro/compare.py`: identity, self-reported rate and whole-process time report;
- `repro/Dockerfile.rng`: RNG test toolchain.

§12.7 records the kit's own end-to-end run on the machine described in §14.1. Where §12.4 to §12.6 say "sub5/sub6", the same holds for every later build: all of them write their own Parquet encoding and are checked by table contents. §12.10 lists the checks and measurements used for the builds from sub7 on.

### 12.1 Prerequisites

| Requirement | Version used | Notes |
|---|---|---|
| OS | Windows 11 + Git Bash, or Linux with bash | The kit handles both path styles |
| Docker | Desktop 29.7.2 (WSL2 engine) | Must be able to build `linux/amd64` |
| RAM | 5.99 GB host, with one worker | Marginal: Docker crashed twice (§16.6). 8 GB or more is advisable; the original ABIDES needs about 2 GB for the largest scenario |
| Disk | ~6 GB free | Images ~0.8 GB each plus outputs |
| Python (host) | 3.12.6 | Only for `compare.py` and the official harness |
| Network | Needed for builds, pulls and clones only | All runs use `--network none` |

### 12.2 Get the sources

```bash
# 1. This project (contains sub/, native/, repro/, lab/, REPORT.md)
cd E:/NeurIPS/agenthon            # or wherever the project lives

# 2. Scenarios, batch units and reference traces: the checkout used throughout
git clone https://github.com/Agenthon-2026/track3-simulation-public.git track3-simulation-public-clone
git -C track3-simulation-public-clone checkout 4cc7882eed85153e9c06667738c87882b2deec90
#    (reference traces under regression_suite/reference_traces/ are generated locally with the
#     repository's own tooling from the baseline image; they are not committed upstream)

# 3. Current organizer harness, used by the `official` step
git clone https://github.com/Agenthon-2026/track3-simulation-public.git track3-upstream
git -C track3-upstream checkout bffb57227f796f9fa769a23d01fc364bee14a119

# 4. Organizer toolkit at the tag the harness requires (used from the checkout; nothing is installed)
git clone --depth 1 --branch v2.5.1 https://github.com/Agenthon-2026/Agenthon2026-public.git toolkit-v2.5.1
```

Other locations can be given with `PUBLIC_REPO`, `HARNESS_REPO` and `TOOLKIT` (see the header of `repro/repro.sh`). The harness needs its Python dependencies (numpy, pandas, pyarrow, scipy) on the host.

### 12.3 One-shot

```bash
bash repro/repro.sh all     # env, build, baseline, candidate, identity, batch, official
bash repro/repro.sh rng     # optional, ~10 min: RNG bit-exactness matrix
bash repro/repro.sh ab 3    # optional: 3 interleaved rounds, baseline vs candidate
```

On a memory-constrained machine use the resilient driver instead:

```bash
IMAGE=agenthon-track3:repro bash repro/run_resilient.sh repro/out/run.log env build baseline candidate identity batch rng official
```

Outputs go to `repro/out/`. Each step is also callable on its own (§12.4).

### 12.4 Step by step: what each does and what you should see

| # | Command | What it does | Expected result |
|---|---|---|---|
| 1 | `bash repro/repro.sh env` | Prints versions; checks 65 scenarios and 6 batch units; shows harness and toolkit revisions | `scenarios: 65`, `batch units: 6`, harness `bffb572`, toolkit `v2.5.1` |
| 2 | `bash repro/repro.sh build` | `docker build sub/` → `agenthon-track3:repro` | `built agenthon-track3:repro: sha256:…` (the ID differs from ours; §11.3) |
| 3 | `bash repro/repro.sh baseline` | Runs the **original ABIDES image** (`slashalpha/agenthon-track3:dev`, public) on all 65 scenarios, one process per scenario | 65 rows `path=reference`, a few thousand events/s each |
| 4 | `bash repro/repro.sh candidate` | Runs the image's real `simulate` command on all 65 scenarios | 65 rows `path=launcher` (any `python-native` or `abides-fallback` row means the launcher declined that scenario) |
| 5 | `bash repro/repro.sh identity` | Compares SHA-256 of both Parquet files per scenario, recomputed from disk | `identical: 65/65`; exit code 0 **for sub1–sub4**. For sub5/sub6 this step reports 0/65 by design (different, equally valid Parquet bytes); use the table check in §12.5 instead |
| 6 | `bash repro/repro.sh batch` | Runs baseline and submission `simulate-batch` on the 6 units | 6/6 units identical (30 subs) for sub1–sub4; for sub5/sub6 use `check_batch_tables.py` (§12.5) |
| 7 | `bash repro/repro.sh official` | Organizer's `run_regression.py` (upstream harness, toolkit v2.5.1, 1 worker, BLAS threads limited) | `{'total_scenarios': 65, 'passed': 65, 'failed': 0, 'errored': 0}` |
| 8 | `bash repro/repro.sh rng` | 478M-draw numpy-vs-C++ matrix | `OVERALL: PASS` |
| 9 | `bash repro/repro.sh ab 3` | Interleaved baseline / candidate rounds | Candidate self-reported rate ≈ 1,000× baseline |

`RESUME=1` makes steps 3 and 4 keep scenarios finished by an interrupted run. Measured durations are in §12.7.

Quick smoke test on two scenarios (measured here: 2/2 identical, both through the launcher; reference 49.4 s of process time, launcher 3.1 s):

```bash
export ONLY=eq_deterministic_baseline,mp07_heavy_flow_oldest OUT=$PWD/repro/out_smoke
bash repro/repro.sh baseline && bash repro/repro.sh candidate && bash repro/repro.sh identity
```

### 12.5 Verifying the exact submitted images (no rebuild)
Point the kit at a published digest:

```bash
IMAGE=slashalpha/agenthon-track3@sha256:697ae5de6d95b1fce2bd467375060a10f4f343a04a00d00a989b38e5869d85c7 bash repro/repro.sh candidate   # sub4
bash repro/repro.sh identity
```

**sub5 and sub6** are checked by table contents, against outputs of an image whose bytes are verified (sub4, or the baseline itself):

```bash
# 1. reference outputs: sub4 (byte-identical to the baseline, step 5) or the baseline image
IMAGE=slashalpha/agenthon-track3@sha256:697ae5de6d95b1fce2bd467375060a10f4f343a04a00d00a989b38e5869d85c7 bash repro/repro.sh candidate
# 2. run sub5 on every scenario and compare tables, hashes and counts (expect: checked 65, bad 0)
IMG=slashalpha/agenthon-track3@sha256:eb90d781431939ce0357290851f4b08f178dfd654d5de2e53feaefa4f117ab06
docker run --rm --cpus 4 \
  -v "$PWD/track3-upstream/regression_suite/scenarios:/sc:ro" \
  -v "$PWD/repro/out/candidate:/stored:ro" -v "$PWD/native/engine:/eng:ro" \
  $IMG python /eng/check_fast.py /sc /stored
# 3. batch units: run each under the runtime restrictions, then compare (expect: batch units bad: 0)
for unit in track3-simulation-public-clone/units/t3-gbatch-*; do u=$(basename $unit); mkdir -p out5/$u
  docker run --rm --network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 \
    --tmpfs /tmp:size=64m,noexec -v "$PWD/$unit/scenarios:/input/scenarios:ro" -v "$PWD/out5/$u:/output" \
    $IMG simulate-batch --batch-dir /input/scenarios --out-dir /output; done
docker run --rm -v "$PWD/out5:/new:ro" -v "$PWD/repro/out/batch_candidate:/old:ro" \
  -v "$PWD/native/engine:/eng:ro" $IMG python /eng/check_batch_tables.py /new /old
# 4. the organizers' gates
IMAGE=$IMG OUT=$PWD/repro/out_sub5 bash repro/repro.sh official
```

On Windows Git Bash use `E:/…` style paths for `-v` and `export MSYS_NO_PATHCONV=1`. Our results for these four steps are in §9.5.

Digests of sub1–sub3 are in §14.5. Those images have no launcher; the kit labels the code path from stderr messages only sub4 emits, so their rows are also printed as `path=launcher`. Ignore the label for them; the hash comparison is the same.

### 12.6 What is and is not exactly reproducible

| Quantity | Reproducible? |
|---|---|
| Table contents of both output files (what sub5/sub6 are checked on) | **Exactly** |
| Output bytes of sub5/sub6 | Exactly between runs of the same image: 65/65 units gave the same SHA-256 for both files in 3 consecutive runs, for each image. They differ from the baseline's bytes by design |
| Output bytes (`trace.parquet`, `message_trace.parquet`) and their SHA-256, sub1–sub4 and the Python paths | **Exactly**, on any x86-64 machine running these images, with one caveat: on AVX-512 hosts the *reference itself* may compute a log-normal latency parameter differently (§11.1) |
| Event and message counts | Exactly |
| Correctness verdicts (identity, official harness) | Exactly |
| Cycles and instructions per event (§7.7) | Instructions: closely; cycles: CPU-dependent |
| events/s, process times, `docker run` times | Machine-dependent; expect similar ratios between images, not the same numbers |
| Image digest after a rebuild | No (build timestamps and metadata); behaviour is identical |
| Leaderboard score | Depends on the organizers' host and, in Development, on a single run per unit. The organizers state that the host is one machine that takes only Track 3 runs; another team reported two runs agreeing to within 0.1% (§9.9.2), and later another team reported identical images scoring up to 14% apart on the Development board (issue #37, §9.10.2). We have no repeat upload of our own; differences of a few percent between single uploads are not established (§11.2) |

### 12.7 Results of our own end-to-end reproduction runs

@@REPRO@@

### 12.8 Reproducing the development experiments

| Experiment | How |
|---|---|
| Baseline profile (§5) | Run cProfile around `abides.run` in the baseline image (the script used, `prof-run/prof.py`, is no longer in the tree) |
| Phase A A/B (§6) | `lab/ab.py dev,cand1,cand2 3 <outdir>` (images built from `cand/`, `cand2/`; those directories are no longer in the tree, the overlays themselves are in `sub/perf/`) |
| Engine cycle counts (§7.7) | In a container with g++ and the sources mounted at `/native` (we used image `t3-native-perf`, started `--privileged` for the counters): `python dump_cfg.py <scenario.json> <name>.bin` for each scenario; `g++ -O2 -std=c++17 -ffp-contract=off -pthread -o bench bench.cpp engine.cpp`; `./bench 5 bins/*.bin`. For the sub3 engine substitute `engine_sub3.cpp` |
| Loop statistics (§7.7 B) | Same, with `-DT3_STATS`; one line per run on stderr |
| perf profiles (§7.4, §7.7) | `perf record -e cycles:u` (or `instructions:u`) around `bench`, built with `-g` |
| Identity of the engine through the Python path | `sh build.sh && python try_all.py /sc` with baseline outputs under `/base/<scenario_id>/events.json` |
| Identity of the launcher (§7.8) | Build as in `sub/Dockerfile`, then `python check_launcher.py <launcher> /sc`; batch: `check_batch.py` after running `simulate-batch` on each unit |
| Launcher phase timing (§7.8, §7.9) | `T3_PHASES=1 simulate --config … --out …` (sub5/sub6 print one line per file plus `parse= create= sim= out= | trace finish/build/emit | ledger finish/build/emit`) |
| Best-of-N process time per unit (§7.9) | Inside the image, with `--cpus 4 --shm-size 1g`: `python /eng/bench_units.py /sc /b/<name>.json 5 [unit …]`; results of our runs are in `lab/bench/*.json` |
| Table check of the built-in writer (§9.5) | `python /eng/check_fast.py /sc /stored [unit …]`; batch: `check_batch_tables.py <new> <stored>` |
| Portable SHA-256 path | Add `-e T3_SHA_PORTABLE=1` to the table check |
| Score model (§9.5) | Per-unit minima in `lab/bench/best_sub5_sub6.json` and `all_sub4.json`; score(overhead, k) = mean of events ÷ (overhead + k·time); overhead found by bisection so that sub4 gives 153,825. The model is refuted (§9.8.7, §9.9.6); the recipe is kept for the record |
| Host end-to-end timing (§1.4) | `python lab/e2e.py agenthon-track3:sub3,agenthon-track3:sub4 3 <scenario,…>` |
| Runtime-restriction check (§9.4) | `docker run --rm --network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 --tmpfs /tmp:size=64m,noexec -v <in>:/input:ro -v <out>:/output <image> simulate --config /input/scenario.json --out /output/trace.parquet` |
| Fuzzing (§8) | `native/fuzz/gen.py` / `mk_*.py` to generate, `driver.py` to run, `recheck.py` (Python path) or `recheck_launcher.py` (reference vs launcher vs Python path) to re-verify |
| Decision rounds (§4.2, §9.7.5, §9.9.6, §9.10.4) | not reproducible from this repository (scripts and raw responses are not deposited); the questions and answers of the eight rounds are in the sections cited |

The `lab/` scripts were written for this machine. They now find the project root from their own location (the absolute paths were removed, §9.8.11); several are meant to run inside the dev container `t3dev` (§14.1). The `repro/` kit is the portable version.

### 12.9 Building and uploading a submission
1. `bash lab/sync_sub.sh` copies the native sources into `sub/`; then `docker build --platform=linux/amd64 -t agenthon-track3:<name> sub/`.
2. Validate: `bash lab/validate_image.sh <name>` (§12.10), or steps 4–7 of §12.4 with `IMAGE=agenthon-track3:<name>`. The uploads since sub7 are scratch images built from `sub/Dockerfile.min` (build arguments `T3_HUGE`, `T3_PREFAULT`, `T3_TRAIL`) around the validated binary and checked with `bash lab/scratch_checks.sh <scratch tag> <full tag>`.
3. `docker tag agenthon-track3:<name> slashalpha/agenthon-track3:<tag> && docker push slashalpha/agenthon-track3:<tag>`
4. Copy the pushed digest into `sub/submission.json` → `image.digest`.
5. Run `python sub/build_submission.py`. It prompts for the **Team Key** (hidden), reseals the descriptor, and writes `sub/submission.zip`. Run this step yourself, in an ordinary terminal.
6. Upload `sub/submission.zip` on CodaBench under *My Submissions → Development* (5 uploads per day and 23 per person in total; §9.9.1). The Final phase (*Final & Verification*) allowed one upload per person (§9.10.2).

### 12.10 Checks and measurements used from sub7 on

These are the commands behind §9.7 to §9.9. Scripts under `lab/` are run from the project root in Git Bash; the last five rows run inside the dev container `t3dev` (§14.1), where `lab/` is mounted at `/lab`.

| Purpose | How | Where the result goes |
|---|---|---|
| Full validation of a full image | `bash lab/validate_image.sh <tag>`: tables of the 65 scenarios, repeat-run bytes (3 runs each), the 6 batch units under the runtime restrictions, a single run and a forced fallback run, the organizers' regression, the 1,318 stored fuzz cases. `bash lab/build_validate.sh <tag>` builds the image first; `bash lab/validate_rest.sh <tag>` runs only the last two stages | `lab/bench/validate_<tag>.log`, details in `lab/bench/val_<tag>/` |
| Fast checks before the long validation | `bash lab/quick_checks.sh <tag> [reference tag]`: tables, the six no-ledger units, repeat-run stability with and without writer threads, the 29 negative-latency cases with no Python reachable | standard output |
| Checks of a scratch image | `bash lab/scratch_checks.sh <scratch tag> <full tag>`: binary identical to the validated full image, batch 6, organizers' regression, six no-ledger units | `lab/bench/scratch_<tag>.log` |
| The last-resort ABIDES path under the runtime restrictions | `bash lab/ref_path_check.sh <tag>`: forces `T3_NO_LAUNCHER=1 T3_FORCE_REFERENCE=1` on one single unit and one batch unit under the Final's restrictions and compares the single unit's tables with the reference (§9.10.3) | `lab/bench/refpath_<tag>/` |
| Units that need no ledger | `bash lab/check_skip.sh <tag>` (§9.8.3) | terminal |
| Why the launcher declined a fuzz case | `native/fuzz/decline_reasons.py` (launcher only, `PATH` emptied); `native/fuzz/dump_case.py` writes cases out | `lab/bench/failcases/` |
| Fresh-container timing | `bash lab/cold_runs.sh <tag> <repeats> <unit> [docker run options]` (§9.8.5) | `lab/bench/cold_out/` |
| Warm timing of several builds, interleaved | `bash lab/measure_builds.sh <rounds> <repeats> <tag[:off]> …` (§9.8.15; reads the inputs from the unit folders, see §9.9.3) | `lab/bench/fig_<tag>_<round>.json` |
| Build of an image from an engine variant file | `bash lab/build_variant.sh <tag> <engine source file>` | `lab/bench/build_<tag>.log` |
| Process time with the inputs in memory | `python true_p.py <binary> <out_json> <repeats> [KEY=VALUE …]` (§9.9.3) | `lab/bench/truep_*.json` |
| Byte comparison of two launcher binaries on the 65 single units | `cmp_bins.sh <reference binary> <new binary> [environment for the new one]` | terminal |
| Table comparison of two launcher binaries on all 71 units | `python cmp_tables.py <reference binary> <new binary> [KEY=VALUE …]` | terminal |
| Hardware counters, one thread | `T3_LAT_THREAD=0 T3_TRAIL=0 perf stat -e cycles:u,instructions:u,branch-misses:u <binary> simulate …` (§9.9.3) | terminal |
| The image's profile-guided build, in the dev container | `build_pgo_dev.sh <output binary>` | the binary |

A scratch image with the helper thread off is made from an existing scratch image with `lab/bench/Dockerfile.nohelper` (`ARG BASE`, `FROM ${BASE}`, `ENV T3_LAT_THREAD=0`), which changes the image's environment and adds no layer (§9.9.8). `lab/bench/Dockerfile.trail` (`ENV T3_TRAIL=1`, sub16t) and `lab/bench/Dockerfile.memoff` (`ENV T3_HUGE=0 T3_PREFAULT=0`, the Final image) are used the same way (§9.9.16, §9.10.4).

---

## 13. File map

Paths that earlier versions of this table listed and that no longer exist are named in the last row.

| Path | Contents |
|---|---|
| `docs/REPORT.md` | This document, assembled by `docs/report_src/assemble_1.py` and `assemble_2.py` from the part files in `docs/report_src/`. `REPORT_v1.md` there is the frozen first version |
| `paper/` | Shorter illustrated version (`zenodo_report.md`, `zenodo_report.pdf`), `make_figures.py`, `build_report.py` |
| `repro/` | Portable reproduction kit (§12); `repro/out/full_run_sub4.log` is the log behind §12.7 |
| `scripts/fetch_upstream.sh` | Fetches the organizers' checkouts, which are not tracked |
| `sub/` | **Submission source:** `Dockerfile` (full image), `Dockerfile.min` (scratch image, §9.7.4), `t3native/`, `native/` (engine, launcher, RNG), `abides_fork/`, `patches/`, `perf/` (`abides_fork/simulate.py` passes a temporary `log_dir` since the Final build, §9.10.3), `submission.json`, `build_submission.py`, `README.md`. `simulate` / `simulate-batch` shell shims are kept but not installed by the Dockerfile |
| `native/engine/engine.cpp` | Native engine (single source of truth; synced into `sub/` by `lab/sync_sub.sh`). When §9.9 was written it was sub18 plus the sensitivity-flag fix of §9.9.10. The Final's engine is the snapshot `lab/bench/engine_final.cpp` (§9.10.3). `engine_sub3.cpp` is the sub3 engine, kept for comparison |
| `native/engine/launcher.cpp` | No-Python `simulate` / `simulate-batch` |
| `native/engine/pq_fast.hpp`, `sha256.hpp` | Built-in Parquet writer and SHA-256 (sub5 onward; §7.9) |
| `native/engine/pgo_train/` | Training scenarios of the profile-guided build (§9.8.4) |
| `native/engine/check_fast.py`, `check_batch_tables.py`, `check_skip.py` | Table-equality checks (single, batch) and the no-ledger check |
| `native/engine/bench_units.py`, `bench_unit_dirs.py`, `res_units.py`, `ab_knobs.py` | Best-of-N timers (scenario files; unit folders), resource survey, switch A/B (§9.7.3, §9.7.7, §9.8.3) |
| `native/engine/bench.cpp`, `driver.cpp`, `dump_cfg.py` | Benchmark with CPU counters; older timing driver; config dumper |
| `native/engine/try_all.py`, `check_launcher.py`, `check_batch.py` | Byte-identity checks (Python path, launcher, batch) used through sub4 |
| `native/rng/` | `np_random.hpp`, `test_rng.cpp`, `gen_ref.py`, `run_all.sh` |
| `native/pkg/t3native/` | Python package: `cli.py`, `batch.py`, `native_sim.py`, `writer.py` |
| `native/refdump/` | ABIDES instrumentation, `first_divergence.py`, `DUMP_FORMAT.md`, `COVERAGE.md` |
| `native/fuzz/` | Fuzz generators, case logs (`*.jsonl`), `recheck.py`, `recheck_launcher.py`, `recheck/` (22 stored failing cases), `recheck_stored.py` (replay of the 1,318 stored cases), `decline_reasons.py`, `dump_case.py` |
| `lab/` | Development harnesses. Validation: `validate_image.sh`, `validate_rest.sh`, `build_validate.sh`, `build_variant.sh`, `quick_checks.sh`, `scratch_checks.sh`, `check_skip.sh`, `run_reg.sh`. Timing: `cold_runs.sh`, `measure_builds.sh`, `true_p.py`, `e2e.py`, `ab.py`. Comparison in the dev container: `cmp_bins.sh`, `cmp_tables.py`, `build_pgo_dev.sh`. Last-resort path under the restrictions: `ref_path_check.sh` (§9.10.3). |
| `lab/bench/` | Logs and results: `validate_sub7.log` to `validate_sub19a.log`, `validate_final.log` (the Final image), `checks_finalm.log` (the Final image with the memory settings), `fuzz_final.log` and `fuzz_sub16_complete.log` (fuzz replays of the Final image and of sub16), `refpath_<tag>/` (forced reference path), `pullcheck/` (the pushed Final image pulled back by digest), `scratch_sub*.log`, `check_fast_all*.log`, `official_sub5.log`, `official_sub6.log`, timing files (`all_sub*.json`, `best_*.json`, `gb_sub*.json`, `ot_sub*.json`, `fig_*.json`, `truep_*.json`), `measure_fig.log`, source snapshots of each build (`engine_sub6.cpp` to `engine_sub19b.cpp`, `launcher_sub6.cpp` to `launcher_sub18.cpp`), `engine_final.cpp` (the Final's engine), `failcases/` (the 29 negative-latency fuzz cases), `Dockerfile.nohelper`, `Dockerfile.trail`, `Dockerfile.memoff` |
| `lab/sub5_src/` | Copy of the native sources and Dockerfile exactly as built into sub5 |
| `lab/agent240/` | Scratch scripts of the first review (§9.8.7; not tracked) |
| `lab/agent220/` | Records of the three agents: `model/` (score model), `osint/` (issue threads and public repositories), `engine/review.md` (§9.9.6) |
| `lab/agent_report/facts_sub16_19.md` | Fact sheet from which §9.9 and the updates of §10 to §17 of that period were written |
| `lab/agent_report/facts_final.md` | Fact sheet from which §9.10 and the updates of §0, §1 and §10 to §17 that concern the Final were written |
| `docker_backup/` | `docker save` archive of the images in use (§9.8.11) |
| `track3-simulation-public-clone/` | Organizer repo at `4cc7882` (scenarios, units, locally generated reference traces); not tracked |
| `track3-upstream/` | Organizer repo at `bffb572` (current harness and rules); not tracked |
| `toolkit-v2.5.1/` | Organizer toolkit at tag `v2.5.1`; not tracked |
| No longer present | `lab/reg_sub4/` (sub4 regression output), `lab/e2e/`, `lab/ab1/`, `lab/batch_*`, `lab/rt/`, `repro/out_sub5` to `out_sub8`, `repro/out_smoke`, `lab/bench/batch5/`, `lab/bench/val_sub7s/`: deleted (§9.8.11). `cand/`, `cand2/` (Phase A candidates), `prof-run/` and the two `workspace-*` directories with the original baseline adapter are also gone from the tree |

---

## 14. Appendix: pinned versions, checksums, glossary

### 14.1 Environment used for all local measurements
- **Host:** Windows 11 Home, 5.99 GB RAM (free RAM during the sub4 work: 54–153 MB).
- **Docker:** Desktop 29.7.2, WSL2 kernel 6.6.87.2, VM with ~2.7–2.8 GiB RAM (2.76 GiB in the period of §9.9; §9.8.5 quotes 2.97 GB from `docker info`); containers see 12 logical CPUs unless limited. Docker's data disk is now on `E:\DockerData` (§9.8.11).
- **Host Python:** 3.12.6.
- **CPU:** AMD Ryzen 5 5500U; SHA instructions present (`sha_ni`); no AVX-512 (`grep -c avx512f /proc/cpuinfo` → 0). Hardware performance counters are available inside privileged containers.
- **Dev container:** `t3dev` (image `t3-native-perf`), with `/native`, `/units`, `/lab` and `/sub` mounted and `perf` installed (§9.9.11).
- **Unit folders** are a Windows-backed mount inside containers and add 10 to 20 ms per run to anything timed from them (§9.9.3).
- **Scoring host** (not ours): per the organizers a single machine, a Xeon Platinum 8570, that takes only Track 3 runs and is also the Final's machine (§2.2, §9.9.2). Per the organizers' calibration, a KVM virtual machine on that CPU with 20 vCPUs (10 cores × 2 threads) and one NVIDIA B200 (§9.10.2).

### 14.2 Inside the submission image
- This subsection describes the full image. The scratch images uploaded since sub7 hold only the static launcher, a `simulate-batch` symlink, empty directories and a two-line `passwd` and `group` (§9.7.4).
- Python 3.11 on Debian (python:3.11-slim), glibc 2.41.
- numpy 1.26.4, pandas 1.5.3, pyarrow 15.0.2, scipy 1.17.1.
- ABIDES `jpmorganchase/abides-jpmc-public` at commit `f9cbe51342b7dedd9587e4e069040d68a5c6477f`.
- Compiler: g++ (Debian); engine `.so`: `-O2 -std=c++17 -ffp-contract=off -fPIC -shared -pthread`; launcher in sub4: `-O2 -std=c++17 -ffp-contract=off -pthread`, linked with `-l:libparquet.so.1500 -l:libarrow.so.1500 -l:libcrypto.so.3`, rpath to the pyarrow package directory; launcher in sub5/sub6: `-O2 -std=c++17 -ffp-contract=off -pthread -static`, no external libraries (g++ 14); from sub11: `-O3` with a profile-guided build, same floating-point options (§9.8.4).

### 14.3 Organizer sources
- `Agenthon-2026/track3-simulation-public` @ `4cc7882eed85153e9c06667738c87882b2deec90` (scenarios, units; used for all validation through sub3)
- `Agenthon-2026/track3-simulation-public` @ `bffb57227f796f9fa769a23d01fc364bee14a119` (harness and rules used from sub4 on; two later commits, `160f86e` and `1d7e994`, change documentation only: §9.9.16)
- `Agenthon-2026/Agenthon2026-public` common library @ tag `v2.3.1` (through sub3) and `v2.5.1` (sub4; commit `50fb2dc`)

### 14.4 Source checksums (SHA-256)

sub4:

| File | SHA-256 |
|---|---|
| `sub/native/engine/engine.cpp` | `58a14260f418df9720165ee6ebedc5655ecc3e12e0cd5588b0b94853baf3552e` |
| `sub/native/engine/launcher.cpp` | `18d07cc7a951736b00e9b876d4b1c9ffb780d65e96697e274a51bb3ec37ca21b` |
| `sub/native/rng/np_random.hpp` | `db7f57703cef0f0a06979b55283c20812a5ad497dde3a1c56c7db9a490332d91` |
| `sub/t3native/__init__.py` | `2ad09afa24c3a00e45a7ec1fc75fbb10e1ecf5d003000fab9314ce52d3ecdb44` |
| `sub/t3native/batch.py` | `888238d1e8f4c727f42e97b9d10582b0251c07dd28288e22c5d78a3caa5fc152` |
| `sub/t3native/cli.py` | `78b5059a21b236b8c5723700d16c4411eb02549b32210de32fcb94efbc92660c` |
| `sub/t3native/native_sim.py` | `caabe71b3aa526c99000daab2d419bacb88e428817734513bbab6af1e9521d87` |
| `sub/t3native/writer.py` | `2078c99a0ab0313f0e3246f20c29f9097b36d5bc35f8048a0435dc3668656e19` |
| `sub/Dockerfile` | `30d085f67f63d6db77d45441f6767164d7c86950f7cb49fcd03491a4b3494218` |

sub5 (as built; copies in `lab/sub5_src/`) and sub6 (as built). Checksums of later builds were not recorded here; their engine and launcher sources are kept as snapshot files in `lab/bench/` (`engine_sub<N>.cpp`, `launcher_sub<N>.cpp`, §13):

| File | sub5 | sub6 |
|---|---|---|
| `native/engine/engine.cpp` | `2455bbd710227ee84d5ff945f7e46e0f0d6ba07626581528ec3b417d204c0f72` (1,519 lines) | `b048a687783eefa9097eb97ba6cef96b91e01acb3e91a73847f2e8a9cca41140` (1,549 lines) |
| `native/engine/launcher.cpp` | `9e5e72ef72f9183809e30e115abd2fcc049c9aa14e731db443dee871b10b1e5f` (789 lines) | `4f4e8f42b958e31688bccd7faea94d0a7c74fe65e89bae5ff3863c859c7435a9` (789 lines) |
| `native/engine/pq_fast.hpp` | `9cf39bb3bf46c387dba9cd6e70feee1f462307029b7058943eecb9d5a88baf3e` (292 lines) | `e41a60ca71ac11c67fc860eefb7189942812e3946fe691eb1e74be85f4a98a0a` (369 lines) |
| `native/engine/sha256.hpp` | `3b0d30229be235b598b1d2ea5fd0a742eee9049455949e14a90e328bcd1f4023` (121 lines) | same |
| `Dockerfile` | `764b0e1dc19a70294a2ab91990e1abbdc62762eff79de4cf64155cfd6d427575` | same |

The RNG header and the five Python files are unchanged from sub3 in every image. sub3 differed in: `engine.cpp` `61819bf375b639384c1489077f956f6f9d3bdb639b77d61780553344b5e168e2`, `Dockerfile` `ffd215f21553478770e2f476c7f5d4db16e9cb44d1f0f7bf0d467073126a9dcf`, no launcher.

Check with: `sha256sum sub/native/engine/*.cpp sub/native/rng/np_random.hpp sub/t3native/*.py sub/Dockerfile`

### 14.5 Image digests

All on Docker Hub under `slashalpha/agenthon-track3`. Scores are in §1.1, §9.8.1, §9.9.1 and §9.10.

| Image | Digest |
|---|---|
| baseline `:dev` | `sha256:c4f8a635794ebeb4026e8bc2977b3fdd9feef830def78025ce4f744461c77996` |
| sub1 `:native-v1` | `sha256:8d4db7f43ea848770c7d99a6b0b14089b3b5ee72d88a95fdf8208414e030fe7b` |
| sub2 `:native-v2` | `sha256:81e6fa40372a3a4e076a3a5e0adc0341b8c0263c288e8d3a5fe3dae32acc2d7a` |
| sub3 `:native-v3` (never uploaded) | `sha256:67e3086d427a68a9ba1c390811dafbc93f11b6ed42d228d5312c1a91c0fc60c7` |
| sub4 `:native-v4` | `sha256:697ae5de6d95b1fce2bd467375060a10f4f343a04a00d00a989b38e5869d85c7` |
| sub5 `:native-v5` | `sha256:eb90d781431939ce0357290851f4b08f178dfd654d5de2e53feaefa4f117ab06` |
| sub6 (local only, never pushed) | image ID `67e474a28959…` |
| sub7 scratch `:native-v7s` | `sha256:2b97366d097cf6a68e6aefb3a148940ae1517de55c6945d7dc43f64e6b3e4cf0` |
| sub9 scratch `:native-v9s` | `sha256:9e8206c3567c1f54e43f74a28a302a06971d8de99ed704b7e6bdb1ace61d3a57` |
| sub10 scratch `:native-v10s` | `sha256:3b27783ef58421aba303d1897564e7b59df06f86d89e70e982d2c5b34254a441` |
| sub11 scratch, memory switches off `:native-v11m` | `sha256:47c37844beb88e6a36043a9ef25bf7ad248ec41ae299fc8f8472136d7cfe8128` |
| sub13 scratch, memory switches off `:native-v13m` | `sha256:1ca74d1cd2c8dbc63cd2db495b9d1fc5885e3206f8aa43c87bac5db3784f86f0` |
| sub16 scratch, memory switches off `:native-v16m` | `sha256:96856191063e0cefe726d5c9a0d8bbea049ef52182e6a3308fe174aadfcdbd83` |
| sub17 scratch, writer threads off `:native-v17n` | `sha256:6d1a0d8fdfce8001fe4d7722009bfa9e7b54f15b458ff68bdb86a1290e03c192` |
| sub17 scratch, writer threads on `:native-v17t` | `sha256:998c2f45c2eac81bb50c14679694a1ca090e43534d0c6bbce9f8b208bb81ecd8` |
| sub16 binary, helper thread off `:native-v16-helper-off` | `sha256:31cb73d3789e38dba5f47f6c6e91068ecd216f45656fa1dd4fc405bbf8788f5c` |
| sub18 binary, helper thread off `:native-v18-helper-off` | `sha256:b437b60816126789b60d9faa5c0c0a16b0fdd7d7e851d5b4711140ff5feaf6ce` |
| sub18, helper sleeping `:native-v18-helper-sleeping` (pushed, never uploaded) | `sha256:2f9c4d39a04390cb7700dfc8730746efabe3cf9bbbe64c26846235fcfae38ea7` |
| sub19a (scratch) `:native-v19a` | `sha256:abca67f17b3558eedca6e44ec2e437ec5b9ff7ccb3121c4ad2c4879f53dcf434` |
| sub16 binary, writer threads on `:native-v16t` (the last Development upload) | `sha256:b0478b41338580ff4cd4285551ce0b3dcaff1a96e974bf391d739d9403f32602` |
| **Final** `:native-final` (full image; Final upload 993712) | `sha256:44f825eb7b8a5e0276baea84aafe3c344bdbb927500dac2a6ac0782e05e93487` |

sub8, sub12, sub14, sub15 and sub19b exist as local images only at the time of writing.

### 14.6 Glossary

| Term | Meaning |
|---|---|
| events/s | Trace rows ÷ time. Which time depends on the rule: the simulation loop (self-reported, old rule), the whole container (new Development rule), or container start-to-exit (Final) |
| Byte-identical | Same SHA-256 for both output Parquet files as the baseline image |
| Table-identical | Both output files read back (pyarrow and pandas) as the same tables as the baseline's: names, order, types, nulls, values, `pandas` metadata. The criterion for sub5/sub6 |
| Fixed overhead | Container time that does not depend on our program: creating, starting, stopping and removing the container |
| Output chain | assemble columns → encode pages → hash and write, for one of the two files |
| Delta encoding | Parquet's DELTA_BINARY_PACKED: stores differences between consecutive integers in as few bits as each block needs |
| Launcher | The C++ program installed as `simulate` and `simulate-batch` from sub4 on |
| Python path | `python -m t3native.cli` / `t3native.batch`: the native engine driven from Python (the sub3 entry point) |
| Fallback / reference path | The exact Python ABIDES path, used for anything the native engine does not certify |
| Requeue | A message re-pushed because its recipient agent is still busy |
| Blocked queue | Per-agent queue holding events whose recipient is busy; replaces repeated requeues with one move (§7.7). A binary heap on the event key through sub17; from sub18 a vector kept in ascending key order with a read position (§9.9.7) |
| Pre-fault | Making the OS back a memory range with physical pages before use |
| Cycles / instructions per event | User-mode CPU cycles / instructions spent inside `t3_simulate`, divided by trace rows |
| ulp | Unit in the last place of a floating-point number |
| Decision model | An external model that answers typed questions (probability, graded value, choice), used for decision routing (§4.2) |
| sub1 … sub19b | Our successive builds. Uploaded: sub1, sub2, sub4, sub5, sub7, sub9, sub10, sub11, sub13, sub16, sub17 (two variants), the sub16 and sub18 binaries with the helper thread off, sub19a, and sub16t (the sub16 binary with writer threads on). The Final upload was `native-final` (§9.10). The others were not uploaded |
| Full image / scratch image | The full image is `python:3.11-slim` with the launcher and both Python fallback layers. The scratch image holds only the static launcher (about 2.2 MB, one layer); a scenario the launcher declines exits with status 127 there (§9.7.4) |
| Unit | One scored item of the roster: a folder with `scenario.json` (or a `scenarios/` directory for a batch unit) and `card.toml`, mounted at `/input`. Development scores 71 public units: 65 single and 6 batch |
| Card | A unit's `card.toml`; its `requires_message_ledger` flag decides whether the ledger file is needed (§9.8.3) |
| Ledger skip | Not recording or writing `message_trace.parquet` on single units whose card says it is not required (sub10 onward) |
| Memory switches | `T3_HUGE` (huge-page requests) and `T3_PREFAULT` (up-front population of output buffers); both off in every upload since sub11 (§9.8.4) |
| Helper thread (latency helper) | A second thread that computes the latency draws ahead of the event loop from a copy of the generator (§7.7 C); `T3_LAT_THREAD=0` switches it off |
| Ring | The single-producer, single-consumer buffer through which the helper thread hands latency values to the event loop: 2^13 values through sub17 and in sub19a/sub19b, 2^15 in sub18 |
| Spinning / sleeping helper | What the helper does while its ring is full: keeps polling (sub16, sub19a/sub19b) or sleeps on a futex until the event loop has used half the ring (sub18) |
| Wakeup ring | From sub18: one of up to four per-interval queues that hold wakeups already in key order; any other wakeup goes to the wakeup heap (§9.9.7) |
| Writer threads | One thread per output file that encodes, hashes and writes finished rows while the simulation runs (sub15; `T3_TRAIL=1`). With `T3_TRAIL=0` the files are built after the run (§9.8.10, §9.9.5) |
| Trace bucket | All trace rows of one timestamp, put in final order when the first row of a later time arrives (sub14 onward, §9.8.9) |
| True process time | Process time of a unit with its inputs copied to memory first (`lab/true_p.py`), as opposed to figures timed from the unit folders (§9.9.3) |
| Fuzz replay | Re-running the 1,318 stored fuzz cases that have a recorded reference, through the Python path and through the launcher (`native/fuzz/recheck_stored.py`, §9.7.2) |
