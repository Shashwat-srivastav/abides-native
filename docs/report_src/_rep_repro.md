Three attempts were made to run the whole kit end to end. All are recorded, including the failures.

| Attempt | Image under test | Outcome |
|---|---|---|
| 1 | `agenthon-track3:repro` (built from the sub3 sources) | **Failed.** `env` passed; `baseline` ran 19 minutes and stopped with `error waiting for container: unexpected EOF` (Docker VM died during the large scenarios); every later step then failed within seconds because the daemon was gone. No comparison was produced |
| 2 | `agenthon-track3:sub4` | **Failed.** `baseline` finished 1 scenario, then Docker Desktop exited (host free RAM about 150 MB). The `official` step in the same run logged "65 errored" for the same reason — not a result about sub4 |
| 3 | `agenthon-track3:sub4` | **Completed**, through `repro/run_resilient.sh` (resume + Docker restart). Every step ended with exit code 0. Log: `repro/out/full_run_sub4.log` |

Attempt 3, step by step:

| Step | Time | Result |
|---|---|---|
| `env` | 13:37 (4 s) | passed on the first try |
| `baseline` (original ABIDES, 65 scenarios, one process each) | 13:37–16:13 | finished on the **6th try**: tries 1–4 ended with Docker exit code 125 (the daemon went away) and try 5 with exit code 1; each retry resumed from the scenarios already done. Total in-container process time 5,405 s |
| `candidate` (sub4, real `simulate` command) | 16:13–16:15 | 65 scenarios, all through the launcher (`{'launcher': 65}`); total in-container process time 43.9 s |
| `identity` | 16:15 | **65/65 identical** (trace and ledger files re-hashed from disk) |
| `batch` | 16:15–16:16 | **6/6 batch units identical** |
| `rng` | 16:16–16:27 | every seed chain "ALL BIT-IDENTICAL"; `OVERALL: PASS` |
| `official` (upstream harness) | 16:27–16:36 | **65 passed, 0 failed, 0 errored** |

Rates from that run (single run per unit on a memory-starved laptop; they are a consistency check, not a benchmark):

| Quantity | Baseline | sub4 |
|---|---|---|
| Self-reported events/s (event loop only), mean over 65 units | 4,639 | 3,141,144 (median 3,133,775, min 960,384) |
| Events per whole-process second, mean over 65 units (excludes container start/stop) | 2,435 | 155,460 |
| Batch units, events/s over the whole batch, mean over 6 | 6,631 | 173,273 |

The whole-process figure for sub4 (155,460) is close to the score the platform gave sub4 (153,825). That is partly coincidence: the platform's number also contains container start/stop time and comes from a faster host.

Earlier partial runs with the kit:

| Run | Result |
|---|---|
| 3-scenario subset, sub3-source image | 3/3 identical; self-reported candidate ≈ 6.4M events/s vs baseline ≈ 7.9K |
| 2-scenario subset (`eq_deterministic_baseline`, `mp07_heavy_flow_oldest`), sub4 | 2/2 identical, both through the launcher; whole-process time: reference 49.4 s (14.2 s + 35.2 s), launcher 3.1 s (1.66 s + 1.40 s) |

Not done: the re-check of the 22 stored failing cases through the reference, launcher and Python paths (`native/fuzz/recheck_launcher.py`) was never run. It was replaced by the replay of the 1,318 stored cases with a recorded reference (`native/fuzz/recheck_stored.py`, §9.7.2), which is part of every full validation since sub7 (§12.10). The kit itself has not been run end to end against any build later than sub4.
