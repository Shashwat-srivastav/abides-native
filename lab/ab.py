"""Controlled A/B: interleaved rounds, serial, same scenario set; median eps per (image, scenario)."""
import json, subprocess, statistics, sys, pathlib, shutil
IMAGES = sys.argv[1].split(","); REPS = int(sys.argv[2]); OUT = pathlib.Path(sys.argv[3])
SC = ["as06_throughput_fast", "fastlob_core", "eq_lognormal_highsigma", "mp07_heavy_flow_oldest", "ra05_shock_momentum_heavy"]
SRC = pathlib.Path(__file__).resolve().parent.parent / "track3-simulation-public-clone/regression_suite/scenarios"
res = {}
for rep in range(REPS):
    for sc in SC:
        for img in IMAGES:
            ind = OUT / "in" / sc; ind.mkdir(parents=True, exist_ok=True); shutil.copy(SRC / f"{sc}.json", ind / "scenario.json")
            od = OUT / img.replace(":", "_") / sc / str(rep); od.mkdir(parents=True, exist_ok=True)
            subprocess.run(["docker", "run", "--rm", "--network", "none", "--cpus", "4",
                            "-v", f"{ind.as_posix()}:/input:ro", "-v", f"{od.as_posix()}:/output", img,
                            "simulate", "--config", "/input/scenario.json", "--out", "/output/trace.parquet"],
                           check=True, capture_output=True)
            e = json.load(open(od / "events.json"))
            res.setdefault((img, sc), []).append((e["events_per_sec"], e["trace_sha256"], e["message_trace_sha256"]))
            print(rep, sc, img, round(e["events_per_sec"]), flush=True)
print("\nscenario                     " + "  ".join(f"{i:>24}" for i in IMAGES))
agg = {i: [] for i in IMAGES}
for sc in SC:
    meds = []
    for img in IMAGES:
        r = res[(img, sc)]; m = statistics.median(x[0] for x in r); meds.append(m); agg[img].append(m)
        hashes = {(x[1], x[2]) for x in r}
        ref = {(x[1], x[2]) for x in res[(IMAGES[0], sc)]}
        assert hashes == ref and len(hashes) == 1, f"HASH DIVERGENCE {img} {sc}"
    print(f"{sc:28} " + "  ".join(f"{m:>12.0f} ({m/meds[0]:4.2f}x)   " for m in meds))
print("mean-of-medians              " + "  ".join(f"{statistics.mean(agg[i]):>12.0f} ({statistics.mean(agg[i])/statistics.mean(agg[IMAGES[0]]):4.2f}x)   " for i in IMAGES))
print("all hashes identical across images and repeats: OK")
