"""Compare a candidate run against the baseline run (both produced by in_container_run.py or batch.sh).

    python repro/compare.py <baseline_dir> <candidate_dir> [--json result.json]

Single-scenario mode: reads <dir>/summary.json from both.
Batch mode (dirs contain <unit>/batch_events.json): compares every sub-scenario's events.json.

A scenario PASSES only if both trace.parquet and message_trace.parquet SHA-256 are identical to the
baseline. Exit code 0 iff everything passes.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import sys


def _single(base_dir: str, cand_dir: str):
    base = {r["scenario_id"]: r for r in json.load(open(os.path.join(base_dir, "summary.json")))}
    cand = json.load(open(os.path.join(cand_dir, "summary.json")))
    rows = []
    for c in cand:
        b = base.get(c["scenario_id"])
        if c.get("failed") or not b or b.get("failed"):
            rows.append({"unit": c["name"], "identical": False, "n_events": 0, "baseline_eps": None,
                         "candidate_eps": 0.0, "path": "FAILED", "baseline_proc_s": None, "candidate_proc_s": None})
            continue
        same = (b["trace_sha256"], b["message_trace_sha256"]) == (c["trace_sha256"], c["message_trace_sha256"])
        same = same and c.get("reported_hashes_match_files", True) and b["n_events"] == c["n_events"]
        rows.append({
            "unit": c["name"], "identical": same, "n_events": c["n_events"],
            "baseline_eps": b["events_per_sec"], "candidate_eps": c["events_per_sec"],
            "path": c.get("path", "?"),
            "baseline_proc_s": b.get("process_seconds"), "candidate_proc_s": c.get("process_seconds"),
        })
    return rows


def _batch(base_dir: str, cand_dir: str):
    rows = []
    for agg_path in sorted(glob.glob(os.path.join(cand_dir, "*", "batch_events.json"))):
        unit = os.path.basename(os.path.dirname(agg_path))
        agg = json.load(open(agg_path))
        bagg_path = os.path.join(base_dir, unit, "batch_events.json")
        bagg = json.load(open(bagg_path)) if os.path.exists(bagg_path) else None
        ok = bagg is not None
        for sub in agg["per_scenario"]:
            c = json.load(open(os.path.join(cand_dir, unit, sub["sub"], "events.json")))
            bp = os.path.join(base_dir, unit, sub["sub"], "events.json")
            b = json.load(open(bp)) if os.path.exists(bp) else None
            ok &= bool(b) and (b["trace_sha256"], b["message_trace_sha256"]) == (c["trace_sha256"], c["message_trace_sha256"])
        rows.append({
            "unit": unit, "identical": ok, "n_events": agg["total_events"],
            "baseline_eps": bagg["events_per_sec"] if bagg else None, "candidate_eps": agg["events_per_sec"],
            "path": f"{agg['n_scenarios']} subs",
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline_dir")
    ap.add_argument("candidate_dir")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    batch = bool(glob.glob(os.path.join(args.candidate_dir, "*", "batch_events.json")))
    rows = _batch(args.baseline_dir, args.candidate_dir) if batch else _single(args.baseline_dir, args.candidate_dir)

    print(f"{'unit':42s} {'identical':9s} {'n_events':>9s} {'baseline eps':>13s} {'candidate eps':>14s} {'speedup':>8s}  path")
    for r in rows:
        sp = (r["candidate_eps"] / r["baseline_eps"]) if r["baseline_eps"] else float("nan")
        be = f"{r['baseline_eps']:13.0f}" if r["baseline_eps"] else f"{'-':>13s}"
        print(f"{r['unit']:42s} {'YES' if r['identical'] else 'NO':9s} {r['n_events']:9d} {be} {r['candidate_eps']:14.0f} {sp:8.1f}x  {r['path']}")
    n_ok = sum(r["identical"] for r in rows)
    eps = [r["candidate_eps"] for r in rows]
    beps = [r["baseline_eps"] for r in rows if r["baseline_eps"]]
    print(f"\nidentical: {n_ok}/{len(rows)}")
    if eps:
        capped = [min(e, 1e7) for e in eps]
        print(f"candidate events/s: mean {statistics.mean(eps):,.0f}  median {statistics.median(eps):,.0f}  "
              f"min {min(eps):,.0f}  mean-capped-at-1e7 {statistics.mean(capped):,.0f}")
    if beps:
        print(f"baseline  events/s: mean {statistics.mean(beps):,.0f}")
    bp = [r["baseline_proc_s"] for r in rows if r.get("baseline_proc_s")]
    cp = [r["candidate_proc_s"] for r in rows if r.get("candidate_proc_s")]
    if bp and cp:
        ne = [r["n_events"] / r["candidate_proc_s"] for r in rows if r.get("candidate_proc_s")]
        nb = [r["n_events"] / r["baseline_proc_s"] for r in rows if r.get("baseline_proc_s")]
        print(f"whole-process time (in container, excludes container start/stop): baseline total {sum(bp):.1f} s, "
              f"candidate total {sum(cp):.1f} s")
        print(f"events / whole-process second, mean over units: baseline {statistics.mean(nb):,.0f}  candidate {statistics.mean(ne):,.0f}")
        from collections import Counter
        print("candidate code paths:", dict(Counter(r["path"] for r in rows)))
    if args.json:
        json.dump({"rows": rows, "identical": n_ok, "total": len(rows)}, open(args.json, "w"), indent=1)
    return 0 if n_ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
