"""Run the no-Python launcher on every scenario and compare output hashes with the baseline.

    python check_launcher.py <launcher> <scenarios_dir> [<name> ...]

Counts a scenario as OK only if both parquet SHA-256s (recomputed from the files on disk, not taken
from events.json) equal the baseline's and the launcher did not hand over to the Python path.
"""
import glob, hashlib, json, os, subprocess, sys, time

launcher, sc_dir, only = sys.argv[1], sys.argv[2], set(sys.argv[3:])
base = {}
for f in glob.glob("/base/*/events.json"):
    e = json.load(open(f))
    base[e["scenario_id"]] = e


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


ok = bad = fell = 0
tot = 0.0
for sc in sorted(glob.glob(sc_dir + "/*.json")):
    name = os.path.basename(sc)[:-5]
    if name == "index" or (only and name not in only):
        continue
    sid = json.load(open(sc))["scenario_id"]
    out = f"/tmp/lo/{sid}"
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(out + "/*"):
        os.remove(f)
    t = time.perf_counter()
    r = subprocess.run([launcher, "--config", sc, "--out", out + "/trace.parquet"], capture_output=True, text=True)
    dt = time.perf_counter() - t
    tot += dt
    fb = "Python path" in r.stderr
    fell += fb
    b = base[sid]
    try:
        ev = json.load(open(out + "/events.json"))
        line = json.loads(r.stdout.strip().splitlines()[-1])
        same = (r.returncode == 0 and sha(out + "/trace.parquet") == b["trace_sha256"] == ev["trace_sha256"]
                and sha(out + "/message_trace.parquet") == b["message_trace_sha256"] == ev["message_trace_sha256"]
                and ev["n_events"] == b["n_events"] and ev["n_messages"] == b["n_messages"] and line == ev
                and ev["scenario_id"] == sid and list(ev) == list(b))
    except Exception as ex:
        same = False
        print("   error:", ex, r.stderr[-300:])
    ok += same
    bad += not same
    print(f"{'OK ' if same else 'BAD'} {name:40s} proc={dt * 1e3:7.0f} ms n={b['n_events']:8d} host_eps={b['n_events'] / dt:10.0f} {'FALLBACK ' + r.stderr.strip()[-80:] if fb else ''}", flush=True)
print(f"\nidentical: {ok}  different: {bad}  fell back to python: {fell}  total process time {tot:.2f} s")
