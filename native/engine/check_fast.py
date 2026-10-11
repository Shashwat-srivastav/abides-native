"""Check the launcher's built-in Parquet writer against stored outputs of the previous image.

For every scenario: run `simulate`, read both Parquet files with pandas and pyarrow, and require
the same tables (values, dtypes, nulls, column order, pandas metadata) as the stored files, and
that the hashes declared in events.json are the real sha256 of the files written.

    python check_fast.py <scenarios_dir> <stored_dir> [name ...]
stored_dir/<scenario_id>/{trace.parquet,message_trace.parquet}
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import time

import pandas as pd
import pyarrow.parquet as pq


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def same(a, b):
    ta, tb = pq.read_table(a), pq.read_table(b)
    if ta.schema.names != tb.schema.names:
        return "column names differ"
    if [f.type for f in ta.schema] != [f.type for f in tb.schema]:
        return "arrow types differ"
    if ta.schema.metadata.get(b"pandas") != tb.schema.metadata.get(b"pandas"):
        return "pandas metadata differs"
    if not ta.equals(tb):
        return "arrow tables differ"
    da, db = pd.read_parquet(a), pd.read_parquet(b)
    if list(da.dtypes) != list(db.dtypes):
        return "pandas dtypes differ"
    if not da.equals(db):
        return "pandas frames differ"
    return ""


def main():
    sdir, stored = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    names = set(sys.argv[3:])
    out = pathlib.Path("/tmp/cf")
    bad = n = 0
    total = 0.0
    for f in sorted(sdir.glob("*.json")):
        if f.name == "index.json" or (names and f.stem not in names):
            continue
        sid = json.loads(f.read_text())["scenario_id"]
        ref = stored / sid
        if not (ref / "trace.parquet").exists():
            print("SKIP", f.stem, "(no stored output)")
            continue
        subprocess.run(["rm", "-rf", str(out)])
        t0 = time.perf_counter()
        r = subprocess.run(["simulate", "--config", str(f), "--out", str(out / "trace.parquet")], capture_output=True, text=True)
        dt = time.perf_counter() - t0
        total += dt
        n += 1
        why = ""
        if r.returncode != 0:
            why = "exit %d: %s" % (r.returncode, r.stderr[-300:])
        elif "using the Python path" in r.stderr:
            why = "fell back: " + r.stderr[-300:]
        else:
            ev = json.loads((out / "events.json").read_text())
            if ev["trace_sha256"] != sha(out / "trace.parquet"):
                why = "declared trace sha is not the file's"
            elif ev["message_trace_sha256"] != sha(out / "message_trace.parquet"):
                why = "declared ledger sha is not the file's"
            elif ev["n_events"] != pq.ParquetFile(out / "trace.parquet").metadata.num_rows:
                why = "n_events is not the row count"
            else:
                why = same(out / "trace.parquet", ref / "trace.parquet") or same(out / "message_trace.parquet", ref / "message_trace.parquet")
        size = sum(p.stat().st_size for p in out.glob("*.parquet")) if out.exists() else 0
        print("%-4s %-40s %7.1f ms %8.1f MB %s" % ("BAD" if why else "ok", f.stem, dt * 1e3, size / 1e6, why), flush=True)
        bad += bool(why)
    print("checked %d, bad %d, total process time %.2f s" % (n, bad, total))
    sys.exit(1 if bad else 0)


main()
