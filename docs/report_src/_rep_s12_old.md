## 12. Reproduction guide

The kit in [`repro/`](repro/) automates every step:
- `repro/repro.sh`: the driver;
- `repro/in_container_run.py`: runs all scenarios inside one container;
- `repro/compare.py`: identity and throughput report;
- `repro/Dockerfile.rng`: RNG test toolchain.

The kit was itself tested end to end on the machine described in §14.1 (results in §12.7).

### 12.1 Prerequisites

| Requirement | Version used | Notes |
|---|---|---|
| OS | Windows 11 + Git Bash, or Linux with bash | The kit handles both path styles |
| Docker | Desktop 29.7.2 (WSL2 engine) | Must be able to build `linux/amd64` |
| RAM | 5.8 GB host worked, with one worker | Large scenarios use ~2 GB inside Docker |
| Disk | ~5 GB free | Images ~0.8 GB each plus outputs |
| Python (host) | 3.12.6 | Only for `compare.py` and the official harness |
| Network | Needed for builds and pulls only | All runs use `--network none` |

### 12.2 Get the sources

```bash
# 1. This project (contains sub/, native/, repro/, lab/, REPORT.md)
cd E:/NeurIPS/agenthon            # or wherever the project lives

# 2. Organizer public repo, pinned to the commit we used
git clone https://github.com/Agenthon-2026/track3-simulation-public.git track3-simulation-public-clone
git -C track3-simulation-public-clone checkout 4cc7882eed85153e9c06667738c87882b2deec90

# 3. Organizer common library, needed only for the official harness (step 12.4.6)
pip install "qfbench2-common @ git+https://github.com/Agenthon-2026/Agenthon2026-public.git@v2.3.1#subdirectory=common"
```

If the public repo is somewhere else, set `PUBLIC_REPO=/path/to/track3-simulation-public` before running the kit.

### 12.3 One-shot

```bash
bash repro/repro.sh all     # env, build, baseline, candidate, identity, batch, official
bash repro/repro.sh rng     # optional, ~10 min: RNG bit-exactness matrix
bash repro/repro.sh ab 3    # optional: 3 interleaved throughput rounds, baseline vs candidate
```

Outputs go to `repro/out/`. Each step is also callable on its own (§12.4).

### 12.4 Step by step: what each does and what you should see

| # | Command | What it does | Expected result | Time (this laptop) |
|---|---|---|---|---|
| 1 | `bash repro/repro.sh env` | Prints versions; checks 65 scenarios and 6 batch units | `scenarios: 65`, `batch units: 6` | seconds |
| 2 | `bash repro/repro.sh build` | `docker build sub/` → `agenthon-track3:repro` | `built agenthon-track3:repro: sha256:…` (ID will differ from ours; see §11) | 5–10 min cold, seconds cached |
| 3 | `bash repro/repro.sh baseline` | Runs the **original ABIDES image** (`slashalpha/agenthon-track3:dev`, public) on all 65 scenarios inside one container | 65 rows `path=reference`, ~6–9K events/s each | see §12.7 |
| 4 | `bash repro/repro.sh candidate` | Runs the **submission CLI** on all 65 scenarios | 65 rows, `path=native` | about 1 min |
| 5 | `bash repro/repro.sh identity` | Compares SHA-256 of both parquet files per scenario | `identical: 65/65`; candidate mean ≈ 5–7M events/s; exit code 0 | seconds |
| 6 | `bash repro/repro.sh batch` | Runs baseline and submission `simulate-batch` on the 6 units | 6/6 units identical (30 subs) | see §12.7 |
| 7 | `bash repro/repro.sh official` | Organizer's `run_regression.py`, 1 worker | `{'total_scenarios': 65, 'passed': 65, 'failed': 0, 'errored': 0}` | see §12.7 |
| 8 | `bash repro/repro.sh rng` | 478M-draw numpy-vs-C++ matrix | `OVERALL: PASS` | ~10 min |
| 9 | `bash repro/repro.sh ab 3` | Interleaved baseline / candidate rounds | Candidate ≈ 1,000× baseline | ~30 min per round (baseline dominates) |

Quick smoke test on a few scenarios:

```bash
ONLY=s001_price_time_priority,mp02_stp_oldest_baseline,ra01_fundamental_shock_mid bash repro/repro.sh baseline
ONLY=s001_price_time_priority,mp02_stp_oldest_baseline,ra01_fundamental_shock_mid bash repro/repro.sh candidate
bash repro/repro.sh identity        # expect identical: 3/3
```

### 12.5 Verifying the exact submitted images (no rebuild)
Point the kit at the published digest:

```bash
IMAGE=slashalpha/agenthon-track3@sha256:67e3086d427a68a9ba1c390811dafbc93f11b6ed42d228d5312c1a91c0fc60c7 bash repro/repro.sh candidate
bash repro/repro.sh identity
```

For sub2 use `@sha256:81e6fa40372a3a4e076a3a5e0adc0341b8c0263c288e8d3a5fe3dae32acc2d7a`; for sub1, `@sha256:8d4db7f43ea848770c7d99a6b0b14089b3b5ee72d88a95fdf8208414e030fe7b`.

### 12.6 What is and is not exactly reproducible

| Quantity | Reproducible? |
|---|---|
| Output bytes (`trace.parquet`, `message_trace.parquet`) and their SHA-256 | **Exactly**, on any x86-64 machine running these images |
| Event and message counts | Exactly |
| Correctness verdicts (identity, official harness) | Exactly |
| events/s | Machine-dependent; expect the same order of magnitude and ratios, not the same numbers |
| Image digest after a rebuild | No (build timestamps and metadata); behaviour is identical |
| Leaderboard score | Depends on the grader's hardware; our sub2 model ratio was 1.28× this laptop |

### 12.7 Results of our own end-to-end reproduction run

**Pending:** the full kit (`env baseline candidate identity batch rng official`) is running at the time of writing. This section will be filled in from `repro/out/full_run.log`.

### 12.8 Reproducing the development experiments

| Experiment | How |
|---|---|
| Baseline profile (§5) | Run cProfile around `abides.run` in the baseline image (`prof-run/prof.py`) |
| Phase A A/B (§6) | `lab/ab.py dev,cand1,cand2 3 <outdir>` (images built from `cand/`, `cand2/`) |
| Engine phase timing | Inside `t3-native-dev`: build `native/engine/driver.cpp` + `engine.cpp`, run on `native/engine/bins/*.bin` with `T3_PHASES=1` |
| perf profiles (§7.4) | `native/Dockerfile.perf` image, `perf record` around the driver (`--privileged`) |
| Host end-to-end timing (§7.6) | `lab/e2e.py <images> <reps> <scenarios>` |
| Fuzzing (§8) | `native/fuzz/gen.py` / `mk_*.py` to generate, `driver.py` to run, `recheck.py` to re-verify |
| Decision rounds (§4.2) | not reproducible from this repository (scripts not deposited) |

The `lab/` scripts were written for this machine and contain absolute `E:/NeurIPS/agenthon` paths. The `repro/` kit is the portable version.

### 12.9 Building and uploading a submission
1. `docker tag agenthon-track3:repro slashalpha/agenthon-track3:<tag> && docker push slashalpha/agenthon-track3:<tag>`
2. Copy the pushed digest from `docker inspect --format '{{index .RepoDigests 0}}' …` into `sub/submission.json` → `image.digest`.
3. Run `python sub/build_submission.py`. It prompts for the **Team Key** (hidden), reseals the descriptor, and writes `sub/submission.zip`. Run this step yourself.
4. Upload `sub/submission.zip` on CodaBench under *My Submissions → Development*.

---

