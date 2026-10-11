"""Re-check stored fuzz cases against the reference hashes recorded when they were first run.

    python recheck_stored.py <dir_with_jsonl> [max_cases] [--list]

Every record that carries both a scenario and an OK reference result (ref.trace / ref.msg SHA-256
of the two Parquet files) is replayed twice inside the submission image:

  1. Python native path (`T3_NO_LAUNCHER=1 simulate`): its files must have exactly the stored
     reference hashes (this path writes through pyarrow, like the reference).
  2. The launcher (`simulate`): its files must read back as the same tables as step 1's files
     (it writes different, valid Parquet bytes), and its declared hashes must be the files' hashes.

No ABIDES run is needed, so thousands of cases take minutes. Records whose reference failed or
timed out are counted and skipped.
"""
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

import pandas as pd
import pyarrow.parquet as pq


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def same_tables(a, b):
    ta, tb = pq.read_table(a), pq.read_table(b)
    da, db = pd.read_parquet(a), pd.read_parquet(b)
    return (ta.schema.names == tb.schema.names and [f.type for f in ta.schema] == [f.type for f in tb.schema]
            and ta.schema.metadata.get(b"pandas") == tb.schema.metadata.get(b"pandas") and ta.equals(tb)
            and list(da.dtypes) == list(db.dtypes) and da.equals(db))


def load(src):
    cases, skipped = {}, 0
    for f in sorted(glob.glob(os.path.join(src, "**", "*.jsonl"), recursive=True)):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            ref = d.get("ref") or {}
            if "scenario" not in d or "id" not in d:
                continue
            if ref.get("status") != "ok" or not ref.get("trace") or not ref.get("msg"):
                skipped += 1
                continue
            key = (d["id"], ref["trace"], ref["msg"], json.dumps(d["scenario"], sort_keys=True))
            cases[key] = d
    return list(cases.values()), skipped


def run(cfg, out, env):
    subprocess.run(["rm", "-rf", out])
    r = subprocess.run(["simulate", "--config", cfg, "--out", out + "/trace.parquet"], capture_output=True, text=True,
                       env=dict(os.environ, **env))
    return r


def main():
    src = sys.argv[1]
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    cases, skipped = load(src)
    if "--list" in sys.argv:
        print("replayable cases:", len(cases), "records without an OK reference:", skipped)
        return
    if args:
        cases = cases[:: max(1, len(cases) // int(args[0]))][: int(args[0])]
    tally, t0 = {}, time.time()
    os.makedirs("/tmp/fzs", exist_ok=True)
    for i, d in enumerate(cases):
        cfg = "/tmp/fzs/case.json"
        json.dump(d["scenario"], open(cfg, "w"))
        ref = d["ref"]
        p = run(cfg, "/tmp/fzs/p", {"T3_NO_LAUNCHER": "1"})
        how_p = "abides-fallback" if "falling back to ABIDES reference" in p.stderr else "python-native"
        if p.returncode != 0:
            v = "PYTHON_PATH_FAILED"
        elif (sha("/tmp/fzs/p/trace.parquet"), sha("/tmp/fzs/p/message_trace.parquet")) != (ref["trace"], ref["msg"]):
            v = "PYTHON_PATH_DIFFERS_FROM_REFERENCE"
        else:
            l = run(cfg, "/tmp/fzs/l", {})
            how_l = "handed-to-python" if "using the Python path" in l.stderr else "launcher"
            if l.returncode != 0:
                v = "LAUNCHER_FAILED"
            else:
                ev = json.load(open("/tmp/fzs/l/events.json"))
                ok = (ev["trace_sha256"] == sha("/tmp/fzs/l/trace.parquet")
                      and ev["message_trace_sha256"] == sha("/tmp/fzs/l/message_trace.parquet")
                      and same_tables("/tmp/fzs/l/trace.parquet", "/tmp/fzs/p/trace.parquet")
                      and same_tables("/tmp/fzs/l/message_trace.parquet", "/tmp/fzs/p/message_trace.parquet"))
                v = ("OK" if ok else "LAUNCHER_TABLES_DIFFER") + " " + how_p + " / " + how_l
        tally[v] = tally.get(v, 0) + 1
        if not v.startswith("OK"):
            print("BAD", d["id"], v, (p.stderr or "")[-200:], flush=True)
        if (i + 1) % 100 == 0:
            print("progress", i + 1, "of", len(cases), "%.0f s" % (time.time() - t0), flush=True)
    print("cases", len(cases), "skipped (no OK reference)", skipped, "seconds %.0f" % (time.time() - t0))
    for k in sorted(tally):
        print("  %6d  %s" % (tally[k], k))
    sys.exit(0 if all(k.startswith("OK") for k in tally) else 1)


if __name__ == "__main__":
    main()
