import glob, json, os, sys
from t3native import native_sim
from abides_fork.simulate import simulate as ref_sim
same = diff = rej = 0
for f in sorted(glob.glob("/rc/*.json")):
    cid = os.path.basename(f)[:-5]
    r = ref_sim(f, f"/tmp/r/{cid}/trace.parquet")
    try:
        n = native_sim.simulate(f, f"/tmp/n/{cid}/trace.parquet")
    except native_sim.Unsupported as e:
        rej += 1; print(cid, "NATIVE-REJECTED (falls back to exact reference):", e); continue
    ok = (n["trace_sha256"], n["message_trace_sha256"]) == (r["trace_sha256"], r["message_trace_sha256"])
    same += ok; diff += not ok
    print(cid, "IDENTICAL" if ok else "DIFF", n["n_events"], r["n_events"])
print(f"identical={same} diff={diff} native_rejected={rej}")
