"""Check runs of units whose card does not require a message ledger.

    python check_skip.py /units /skip /full
/units: the public units; /skip/<unit>: output of a run that read the card; /full/<unit>: output of
the same image with T3_LEDGER=1. Checks, per unit: no message_trace.parquet in the skip run; the
trace table equals the unit's reference; trace bytes equal the full run's; events.json declares the
file's hash and row count and carries no ledger keys.
"""
import hashlib
import json
import os
import sys

import pyarrow.parquet as pq

units, skip, full = sys.argv[1:4]
bad = 0
for u in sorted(os.listdir(skip)):
    d = os.path.join(skip, u)
    problems = []
    names = sorted(os.listdir(d))
    if names != ["events.json", "trace.parquet"]:
        problems.append("files %s" % names)
    raw = open(os.path.join(d, "trace.parquet"), "rb").read()
    ev = json.load(open(os.path.join(d, "events.json")))
    t = pq.read_table(os.path.join(d, "trace.parquet"))
    ref = pq.read_table(os.path.join(units, u, "trace.parquet"))
    if not t.equals(ref):
        problems.append("trace table differs from the reference")
    if not t.to_pandas().equals(ref.to_pandas()):
        problems.append("trace frame differs from the reference")
    if ev["trace_sha256"] != hashlib.sha256(raw).hexdigest():
        problems.append("declared hash")
    if ev["n_events"] != t.num_rows:
        problems.append("n_events")
    if "n_messages" in ev or "message_trace_sha256" in ev:
        problems.append("ledger keys present")
    fd = os.path.join(full, u)
    if sorted(os.listdir(fd)) != ["events.json", "message_trace.parquet", "trace.parquet"]:
        problems.append("full run files %s" % sorted(os.listdir(fd)))
    elif open(os.path.join(fd, "trace.parquet"), "rb").read() != raw:
        problems.append("trace bytes differ from the full run")
    print(u, t.num_rows, "OK" if not problems else "BAD " + "; ".join(problems))
    bad += bool(problems)
print("units checked %d, bad %d" % (len(os.listdir(skip)), bad))
sys.exit(1 if bad else 0)
