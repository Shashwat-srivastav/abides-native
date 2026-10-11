#!/bin/sh
# Usage (inside container): sh /w/run_pair.sh <scenario_name>
# Runs the uninstrumented `simulate` CLI and refdump.py on the same scenario and prints both shas.
set -e
n="$1"
rm -rf /w/runs/$n; mkdir -p /w/runs/$n/base /w/runs/$n/dump
simulate --config /sc/$n.json --out /w/runs/$n/base/trace.parquet > /w/runs/$n/base/stdout.json
python /w/refdump.py /sc/$n.json /w/runs/$n/dump > /w/runs/$n/dump/summary.json
python - "$n" <<'PY'
import json,sys
n=sys.argv[1]
b=json.load(open(f"/w/runs/{n}/base/events.json")); d=json.load(open(f"/w/runs/{n}/dump/summary.json"))
ok = b["trace_sha256"]==d["trace_sha256"] and b["message_trace_sha256"]==d["message_trace_sha256"]
res={"scenario":n,"equal":ok,"base_trace_sha256":b["trace_sha256"],"dump_trace_sha256":d["trace_sha256"],
     "base_msg_sha256":b["message_trace_sha256"],"dump_msg_sha256":d["message_trace_sha256"],
     "n_events":d["n_events"],"n_messages":d["n_messages"],"dump_bytes":d["dump_bytes"],
     "record_counts":d["record_counts"],"base_wall":b["wall_clock_sec"],"dump_wall":d["wall_clock_sec"]}
json.dump(res,open(f"/w/runs/{n}/equality.json","w"),indent=1)
print(json.dumps(res))
PY
