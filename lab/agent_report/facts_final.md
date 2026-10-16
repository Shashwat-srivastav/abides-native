# Fact sheet: from the end of Development to the Final result

Authoritative for everything after sub19a. Every number here is from a log, an organizer statement or the
CodaBench pages the team read. Do not add numbers that are not here or in the cited files.

## 1. The last Development upload

- sub16t = the sub16 scratch binary with `T3_TRAIL=1` (writer threads during the run), image
  `slashalpha/agenthon-track3:native-v16t`, `sha256:b0478b41338580ff4cd4285551ce0b3dcaff1a96e974bf391d739d9403f32602`.
  Checks before upload: binary identical to sub16, batch 6/6, official regression 65/65, no-ledger units 6/6,
  output bytes identical across three runs on the 65 single units (`lab/bench/scratch_sub16t.log`).
- It was the 23rd and last Development upload. **It scored below sub16** (the team reported it as "not good"); its
  exact score was not recorded in this record. sub16's 203,394.4709 stays the best Development score.
- Board position at the last reading the team recorded: rank 10 of 50.

## 2. What the organizers published about the Final (issue trackers and README of Agenthon-2026)

- CodaBench phase "Final & Verification": current from 13 October 12:00 UTC to 26 October 11:59:59 UTC,
  1 upload per person in total (CodaBench competition API, phase 29647). Development ended 13 October 11:59 UTC
  (the earlier 20:00 UTC cutoff was cancelled).
- One Final upload per team. A Final upload that ends Failed does not use it; a held one does. Code may change after
  Development; ties go to the earlier upload. Outputs, logs, per-unit outcomes and the Final board are hidden;
  results are published in early November. The image must stay pullable until then.
- Timing: each unit runs five times back to back with the same seed; the unit's rate is verified events / the median of
  the four runs after the warm-up; each run is timed from `StartedAt` to `FinishedAt` (creating and removing the
  container are not counted). The score is the arithmetic mean of the unit rates over the whole roster (public units
  plus an unpublished number of sealed scenarios), so units with the most events weigh most.
- Correctness: every scenario, public and sealed, must pass ("a single failure anywhere is inadmissible"); a run that
  crashes, times out (300 s) or runs out of memory scores the unit 0; all runs of a unit must write byte-identical
  trace and ledger files.
- Runtime: read-only root, 64 MiB `noexec` `/tmp`, uid 65534, no network, `--cpus=4` quota (not pinned), 16 GiB, GPU
  attached through CDI (it cannot be opted out of).
