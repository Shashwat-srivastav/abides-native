#!/bin/sh
# Inside container. (1) --events all on ra01 must keep shas equal to base run;
# (2) second refdump run on ra01 must give a byte-identical dump.tsv (determinism).
set -e
n=ra01_fundamental_shock_mid
rm -rf /w/runs/$n/dump_all /w/runs/$n/dump2
python /w/refdump.py /sc/$n.json /w/runs/$n/dump_all --events all 2>/dev/null > /tmp/s1.json; cp /tmp/s1.json /w/runs/$n/dump_all/summary.json
python /w/refdump.py /sc/$n.json /w/runs/$n/dump2 2>/dev/null > /tmp/s2.json; cp /tmp/s2.json /w/runs/$n/dump2/summary.json
python - <<'PY'
import json,hashlib
n="ra01_fundamental_shock_mid"
b=json.load(open(f"/w/runs/{n}/base/events.json"))
for d in ("dump_all","dump2"):
    s=json.load(open(f"/w/runs/{n}/{d}/summary.json"))
    print(d, "trace_eq", s["trace_sha256"]==b["trace_sha256"], "msg_eq", s["message_trace_sha256"]==b["message_trace_sha256"], s["record_counts"])
h=lambda p: hashlib.sha256(open(p,"rb").read()).hexdigest()
print("dump.tsv run1==run2:", h(f"/w/runs/{n}/dump/dump.tsv")==h(f"/w/runs/{n}/dump2/dump.tsv"))
PY
grep '^E' /w/runs/$n/dump_all/dump.tsv | cut -f4 | sort | uniq -c
