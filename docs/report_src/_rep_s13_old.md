## 13. File map

| Path | Contents |
|---|---|
| `REPORT.md` | This document |
| `repro/` | Portable reproduction kit (§12) |
| `sub/` | **Submission source:** `Dockerfile`, `simulate`, `simulate-batch`, `t3native/`, `native/`, `abides_fork/`, `patches/`, `perf/`, `submission.json`, `build_submission.py` |
| `native/engine/engine.cpp` | Native engine (single source of truth; synced into `sub/` by `lab/sync_sub.sh`) |
| `native/rng/` | `np_random.hpp`, `test_rng.cpp`, `gen_ref.py`, `run_all.sh` |
| `native/pkg/t3native/` | Python package: `cli.py`, `batch.py`, `native_sim.py`, `writer.py` |
| `native/refdump/` | ABIDES instrumentation, `first_divergence.py`, `DUMP_FORMAT.md`, `COVERAGE.md` |
| `native/fuzz/` | Fuzz generators, case logs (`*.jsonl`), `recheck.py` |
| `lab/` | Development harnesses (A/B, e2e, regression wrappers, comparison scripts) |
| `cand/`, `cand2/` | Phase A Python-only candidates |
| `workspace-*/agenthon_t3_baseline/` | Original baseline adapter (untouched) |
| `track3-simulation-public-clone/` | Organizer public repo (scenarios, reference traces, harness, units) |

---

## 14. Appendix: pinned versions, checksums, glossary

### 14.1 Environment used for all measurements
- **Host:** Windows 11 Home, 5.8 GB RAM.
- **Docker:** Desktop 29.7.2, WSL2 kernel 6.6.87.2, VM with ~2.7 GiB RAM and 4 CPUs.
- **Host Python:** 3.12.6.
- **CPU:** no AVX-512 (numpy reports `AVX512F` not found).

### 14.2 Inside the submission image
- Python 3.11.16 on Debian 13.7, glibc 2.41.
- numpy 1.26.4, pandas 1.5.3, pyarrow 15.0.2, scipy 1.17.1.
- ABIDES `jpmorganchase/abides-jpmc-public` at commit `f9cbe51342b7dedd9587e4e069040d68a5c6477f`.
- Engine compiler: g++ (Debian), flags `-O2 -std=c++17 -ffp-contract=off -fPIC -shared`.

### 14.3 Organizer sources
- `Agenthon-2026/track3-simulation-public` @ `4cc7882eed85153e9c06667738c87882b2deec90`
- `Agenthon-2026/Agenthon2026-public` common library @ tag `v2.3.1`

### 14.4 sub3 source checksums (SHA-256)

| File | SHA-256 |
|---|---|
| `sub/native/engine/engine.cpp` | `61819bf375b639384c1489077f956f6f9d3bdb639b77d61780553344b5e168e2` |
| `sub/native/rng/np_random.hpp` | `db7f57703cef0f0a06979b55283c20812a5ad497dde3a1c56c7db9a490332d91` |
| `sub/t3native/__init__.py` | `2ad09afa24c3a00e45a7ec1fc75fbb10e1ecf5d003000fab9314ce52d3ecdb44` |
| `sub/t3native/batch.py` | `888238d1e8f4c727f42e97b9d10582b0251c07dd28288e22c5d78a3caa5fc152` |
| `sub/t3native/cli.py` | `78b5059a21b236b8c5723700d16c4411eb02549b32210de32fcb94efbc92660c` |
| `sub/t3native/native_sim.py` | `caabe71b3aa526c99000daab2d419bacb88e428817734513bbab6af1e9521d87` |
| `sub/t3native/writer.py` | `2078c99a0ab0313f0e3246f20c29f9097b36d5bc35f8048a0435dc3668656e19` |
| `sub/Dockerfile` | `ffd215f21553478770e2f476c7f5d4db16e9cb44d1f0f7bf0d467073126a9dcf` |
| `sub/simulate` | `3e2cf4c80653580305be0ab19c12a082a872b5b13a9fc9806dc9807255c4b24d` |
| `sub/simulate-batch` | `7edf4906241cb313bd4f24a23a9318a70856129ce4368d153f48d57cfc446305` |

Check them with: `sha256sum sub/native/engine/engine.cpp sub/native/rng/np_random.hpp sub/t3native/*.py sub/Dockerfile sub/simulate sub/simulate-batch`

### 14.5 Image digests

| Image | Digest |
|---|---|
| baseline `slashalpha/agenthon-track3:dev` | `sha256:c4f8a635794ebeb4026e8bc2977b3fdd9feef830def78025ce4f744461c77996` |
| sub1 `:native-v1` | `sha256:8d4db7f43ea848770c7d99a6b0b14089b3b5ee72d88a95fdf8208414e030fe7b` |
| sub2 `:native-v2` | `sha256:81e6fa40372a3a4e076a3a5e0adc0341b8c0263c288e8d3a5fe3dae32acc2d7a` |
| sub3 `:native-v3` | `sha256:67e3086d427a68a9ba1c390811dafbc93f11b6ed42d228d5312c1a91c0fc60c7` |

### 14.6 Glossary

| Term | Meaning |
|---|---|
| events/s | Trace rows ÷ simulation wall time (self-reported) or ÷ `docker run` time (host-measured) |
| Byte-identical | Same SHA-256 for both output parquet files as the baseline image |
| Fallback | The exact Python ABIDES path, used for anything the native engine does not certify |
| Requeue | A message re-pushed because its recipient agent is still busy |
| Pre-fault | Making the OS back a memory range with physical pages before use, so the timed loop takes no page-fault traps |
| Decision model | An external model that answers typed questions (probability, graded value, choice), used for decision routing (§4.2) |
| sub1 / sub2 / sub3 | Our successive native submission images |
