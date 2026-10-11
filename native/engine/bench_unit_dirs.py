"""Best-of-N whole-process time of `simulate` on unit directories (scenario.json beside card.toml).

    python bench_unit_dirs.py <units_dir> <out_json> <repeats> [unit ...]
The unit directory is the config's directory, as on the scoring host, so the launcher sees the card.
Without unit names, every single-scenario unit (a directory holding scenario.json) is run.
Per unit: best time (ms), event count, page faults and peak memory of the best run, output bytes.
These are warm runs inside one container: good for counting work, a poor guide to the scoring host.
"""
import json
import os
import re
import subprocess
import sys
import time

units, dest, reps = sys.argv[1], sys.argv[2], int(sys.argv[3])
names = sys.argv[4:] or sorted(u for u in os.listdir(units) if os.path.isfile(os.path.join(units, u, "scenario.json")))
# The memory switches are passed through so a build can be measured in the mode it was shipped in.
ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "T3_PHASES": "1"}
ENV.update({k: v for k, v in os.environ.items() if k in ("T3_HUGE", "T3_PREFAULT", "T3_TRAIL", "T3_LEDGER")})
res = {}
for u in names:
    best = None
    for _ in range(reps):
        subprocess.run(["rm", "-rf", "/dev/shm/bo"])
        t0 = time.perf_counter()
        r = subprocess.run(["simulate", "--config", "%s/%s/scenario.json" % (units, u), "--out", "/dev/shm/bo/trace.parquet"],
                           capture_output=True, text=True, env=ENV)
        dt = time.perf_counter() - t0
        if r.returncode != 0:
            print("FAILED", u, r.stderr[-200:])
            best = None
            break
        if best is None or dt < best["ms"] / 1e3:
            m = re.search(r"minflt=(\d+).*?maxrss=(\d+) MB", r.stderr)
            out_bytes = sum(os.path.getsize(os.path.join("/dev/shm/bo", f)) for f in os.listdir("/dev/shm/bo")
                            if f.endswith(".parquet"))
            best = {"ms": round(dt * 1e3, 1), "n_events": json.loads(r.stdout)["n_events"],
                    "minflt": int(m.group(1)) if m else None, "maxrss_mb": int(m.group(2)) if m else None,
                    "out_bytes": out_bytes, "ledger": os.path.exists("/dev/shm/bo/message_trace.parquet")}
    if best:
        res[u] = best
        print(u, best, flush=True)
json.dump(res, open(dest, "w"), indent=1)
