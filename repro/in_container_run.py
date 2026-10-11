"""Run every scenario in /scenarios inside ONE container and record the results.

Usage (inside an image that has /opt/abides_fork and, for --mode submission, the `simulate` verb):
    python /repro/in_container_run.py --mode reference|submission --out /out [--only name1,name2]

--mode reference   : the original ABIDES adapter (abides_fork.simulate) -- what the baseline image runs.
                     Each scenario runs in its own Python process, so memory does not accumulate
                     (the largest scenarios need about 2 GB each under the original ABIDES).
--mode submission  : the image's real `simulate` command, exactly as the harness invokes it.

Writes /out/<scenario_id>/{trace.parquet,message_trace.parquet,events.json} plus /out/summary.json
(one row per scenario: name, scenario_id, n_events, self-reported events_per_sec, whole-process
seconds, both SHA-256s recomputed from the files on disk, and which code path produced them).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/opt")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def child(config: str, out: str) -> int:
    from abides_fork.simulate import simulate

    simulate(config, out)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["reference", "submission"], required=True)
    ap.add_argument("--scenarios", default="/scenarios")
    ap.add_argument("--out", default="/out")
    ap.add_argument("--only", default="", help="comma-separated scenario file stems to run")
    ap.add_argument("--resume", action="store_true", help="keep scenarios finished by an interrupted run")
    ap.add_argument("--child", nargs=2, metavar=("CONFIG", "OUT"), help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        return child(*args.child)

    only = {s for s in args.only.split(",") if s}
    rows = []
    for path in sorted(glob.glob(os.path.join(args.scenarios, "*.json"))):
        name = os.path.basename(path)[:-5]
        if name == "index" or (only and name not in only):
            continue
        sid = json.load(open(path))["scenario_id"]
        out = os.path.join(args.out, sid)
        os.makedirs(out, exist_ok=True)
        trace = os.path.join(out, "trace.parquet")
        row_file = os.path.join(out, "row.json")
        if args.resume and os.path.exists(row_file):  # finished in an earlier, interrupted invocation
            rows.append(json.load(open(row_file)))
            print(f"{name:40s} (kept from an earlier run)", flush=True)
            continue
        if args.mode == "reference":
            cmd = [sys.executable, os.path.abspath(__file__), "--mode", "reference", "--child", path, trace]
        else:
            cmd = ["simulate", "--config", path, "--out", trace]
        t = time.perf_counter()
        r = subprocess.run(cmd, capture_output=True, text=True)
        host = time.perf_counter() - t
        if r.returncode != 0:
            print(f"{name:40s} FAILED rc={r.returncode} {r.stderr.strip()[-200:]}", flush=True)
            rows.append({"name": name, "scenario_id": sid, "failed": True, "returncode": r.returncode})
            continue
        ev = json.load(open(os.path.join(out, "events.json")))
        if args.mode == "reference":
            used = "reference"
        elif "falling back to ABIDES reference" in r.stderr:
            used = "abides-fallback"
        elif "using the Python path" in r.stderr:
            used = "python-native"
        else:
            used = "launcher"
        row = {
            "name": name, "scenario_id": sid, "n_events": ev["n_events"],
            "events_per_sec": ev["events_per_sec"], "wall_clock_sec": ev["wall_clock_sec"],
            "process_seconds": host, "trace_sha256": sha256(trace),
            "message_trace_sha256": sha256(os.path.join(out, "message_trace.parquet")),
            "reported_hashes_match_files": (ev["trace_sha256"], ev["message_trace_sha256"])
            == (sha256(trace), sha256(os.path.join(out, "message_trace.parquet"))),
            "path": used,
        }
        rows.append(row)
        json.dump(row, open(row_file, "w"))
        print(f"{name:40s} n={row['n_events']:8d} self_eps={row['events_per_sec']:12.0f} "
              f"proc={host * 1e3:8.0f} ms path={used}", flush=True)
    json.dump(rows, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
