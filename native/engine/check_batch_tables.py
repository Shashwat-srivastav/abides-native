"""Compare two batch output trees by table contents (not file bytes).

    python check_batch_tables.py <new_dir> <stored_dir>
Each holds <unit>/batch_events.json and <unit>/<sub>/{trace.parquet,message_trace.parquet,events.json}.
A unit is OK when every sub's two tables equal the stored ones, every declared sha256 is the real
hash of the file written, counts agree, and batch_events.json has the stored structure.
"""
import hashlib
import json
import pathlib
import sys

import pandas as pd
import pyarrow.parquet as pq


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def same(a, b):
    ta, tb = pq.read_table(a), pq.read_table(b)
    da, db = pd.read_parquet(a), pd.read_parquet(b)
    return (ta.schema.names == tb.schema.names and [f.type for f in ta.schema] == [f.type for f in tb.schema]
            and ta.schema.metadata.get(b"pandas") == tb.schema.metadata.get(b"pandas") and ta.equals(tb)
            and list(da.dtypes) == list(db.dtypes) and da.equals(db))


new, old = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
bad = 0
for u in sorted(p.name for p in old.iterdir() if p.is_dir()):
    a = json.loads((new / u / "batch_events.json").read_text())
    r = json.loads((old / u / "batch_events.json").read_text())
    why = []
    if list(a) != list(r) or a["n_scenarios"] != r["n_scenarios"] or a["total_events"] != r["total_events"]:
        why.append("aggregate differs")
    if [x["sub"] for x in a["per_scenario"]] != [x["sub"] for x in r["per_scenario"]]:
        why.append("sub list differs")
    for x, y in zip(a["per_scenario"], r["per_scenario"]):
        d, e = new / u / x["sub"], old / u / y["sub"]
        ev = json.loads((d / "events.json").read_text())
        if x["trace_sha256"] != sha(d / "trace.parquet") or ev["trace_sha256"] != x["trace_sha256"]:
            why.append(x["sub"] + ": declared trace sha wrong")
        if ev["message_trace_sha256"] != sha(d / "message_trace.parquet"):
            why.append(x["sub"] + ": declared ledger sha wrong")
        if not (x["n_events"] == y["n_events"] == ev["n_events"] == pq.ParquetFile(d / "trace.parquet").metadata.num_rows):
            why.append(x["sub"] + ": counts differ")
        if not same(d / "trace.parquet", e / "trace.parquet"):
            why.append(x["sub"] + ": trace table differs")
        if not same(d / "message_trace.parquet", e / "message_trace.parquet"):
            why.append(x["sub"] + ": ledger table differs")
    if abs(a["events_per_sec"] - a["total_events"] / a["wall_clock_sec"]) > 0.05 * a["events_per_sec"]:
        why.append("events_per_sec inconsistent")
    bad += bool(why)
    print("BAD" if why else "ok ", u, a["n_scenarios"], a["total_events"], "wall %.3f s" % a["wall_clock_sec"], "; ".join(why))
print("batch units bad:", bad)
sys.exit(1 if bad else 0)
