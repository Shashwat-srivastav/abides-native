"""Table comparison of two launcher binaries on every public unit (run inside the dev container).

    python cmp_tables.py <ref binary> <new binary> [KEY=VALUE ... for the new one]
Single units: both Parquet files must read back as equal tables (arrow and pandas), the set of
files must match, and events.json must declare the real sha256 and row count of what was written.
Batch units: the same for every sub-scenario.
"""
import hashlib, json, os, shutil, subprocess, sys
import pandas as pd
import pyarrow.parquet as pq

ref, new = sys.argv[1], sys.argv[2]
extra = dict(a.split("=", 1) for a in sys.argv[3:])
base = {"PATH": "/nonexistent", "T3_HUGE": "0", "T3_PREFAULT": "0"}

def same(a, b):
    ta, tb = pq.read_table(a), pq.read_table(b)
    if ta.schema.names != tb.schema.names or [f.type for f in ta.schema] != [f.type for f in tb.schema]:
        return "schema differs"
    if ta.schema.metadata.get(b"pandas") != tb.schema.metadata.get(b"pandas"):
        return "pandas metadata differs"
    if not ta.equals(tb):
        return "arrow tables differ"
    da, db = pd.read_parquet(a), pd.read_parquet(b)
    if list(da.dtypes) != list(db.dtypes) or not da.equals(db):
        return "pandas frames differ"
    return ""

def files(d):
    out = []
    for r, _, fs in os.walk(d):
        out += [os.path.relpath(os.path.join(r, f), d) for f in fs]
    return sorted(out)

def check_events(d):
    for r, _, fs in os.walk(d):
        if "events.json" in fs and "trace.parquet" in fs:
            e = json.load(open(os.path.join(r, "events.json")))
            t = os.path.join(r, "trace.parquet")
            if e["trace_sha256"] != hashlib.sha256(open(t, "rb").read()).hexdigest():
                return "trace hash"
            if e["n_events"] != pq.read_metadata(t).num_rows:
                return "n_events"
            m = os.path.join(r, "message_trace.parquet")
            if os.path.exists(m) and "message_trace_sha256" in e and e["message_trace_sha256"] != hashlib.sha256(open(m, "rb").read()).hexdigest():
                return "ledger hash"
    return ""

ok = bad = 0
for u in sorted(os.listdir("/units")):
    if "EXAMPLE" in u:
        continue
    src = os.path.join("/units", u)
    tmp = "/dev/shm/u"
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    batch = os.path.isdir(os.path.join(src, "scenarios"))
    for f in ("scenario.json", "card.toml"):
        if os.path.exists(os.path.join(src, f)):
            shutil.copy(os.path.join(src, f), tmp)
    if batch:
        shutil.copytree(os.path.join(src, "scenarios"), tmp + "/scenarios")
    outs = []
    err = ""
    for tag, binary, env in (("a", ref, base), ("b", new, dict(base, **extra))):
        o = "/dev/shm/ct_" + tag
        shutil.rmtree(o, ignore_errors=True)
        cmd = ([binary, "simulate-batch", "--batch-dir", tmp + "/scenarios", "--out-dir", o] if batch
               else [binary, "simulate", "--config", tmp + "/scenario.json", "--out", o + "/trace.parquet"])
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            err = "%s failed rc=%d %s" % (tag, r.returncode, r.stderr[-120:])
            break
        outs.append(o)
    if not err:
        fa, fb = files(outs[0]), files(outs[1])
        if fa != fb:
            err = "file sets differ"
        else:
            for f in fa:
                if f.endswith(".parquet"):
                    err = same(os.path.join(outs[0], f), os.path.join(outs[1], f))
                    if err:
                        err = f + ": " + err
                        break
        err = err or check_events(outs[1])
    if err:
        bad += 1; print("BAD", u, err, flush=True)
    else:
        ok += 1
print("units equal %d, bad %d" % (ok, bad))
