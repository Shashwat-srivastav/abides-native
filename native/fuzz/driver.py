"""Differential fuzz driver (runs inside the t3-native-dev container).

  python /fz/driver.py gen   N SEED OUT.jsonl [--cats a,b] [--workers 3] [--max-events 60000]
  python /fz/driver.py file  IN.jsonl OUT.jsonl [--workers 3]          # scenarios (one per line, key "scenario")
  python /fz/driver.py renative IN.jsonl OUT.jsonl [--workers 3]       # native only vs stored ref shas in IN

Native: t3native.native_sim.simulate called directly (Unsupported/exceptions are recorded, no fallback).
Reference: abides_fork.simulate.simulate (the exact ABIDES path).
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
import traceback
import warnings

sys.path.insert(0, "/opt")
sys.path.insert(0, "/native/pkg")
sys.path.insert(0, "/fz")
warnings.filterwarnings("ignore")

TIMEOUT = int(os.environ.get("FZ_TIMEOUT", "240"))


class _TO(Exception):
    pass


def _alarm(*_):
    raise _TO("timeout")


def _run_native(path, out):
    from t3native import native_sim
    t0 = time.time()
    try:
        ev = native_sim.simulate(path, out + "/trace.parquet")
        return {"status": "ok", "trace": ev["trace_sha256"], "msg": ev["message_trace_sha256"],
                "n": ev["n_events"], "m": ev["n_messages"], "sec": round(time.time() - t0, 3)}
    except native_sim.Unsupported as e:
        return {"status": "unsupported", "err": str(e)}
    except Exception as e:  # noqa
        return {"status": "exc", "err": f"{type(e).__name__}: {e}"[:300]}


def _run_ref(path, out):
    from abides_fork.simulate import simulate
    t0 = time.time()
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(TIMEOUT)
    try:
        ev = simulate(path, out + "/trace.parquet")
        return {"status": "ok", "trace": ev["trace_sha256"], "msg": ev["message_trace_sha256"],
                "n": ev["n_events"], "m": ev["n_messages"], "sec": round(time.time() - t0, 3)}
    except _TO:
        return {"status": "timeout"}
    except Exception as e:  # noqa
        return {"status": "exc", "err": f"{type(e).__name__}: {e}"[:300]}
    finally:
        signal.alarm(0)


def verdict(nat, ref):
    if ref["status"] != "ok":
        if nat["status"] == "ok":
            return "REF_FAIL_NATIVE_OK"
        return "BOTH_FAIL"
    if nat["status"] == "unsupported":
        return "REJECTED"
    if nat["status"] != "ok":
        return "NATIVE_EXC"
    if nat["trace"] == ref["trace"] and nat["msg"] == ref["msg"]:
        return "PASS"
    return "FAIL"


def work(item):
    mode, rec = item
    s = rec["scenario"]
    sid = s.get("scenario_id", "x")
    d = os.environ.get("FZ_OUT", "/tmp/fz") + f"/{sid}"
    os.makedirs(d + "/n", exist_ok=True)
    os.makedirs(d + "/r", exist_ok=True)
    path = d + "/scenario.json"
    os.chdir(d)
    with open(path, "w") as f:
        json.dump(s, f)
    nat = _run_native(path, d + "/n")
    if mode == "renative":
        ref = rec["ref"]
    else:
        ref = _run_ref(path, d + "/r")
    out = {"id": sid, "tags": rec.get("tags", []), "verdict": verdict(nat, ref), "native": nat, "ref": ref,
           "scenario": s}
    return out


def main():
    a = sys.argv[1:]
    mode = a[0]
    workers = 3
    cats = None
    max_events = 60000
    if "--workers" in a:
        i = a.index("--workers"); workers = int(a[i + 1]); del a[i:i + 2]
    if "--cats" in a:
        i = a.index("--cats"); cats = a[i + 1].split(","); del a[i:i + 2]
    if "--max-events" in a:
        i = a.index("--max-events"); max_events = int(a[i + 1]); del a[i:i + 2]
    if mode == "gen":
        from gen import generate
        n, seed, outp = int(a[1]), int(a[2]), a[3]
        start = int(a[4]) if len(a) > 4 else seed * 10000
        recs = [{"scenario": s, "tags": t} for s, t in generate(n, seed, cats, max_events, start)]
        m = "both"
    else:
        inp, outp = a[1], a[2]
        recs = [json.loads(l) for l in open(inp) if l.strip()]
        m = "renative" if mode == "renative" else "both"
    import multiprocessing as mp
    counts = {}
    t0 = time.time()
    with open(outp, "w") as fo, mp.get_context("fork").Pool(workers, maxtasksperchild=20) as pool:
        for r in pool.imap_unordered(work, [(m, x) for x in recs]):
            fo.write(json.dumps(r) + "\n"); fo.flush()
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
            if r["verdict"] not in ("PASS",):
                print(r["verdict"], r["id"], r["tags"], json.dumps(r["native"])[:200], json.dumps(r["ref"])[:200], flush=True)
    print("DONE", len(recs), counts, f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
