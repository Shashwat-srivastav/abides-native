"""Interleaved A/B of launcher tuning switches inside one container.

    python ab_knobs.py <scenarios_dir> <repeats> <unit,unit,...> NAME=K1=V1,K2=V2 [NAME=...]
Each round runs every variant once per unit (so drift hits all variants alike); the best
whole-process time per (unit, variant) is reported with the phases of that run.
"""
import re
import subprocess
import sys
import time

sdir, reps, units = sys.argv[1], int(sys.argv[2]), sys.argv[3].split(",")
variants = []
for a in sys.argv[4:]:
    name, _, kv = a.partition("=")
    env = dict(x.split("=") for x in kv.split(",") if x)
    variants.append((name, env))
best = {}
for _ in range(reps):
    for u in units:
        for name, env in variants:
            subprocess.run(["rm", "-rf", "/dev/shm/ab"])
            e = {"PATH": "/usr/local/bin:/usr/bin:/bin", "T3_PHASES": "1"}
            e.update(env)
            t0 = time.perf_counter()
            r = subprocess.run(["simulate", "--config", "%s/%s.json" % (sdir, u), "--out", "/dev/shm/ab/trace.parquet"],
                               capture_output=True, text=True, env=e)
            dt = time.perf_counter() - t0
            if r.returncode != 0:
                print("FAILED", u, name, r.stderr[-200:])
                continue
            m = re.findall(r"^parse=.*$", r.stderr, re.M)
            if (u, name) not in best or dt < best[(u, name)][0]:
                best[(u, name)] = (dt, m[-1] if m else "")
for u in units:
    for name, _ in variants:
        dt, ph = best.get((u, name), (0, ""))
        print("%-26s %-10s %7.1f ms  %s" % (u, name, dt * 1e3, ph))
tot = {name: sum(best[(u, name)][0] for u in units if (u, name) in best) for name, _ in variants}
print("sum over units:", {k: round(v * 1e3, 1) for k, v in tot.items()})
