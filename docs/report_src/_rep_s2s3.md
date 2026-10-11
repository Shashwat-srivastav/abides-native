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

