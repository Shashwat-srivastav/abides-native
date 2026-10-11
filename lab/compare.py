"""Differential ledger: candidate vs baseline image (c4f8a635) — hashes, verdicts, speedup."""
import json, glob, os, statistics, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
base = {}
for f in glob.glob(f"{ROOT}/_archive/clone-regression-results-2/*/events.json") + glob.glob(f"{ROOT}/_archive/gb-large-rerun/*/events.json"):
    e = json.load(open(f)); base[e["scenario_id"]] = e
cand_dir = sys.argv[1]
reports = [json.load(open(f)) for f in glob.glob(f"{cand_dir}/*/report.json")]
verdict = {r["scenario_id"]: r for rep in reports for r in rep["results"]}
rows, mism, fails = [], [], []
for f in glob.glob(f"{cand_dir}/*/*/events.json"):
    e = json.load(open(f)); sid = e["scenario_id"]; b = base.get(sid)
    v = verdict.get(sid, {})
    if v.get("failure_labels"): fails.append((sid, v["failure_labels"]))
    if not b: continue
    same = e["trace_sha256"] == b["trace_sha256"] and e.get("message_trace_sha256") == b.get("message_trace_sha256")
    if not same: mism.append(sid)
    rows.append((e["events_per_sec"] / b["events_per_sec"], e["events_per_sec"], b["events_per_sec"], sid))
print(f"scenarios with output: {len(rows)}  verdicts: {len(verdict)}  failed: {len(fails)}  hash-mismatch vs baseline: {len(mism)}")
for s in fails: print("  FAIL", s)
for s in mism: print("  HASH-DIFF", s)
if rows:
    sp = [r[0] for r in rows]
    print(f"speedup  median {statistics.median(sp):.3f}x  mean {statistics.mean(sp):.3f}x  min {min(sp):.3f}x  max {max(sp):.3f}x")
    print(f"eps mean cand {statistics.mean(r[1] for r in rows):.0f}  base {statistics.mean(r[2] for r in rows):.0f}")
