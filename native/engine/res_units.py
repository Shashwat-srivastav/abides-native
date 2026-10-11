"""Per-unit resource counters of the launcher (page faults, CPU time, buffer reservation vs use).

    python res_units.py <scenarios_dir> <out_json> [name ...]
Counters come from the launcher's `res:` line (T3_PHASES=1). Page-fault counts and row counts do
not depend on machine load, so they are usable where wall-clock timings are not.
"""
import json
import pathlib
import re
import subprocess
import sys

sdir, dest = pathlib.Path(sys.argv[1]), sys.argv[2]
names = sys.argv[3:] or sorted(p.stem for p in sdir.glob("*.json") if p.name != "index.json")
res = {}
for nm in names:
    subprocess.run(["rm", "-rf", "/dev/shm/ru"])
    r = subprocess.run(["simulate", "--config", str(sdir / (nm + ".json")), "--out", "/dev/shm/ru/trace.parquet"],
                       capture_output=True, text=True, env={"PATH": "/usr/local/bin:/usr/bin:/bin", "T3_PHASES": "1"})
    m = re.search(r"res: minflt=(\d+) majflt=(\d+) utime=([\d.]+) stime=([\d.]+) ms maxrss=(\d+) MB \| reserved rows: order=(\d+) quote=(\d+) ledger=(\d+) \| used: order=(\d+) quote=(\d+) ledger=(\d+)", r.stderr)
    if r.returncode != 0 or not m:
        print("FAILED", nm, r.stderr[-200:])
        continue
    g = [float(x) for x in m.groups()]
    res[nm] = dict(minflt=g[0], utime=g[2], stime=g[3], maxrss=g[4], r_order=g[5], r_quote=g[6], r_ledger=g[7],
                   u_order=g[8], u_quote=g[9], u_ledger=g[10])
json.dump(res, open(dest, "w"), indent=1)
tot = lambda k: sum(v[k] for v in res.values())
print("units %d  minflt %.0f  utime %.0f ms  stime %.0f ms" % (len(res), tot("minflt"), tot("utime"), tot("stime")))
for k in ("order", "quote", "ledger"):
    ratios = sorted(v["u_" + k] / v["r_" + k] for v in res.values() if v["r_" + k])
    print("%-7s used/reserved: min %.2f  median %.2f  max %.2f" % (k, ratios[0], ratios[len(ratios) // 2], ratios[-1]))
