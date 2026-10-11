"""Mutate public scenarios into unseen-but-plausible parameter combinations (hidden-set proxy)."""
import copy
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from gen import est_events  # noqa: E402

SC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "track3-simulation-public-clone", "regression_suite", "scenarios")
rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
per = int(sys.argv[2]) if len(sys.argv) > 2 else 3
cap = float(sys.argv[3]) if len(sys.argv) > 3 else 60000


def jitter(v, lo=0.5, hi=2.0, keep_int=True):
    x = v * rng.uniform(lo, hi)
    if isinstance(v, int) and keep_int and rng.random() < 0.7:
        return max(0, int(round(x)))
    return round(x, rng.choice([0, 1, 2, 3]))


files = sorted(f for f in glob.glob(SC + "/*.json") if not f.endswith("index.json"))
k = 0
for f in files:
    base = json.load(open(f))
    for j in range(per):
        s = copy.deepcopy(base)
        s["scenario_id"] = f"mu_{os.path.basename(f)[:-5]}_{j}_{rng.randint(0, 999)}"
        s["seed"] = rng.choice([rng.randint(0, 2**32 - 1), 0, 1, 2**32 - 1]) if rng.random() < 0.3 else rng.randint(0, 2**32 - 1)
        muts = []
        for a in s["agent_configs"]:
            p = a.setdefault("params", {})
            for key in list(p.keys()):
                if key == "fundamental_value_source":
                    continue
                if isinstance(p[key], (int, float)) and not isinstance(p[key], bool) and rng.random() < 0.35:
                    p[key] = jitter(p[key]); muts.append(key)
            if rng.random() < 0.25:
                a["count"] = max(1, a["count"] + rng.choice([-2, -1, 1, 2, 3])); muts.append("count")
        op = s["oracle_config"].setdefault("params", {})
        for key in ["kappa", "sigma", "jump_intensity", "jump_sigma", "initial_price"]:
            if key in op and rng.random() < 0.3:
                op[key] = jitter(op[key]) if op[key] else rng.choice([0.0, 0.5, 2.0, 100.0]); muts.append(key)
        if rng.random() < 0.2:
            op["scheduled_jump"] = {"time_ns": rng.randint(0, int(s["horizon_ns"])), "magnitude": rng.choice([-20000, -5000, 8000, 30000])}; muts.append("sched")
        lp = s["latency_config"].setdefault("params", {})
        for key in list(lp.keys()):
            if rng.random() < 0.3:
                lp[key] = jitter(lp[key], 0.3, 3.0); muts.append("lat." + key)
        if rng.random() < 0.1:
            s["latency_config"]["model"] = rng.choice(["log_normal", "uniform", "pareto", "deterministic"]); muts.append("model")
        ex = s["exchange_config"]
        if rng.random() < 0.25:
            ex["protocol_enforcement"] = not ex.get("protocol_enforcement", False); muts.append("proto")
        if ex.get("protocol_enforcement") and rng.random() < 0.4:
            ex["ack_delay_ns"] = rng.choice([0, 1, 100, 5000, 50000]); ex["compute_delay_ns"] = rng.choice([0, 0, 1, 10, 100, 1000]); muts.append("delays")
        if rng.random() < 0.15:
            ex["stp_policy"] = rng.choice(["cancel_newest", "cancel_oldest"]); muts.append("stp")
        # scale horizon to keep the reference fast
        if rng.random() < 0.3:
            s["horizon_ns"] = int(int(s["horizon_ns"]) * rng.uniform(0.2, 1.3)); muts.append("horizon")
        while est_events(s) > cap and int(s["horizon_ns"]) > 200_000_000:
            s["horizon_ns"] = int(int(s["horizon_ns"]) * 0.6)
        if est_events(s) > cap:
            continue
        print(json.dumps({"scenario": s, "tags": ["mutant", os.path.basename(f)[:-5]] + muts}))
        k += 1
print(k, file=sys.stderr)
