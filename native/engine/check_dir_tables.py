"""Compare single-scenario outputs produced on the host by `docker run` with stored outputs.

    python check_dir_tables.py <new_dir> <stored_dir>
new_dir/<name>/{trace.parquet,message_trace.parquet,events.json}; the stored directory is keyed by
scenario_id (read from events.json). Same criteria as check_fast.py.
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
n = bad = 0
for d in sorted(p for p in new.iterdir() if p.is_dir()):
    n += 1
    why = ""
    if not (d / "events.json").exists():
        why = "no events.json (container failed?)"
    else:
        ev = json.loads((d / "events.json").read_text())
        ref = old / ev["scenario_id"]
        if ev["trace_sha256"] != sha(d / "trace.parquet") or ev["message_trace_sha256"] != sha(d / "message_trace.parquet"):
            why = "declared sha wrong"
        elif ev["n_events"] != pq.ParquetFile(d / "trace.parquet").metadata.num_rows:
            why = "n_events is not the row count"
        elif not same(d / "trace.parquet", ref / "trace.parquet") or not same(d / "message_trace.parquet", ref / "message_trace.parquet"):
            why = "tables differ"
    bad += bool(why)
    if why:
        print("BAD", d.name, why)
print("checked %d, bad %d" % (n, bad))
sys.exit(1 if bad or not n else 0)