- Calibration on the timing machine (organizers, issue #24 and #34): a KVM virtual machine on an Intel Xeon Platinum
  8570, 20 vCPUs as 10 cores x 2 threads, one NVIDIA B200. A static binary that only copies outputs takes a median
  0.165-0.173 s per Final window (runtime and GPU set-up); the same work from a Python image took 0.342-0.343 s.
  Create-to-remove, as the Development board counted it, was 0.630-0.643 s for the static binary: about 0.46 s per
  unit outside the Final window.
- Another team (issue #37) reported identical images scoring up to 14% apart on the Development board (203.0K and
  219.4K; 230.9K and 202K). The organizers could not tell drift from noise in their own two timings 26 minutes apart.
  Consequence for this record: single Development uploads that differ by a few percent (helper +9.5%, sub19a -2.1%,
  writer threads +1.6%, sub16t below sub16) are weaker evidence than the record treated them as.
- The organizers' own baseline had a bug: ABIDES writes `summary_log.bz2` under `./log/` at the end of every run,
  which fails on the read-only root (fixed upstream in commit `fe32378` with `log_dir="/tmp/abides"`).

## 3. Two defects found in our best image while preparing the Final

1. **The last-resort ABIDES path crashed on the read-only root.** `sub/abides_fork/simulate.py` called
   `abides.run(config)` without `log_dir`. With the reference path forced (`T3_NO_LAUNCHER=1 T3_FORCE_REFERENCE=1`)
   under the Final's restrictions, the sub16 full image exited with `OSError: [Errno 30] Read-only file system:
   './log'` and wrote no files (`lab/bench/refpath_sub16/` when present; script `lab/ref_path_check.sh`). The batch
   path was not affected (it changes into a temporary directory). The scored scratch images have no Python layer, so
   this never affected a score; it would have affected any declined input in a full image.
   Fix: `abides.run(config, log_dir=tempfile.mkdtemp(prefix="abides-log-"))`.
2. **The hand-over decision could depend on thread timing.** The helper thread computes latency draws ahead of the
   event loop and raised the "rounding-sensitive" flag for draws the run might never use. Launcher-only passes over the
   stored fuzz cases declined 23; full replays handed 22 to Python. Across five repeats of a sealed unit this could have
   sent one repeat to the Python path and not another: different file bytes, a refused unit.
   Fix (`lab/bench/engine_final.cpp`, made by `amb_patch16.py` from `lab/bench/engine_sub16.cpp`): `latency_from`
   reports sensitivity through a flag argument; the event loop's own inline draws raise the global flag as before; the
   helper records only the index of the first sensitive draw it computed, and after the run that counts only if the
   loop used the ring and the index is below the number of values it consumed.

## 4. The Final build

- **What:** sub16's engine, launcher and Parquet writer (launcher and writer are byte-identical to the sub16 snapshots)
  with the two fixes, in the **full image with the exact Python fallback**, environment `T3_HUGE=0 T3_PREFAULT=0
  T3_TRAIL=0` (the memory settings and writer setting of the 203,394 run).
- **Image:** `slashalpha/agenthon-track3:native-final`,
  `sha256:44f825eb7b8a5e0276baea84aafe3c344bdbb927500dac2a6ac0782e05e93487`, 773 MB, `linux/amd64`, interface label
  2.0, no `VOLUME`, no entrypoint (the command starts the static launcher directly).
- **Why the full image, not the 2 MB scratch image that scored 203,394:** with all-or-nothing correctness on sealed
  scenarios, a declined input in a scratch image exits with status 127 (a crash). In the timed window both images start
  the same static launcher; Python loads only for a declined input. Its host timing was never measured (no Development
  uploads were left). A decision round (the typed decision model used throughout, round 8) given both sides chose the
  full image with probability 0.97 (scratch as scored 0.01, new scratch of the fixed binary 0.02); its probability that
  at least one sealed scenario would be handed over was 0.56 and that the full image would score more than 1% (3%) below
  scratch 0.36 (0.23). These are judgments, not measurements.
- **Validation** (`lab/bench/validate_final.log`, `lab/bench/checks_finalm.log`, `lab/bench/fuzz_final.log`):
  output byte-identical to the sub16 binary on all 65 single units with the helper on and with it off; tables 65/65;
  repeat-run bytes 65/65 across three runs; batch 6/6 under the runtime restrictions; forced fallback (two modes) under
  restrictions; official regression 65/65 (on the image and again on the memory-settings image); no-ledger units 6/6;
  fuzz replay 1,318 of 1,318 (1,296 through the launcher, 22 to the Python path); forced reference path under the
  Final's restrictions on one single unit (604 and 664 rows, equal to the reference tables) and one batch unit;
  pulled back by digest and run on one unit under the restrictions: tables equal to the reference (71,932 and 63,287
  rows).
- **Also recorded:** sub16's fuzz replay did complete in a separate run before its upload:
  `lab/bench/fuzz_sub16_complete.log` (1,318 of 1,318, 1,296/22).

## 5. The Final result

- Upload **993712**, status Finished, **primary score 1,755,232.6496** (events per second, Final metric).
- The run summary page lists the kinds of problems a run had; it listed none (no reason codes). It shows no unit count
  and no per-unit outcomes on a sealed phase. Reading: no unit failed; not a unit-by-unit proof.
- The Final board and other teams' Final scores are hidden until early November, so no rank is known.
- The Final score is not comparable with Development scores (different timed window: about 0.46 s per unit less).
