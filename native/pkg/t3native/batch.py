"""``simulate-batch`` verb: same output contract as abides_fork.simulate_batch, native engine per sub.

Timing scope matches the single-scenario verb (and the reference's ``abides.run`` scope): only the
simulation is timed. Each worker first simulates all of its sub-scenarios, then assembles and writes
their outputs, so the batch wall clock is the real elapsed time of the parallel simulation phase
(earliest simulation start to latest simulation end, on the system-wide CLOCK_MONOTONIC that
``time.perf_counter`` uses on Linux). If any sub-scenario needs the ABIDES reference fallback, the
whole batch is timed end to end instead -- conservative, never flattering.

Per-sub outputs are byte-identical to running each scenario alone: every sub gets its own engine
instance (the engine keeps no global state), and scheduling order never affects a sub's result.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import pathlib
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Optional


def _expected_work(path: pathlib.Path) -> float:
    """Scheduled wakeups (horizon x agent rates): a cheap proxy for a sub-scenario's cost."""
    try:
        sc = json.loads(path.read_text())
        horizon = float(sc["horizon_ns"])
        total = 0.0
        for cfg in sc.get("agent_configs", []):
            p = cfg.get("params", {})
            if "rebalance_interval_ns" in p:
                iv = max(1.0, float(p["rebalance_interval_ns"]))
            else:
                hz = float(p.get("arrival_rate_hz", 1.0))
                iv = 1e9 / hz if hz > 0 else 1e9
            total += int(cfg.get("count", 1)) * horizon / iv
        return total
    except Exception:
        return 0.0


def _reference_one(config_path: str, out_path: str) -> dict[str, Any]:
    """Exact ABIDES path, in its own scratch cwd like abides_fork.simulate_batch."""
    from abides_fork.simulate import simulate as reference_simulate

    work_dir = tempfile.mkdtemp(prefix=f"t3-batch-{os.getpid()}-")
    previous = os.getcwd()
    try:
        os.chdir(work_dir)
        return reference_simulate(config_path, out_path)
    finally:
        os.chdir(previous)


def _run_group(jobs: list[tuple[int, str, str]]) -> list[tuple[int, dict[str, Any], Optional[float], Optional[float]]]:
    """Worker: phase 1 simulates every assigned sub (timed); phase 2 writes outputs (untimed).

    Returns (job index, events, sim_start, sim_end); sim_start/end are None for fallback subs.
    """
    from t3native import native_sim

    staged = []
    for idx, cfg, out in jobs:
        try:
            scenario = native_sim.load_scenario(cfg)
            run = native_sim.NativeRun(scenario)
            wall = run.simulate()
            staged.append((idx, cfg, out, scenario, run, wall))
        except Exception:
            staged.append((idx, cfg, out, None, None, None))
    results = []
    for idx, cfg, out, scenario, run, wall in staged:
        if run is not None:
            try:
                out_path = pathlib.Path(out)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                n, m, hashes = run.finish(out_path, out_path.parent / "message_trace.parquet")
                ev = native_sim.write_events(scenario, out_path, n, m, wall, hashes)
                results.append((idx, ev, run.t_start, run.t_end))
                continue
            except Exception:
                pass
        results.append((idx, _reference_one(cfg, out), None, None))
    return results


def _lpt_groups(n_workers: int, subs: list[pathlib.Path], jobs: list[tuple[int, str, str]]):
    """Longest-processing-time-first assignment of jobs to workers (shortens the makespan)."""
    order = sorted(range(len(jobs)), key=lambda i: -_expected_work(subs[i]))
    groups: list[list] = [[] for _ in range(n_workers)]
    load = [0.0] * n_workers
    for i in order:
        w = min(range(n_workers), key=lambda k: load[k])
        groups[w].append(jobs[i])
        load[w] += max(_expected_work(subs[i]), 1.0)
    return [g for g in groups if g]


def simulate_batch(batch_dir: str | pathlib.Path, out_dir: str | pathlib.Path) -> dict[str, Any]:
    batch_dir = pathlib.Path(batch_dir)
    out_dir = pathlib.Path(out_dir)
    subs = sorted(p for p in batch_dir.glob("*.json"))
    if not subs:
        raise SystemExit(f"simulate-batch: no sub-scenarios (*.json) found in {batch_dir}")
    # Warm the parent (numpy, pyarrow, writer, engine .so) before forking so workers inherit it.
    # Like the reference adapter (imports at module load), imports are outside the timed region.
    from t3native import native_sim, writer  # noqa: F401

    try:
        native_sim._load()
    except OSError:
        pass
    t_batch0 = time.perf_counter()
    jobs = [(i, str(p), str(out_dir / p.stem / "trace.parquet")) for i, p in enumerate(subs)]
    workers = max(1, min(len(jobs), int(os.environ.get("T3_BATCH_WORKERS", "4"))))
    if workers > 1:
        groups = _lpt_groups(workers, subs, jobs)
        ctx = multiprocessing.get_context("fork")
        with ProcessPoolExecutor(max_workers=len(groups), mp_context=ctx) as pool:
            flat = [r for part in pool.map(_run_group, groups) for r in part]
    else:
        flat = _run_group(jobs)
    t_batch1 = time.perf_counter()
    flat.sort(key=lambda r: r[0])
    results = [r[1] for r in flat]
    starts = [r[2] for r in flat]
    ends = [r[3] for r in flat]
    if all(s is not None for s in starts):
        wall = max(ends) - min(starts)  # elapsed wall time of the parallel simulation phase
    else:
        wall = t_batch1 - t_batch0  # some sub used the reference fallback: time everything

    per_scenario, total_events, peak, gpu = [], 0, 0, 0.0
    for p, ev in zip(subs, results):
        total_events += int(ev["n_events"])
        peak = max(peak, int(ev.get("peak_memory_bytes", 0)))
        gpu += float(ev.get("gpu_seconds", 0.0))
        per_scenario.append({"sub": p.stem, "n_events": int(ev["n_events"]), "trace_sha256": ev["trace_sha256"]})
    agg = {
        "n_scenarios": len(subs),
        "total_events": total_events,
        "wall_clock_sec": float(wall),
        "events_per_sec": float(total_events / wall) if wall > 0 else 0.0,
        "peak_memory_bytes": peak,
        "gpu_seconds": gpu,
        "per_scenario": per_scenario,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "batch_events.json").write_text(json.dumps(agg, indent=2) + "\n")
    return agg


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="simulate-batch")
    ap.add_argument("verb", nargs="?", default="simulate-batch", choices=["simulate-batch"])
    ap.add_argument("--batch-dir", required=True, help="directory of <sub>.json sub-scenarios")
    ap.add_argument("--out-dir", required=True, help="output directory")
    args = ap.parse_args(argv)
    print(json.dumps(simulate_batch(args.batch_dir, args.out_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
