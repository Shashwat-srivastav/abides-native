"""Process time per unit with the inputs on an in-memory mount (the unit folders on this laptop
are a slow Windows mount, which adds 10-20 ms per run that the scoring host does not have).

    python true_p.py <binary> <out_json> <repeats> [KEY=VALUE ...]
Per unit: the smallest sum of the launcher's phases (parse + create + sim + out), in ms, and the
event count. Batch units: whole-process time of simulate-batch.
"""
import json, os, re, shutil, subprocess, sys, time
binary, dest, reps = sys.argv[1], sys.argv[2], int(sys.argv[3])
env = {"PATH": "/usr/bin:/bin", "T3_PHASES": "1", "T3_HUGE": "0", "T3_PREFAULT": "0"}
env.update(dict(a.split("=", 1) for a in sys.argv[4:]))
src, tmp = "/units", "/dev/shm/u"
res = {}
for u in sorted(os.listdir(src)):
    if "EXAMPLE" in u:
        continue
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    batch = os.path.isdir(os.path.join(src, u, "scenarios"))
    for f in ("scenario.json", "card.toml"):
        if os.path.exists(os.path.join(src, u, f)):
            shutil.copy(os.path.join(src, u, f), tmp)
    if batch:
        shutil.copytree(os.path.join(src, u, "scenarios"), tmp + "/scenarios")
    best = None
    for _ in range(reps):
        shutil.rmtree("/dev/shm/bo", ignore_errors=True)
        if batch:
            cmd = [binary, "simulate-batch", "--batch-dir", tmp + "/scenarios", "--out-dir", "/dev/shm/bo"]
        else:
            cmd = [binary, "simulate", "--config", tmp + "/scenario.json", "--out", "/dev/shm/bo/trace.parquet"]
        t0 = time.perf_counter()
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        dt = (time.perf_counter() - t0) * 1e3
        if r.returncode != 0:
            print("FAILED", u, r.stderr[-200:]); best = None; break
        j = json.loads(r.stdout)
        n = j.get("n_events", j.get("total_events"))
        m = re.search(r"parse=([\d.]+) create=([\d.]+) sim=([\d.]+) out=([\d.]+)", r.stderr)
        ms = sum(float(x) for x in m.groups()) if (m and not batch) else dt
        if best is None or ms < best["ms"]:
            best = {"ms": round(ms, 2), "n_events": n, "whole_ms": round(dt, 2)}
            if m and not batch:
                best.update(sim=float(m.group(3)), out=float(m.group(4)))
    if best:
        res[u] = best
json.dump(res, open(dest, "w"), indent=1)
print(len(res), "units, sum %.0f ms" % sum(v["ms"] for v in res.values()))
