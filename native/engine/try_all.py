import sys, json, glob, os, time, statistics
sys.path.insert(0, "/native/pkg")
from t3native import native_sim
base = {}
for f in glob.glob("/base/*/events.json"):
    e = json.load(open(f)); base[e["scenario_id"]] = e
ok = bad = 0; rates = []; fails = []
for sc in sorted(glob.glob(sys.argv[1] + "/*.json")):
    name = os.path.basename(sc)
    if name == "index.json": continue
    s = json.load(open(sc)); sid = s["scenario_id"]
    out = f"/tmp/o/{sid}"; os.makedirs(out, exist_ok=True)
    try:
        ev = native_sim.simulate(sc, out + "/trace.parquet")
    except Exception as ex:
        fails.append((name, f"EXC {type(ex).__name__}: {ex}")); bad += 1; continue
    b = base.get(sid)
    same = b and ev["trace_sha256"] == b["trace_sha256"] and ev["message_trace_sha256"] == b["message_trace_sha256"]
    if same: ok += 1; rates.append(ev["events_per_sec"])
    else:
        bad += 1
        fails.append((name, f"n={ev['n_events']} vs {b and b['n_events']}  msgs={ev['n_messages']} vs {b and b['n_messages']}"))
    print(f"{'OK ' if same else 'BAD'} {name:40s} n={ev['n_events']:8d} eps={ev['events_per_sec']:12.0f}", flush=True)
print(f"\nidentical: {ok}  different: {bad}")
for f in fails: print("  FAIL", *f)
if rates: print(f"eps mean {statistics.mean(rates):.0f} median {statistics.median(rates):.0f}")
print("pandas imported:", "pandas" in sys.modules)
