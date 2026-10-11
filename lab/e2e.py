"""Host-measured end-to-end `docker run` wall clock (what the Final runner ranks), median of N."""
import json, subprocess, statistics, sys, time, pathlib, shutil
IMAGES = sys.argv[1].split(","); REPS = int(sys.argv[2]); SC = sys.argv[3].split(",")
SRC = pathlib.Path(__file__).resolve().parent.parent / "track3-simulation-public-clone/regression_suite/scenarios"
OUT = pathlib.Path(__file__).resolve().parent / "e2e"
res = {}
for rep in range(REPS):
    for sc in SC:
        for img in IMAGES:
            ind = OUT / "in" / sc; ind.mkdir(parents=True, exist_ok=True); shutil.copy(SRC / f"{sc}.json", ind / "scenario.json")
            od = OUT / img.replace(":", "_") / sc; shutil.rmtree(od, ignore_errors=True); od.mkdir(parents=True)
            t = time.monotonic()
            subprocess.run(["docker", "run", "--rm", "--network", "none", "--cpus", "4", "-v", f"{ind.as_posix()}:/input:ro",
                            "-v", f"{od.as_posix()}:/output", img, "simulate", "--config", "/input/scenario.json",
                            "--out", "/output/trace.parquet"], check=True, capture_output=True)
            wall = time.monotonic() - t
            e = json.load(open(od / "events.json"))
            res.setdefault((img, sc), []).append((wall, e["n_events"], e["events_per_sec"], e["trace_sha256"], e["message_trace_sha256"]))
print(f"{'scenario':26} {'image':28} {'n_events':>9} {'host_wall_s':>11} {'host_eps':>10} {'self_eps':>10}")
for sc in SC:
    ref = {(x[3], x[4]) for x in res[(IMAGES[0], sc)]}
    for img in IMAGES:
        r = res[(img, sc)]; w = statistics.median(x[0] for x in r); n = r[0][1]
        same = {(x[3], x[4]) for x in r} == ref
        print(f"{sc:26} {img:28} {n:9d} {w:11.2f} {n / w:10.0f} {statistics.median(x[2] for x in r):10.0f} {'' if same else 'HASH-DIFF'}")
