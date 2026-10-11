"""Best-of-N whole-process time of `simulate` per scenario, with the launcher's phase breakdown.

    python bench_units.py <scenarios_dir> <out_json> <repeats> [name ...]
"""
import json
import pathlib
import re
import subprocess
import sys
import time

sdir, dest, reps = pathlib.Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
names = sys.argv[4:]
out = "/dev/shm/bo/trace.parquet"
res = {}
for nm in names or sorted(p.stem for p in sdir.glob("*.json") if p.name != "index.json"):
    best, phases, n = 1e9, "", 0
    for _ in range(reps):
        subprocess.run(["rm", "-rf", "/dev/shm/bo"])
        t0 = time.perf_counter()
        r = subprocess.run(["simulate", "--config", str(sdir / (nm + ".json")), "--out", out], capture_output=True, text=True,
                           env={"PATH": "/usr/local/bin:/usr/bin:/bin", "T3_PHASES": "1"})
        dt = time.perf_counter() - t0
        if r.returncode != 0:
            print("FAILED", nm, r.stderr[-200:])
            break
        if dt < best:
            best = dt
            m = re.findall(r"^parse=.*$", r.stderr, re.M)
            phases = m[-1] if m else ""
            n = json.loads(r.stdout)["n_events"]
    res[nm] = {"n_events": n, "best_s": best}
    print("%-34s %8d ev %8.1f ms  %s" % (nm, n, best * 1e3, phases), flush=True)
json.dump(res, open(dest, "w"), indent=1)
for oh in (0.2, 0.3, 0.4, 0.5):
    print("overhead %.1f s -> mean rate over these units %.0f" % (oh, sum(v["n_events"] / (oh + v["best_s"]) for v in res.values()) / len(res)))
