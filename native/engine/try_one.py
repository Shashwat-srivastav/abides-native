import sys, json, pathlib, shutil
sys.path.insert(0, "/native/pkg")
from t3native import native_sim
sc, out = sys.argv[1], sys.argv[2]
ev = native_sim.simulate(sc, out + "/trace.parquet")
print(json.dumps({k: ev[k] for k in ("n_events", "events_per_sec", "trace_sha256", "message_trace_sha256", "n_messages")}))
