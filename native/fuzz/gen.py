"""Adversarial scenario generator for native-vs-reference differential fuzzing.

gen_case(rng, idx, category) -> (scenario_dict, tags)
Keeps expected event volume small so the reference runs in seconds.
"""
from __future__ import annotations

import copy
import json
import math
import random

BASE_EXCHANGE = {
    "symbol": "SYM", "tick_size": 1, "lot_size": 1, "min_price": 1, "max_price": 1000000,
    "stp_policy": "cancel_newest", "order_types_allowed": ["LIMIT", "MARKET", "CANCEL", "REPLACE"],
}
CATEGORIES = [
    "mix", "seed", "latency", "oracle_small_price", "oracle_jumps", "sched_jump", "exchange_proto",
    "agent_params", "horizon", "late_response", "types", "missing_keys", "large",
    "neg_time", "refcrash", "proto_delays", "tie_storm",
]


def _num(rng, v, p_float=0.3):
    """Return v as int or float JSON type (and sometimes a .5 variant)."""
    if rng.random() < p_float:
        return float(v)
    return int(v)


def _rate(rng, lo=0.5, hi=30.0):
    r = rng.random()
    if r < 0.6:
        return round(rng.uniform(lo, hi), rng.choice([0, 1, 3]))
    if r < 0.8:
        return rng.choice([1, 2, 4, 5, 8, 10, 20])
    return rng.uniform(lo, hi)


def noise(rng, heavy=False):
    p = {"order_size_mean": _num(rng, rng.choice([1, 5, 8, 10, 20, 50])),
         "order_size_std": _num(rng, rng.choice([0, 1, 2, 3, 5])),
         "price_offset_ticks": _num(rng, rng.choice([0, 1, 2, 3, 5, 10])),
         "arrival_rate_hz": _rate(rng)}
    if heavy:
        r = rng.random()
        if r < 0.2: p["order_size_mean"] = rng.choice([0, 0.5, 1.5, 2.5, -3, 0.4999, 1e-9])
        elif r < 0.35: p["order_size_std"] = rng.choice([0, 0.0, 1e-12, 0.5, 100])
        elif r < 0.5: p["price_offset_ticks"] = rng.choice([0, 0.0, 2.7, 1.5, 100, 1000])
        elif r < 0.6: p["order_size_mean"] = rng.choice([2.5, 3.5, 0.5]); p["order_size_std"] = 0
        elif r < 0.75:
            p.pop("arrival_rate_hz"); p["rebalance_interval_ns"] = _num(rng, rng.choice([1, 7, 1000, 123457, 50_000_000, 333_333_333]))
        elif r < 0.85: p["arrival_rate_hz"] = rng.choice([0, 0.0, -1, -5.5, 1e-3, 0.1, 1000, 1e5, 3.3])
        else: p.pop(rng.choice(list(p.keys())))
    return {"agent_type": "NoiseTrader", "count": rng.randint(1, 6), "params": p}


def mm(rng, heavy=False):
    p = {"spread_ticks": _num(rng, rng.choice([1, 2, 3, 4, 5, 6, 10])),
         "depth_levels": _num(rng, rng.choice([1, 2, 3, 4, 5])),
         "size_per_level": _num(rng, rng.choice([1, 5, 10, 12, 50])),
         "rebalance_interval_ns": _num(rng, rng.choice([2_000_000, 5_000_000, 10_000_000, 50_000_000, 100_000_000, 250_000_000]))}
    if heavy:
        r = rng.random()
        if r < 0.2: p["spread_ticks"] = rng.choice([0, 1, 1.9, 2.5, 3.5, 7, -4, 100])
        elif r < 0.35: p["depth_levels"] = rng.choice([0, -1, 1.5, 2.9, 8])
        elif r < 0.5: p["size_per_level"] = rng.choice([0, -2, 0.5, 1.5, 7.9, 1000])
        elif r < 0.65: p["rebalance_interval_ns"] = rng.choice([0, -5, 1, 250_000, 500_000, 1e6, 7.7e6, 123_456_789])
        elif r < 0.75: p.pop("rebalance_interval_ns"); p["arrival_rate_hz"] = _rate(rng, 1, 200)
        else: p.pop(rng.choice(list(p.keys())))
    return {"agent_type": "MarketMaker", "count": rng.randint(1, 3), "params": p}


def value(rng, heavy=False):
    p = {"fundamental_value_source": "oracle", "order_size_mean": _num(rng, rng.choice([1, 10, 25, 80])),
         "threshold_ticks": _num(rng, rng.choice([0, 1, 2, 5, 10])), "arrival_rate_hz": _rate(rng)}
    if heavy:
        r = rng.random()
        if r < 0.25: p["order_size_mean"] = rng.choice([0, 0.5, 1.5, 2.5, 24.5, -7, 3.49999])
        elif r < 0.5: p["threshold_ticks"] = rng.choice([0, -1, -10, 1.5, 2.9, -0.5, 1000, 50000])
        elif r < 0.65: p.pop("arrival_rate_hz"); p["rebalance_interval_ns"] = rng.choice([1, 999, 1_000_000, 77_777_777])
        else: p.pop(rng.choice(list(p.keys())))
    return {"agent_type": "ValueTrader", "count": rng.randint(1, 6), "params": p}


def momentum(rng, heavy=False):
    p = {"order_size_mean": _num(rng, rng.choice([1, 15, 40])), "threshold_ticks": _num(rng, rng.choice([0, 1, 2, 5])),
         "lookback": _num(rng, rng.choice([1, 2, 3, 5, 10])), "arrival_rate_hz": _rate(rng)}
    if heavy:
        r = rng.random()
        if r < 0.25: p["lookback"] = rng.choice([0, -3, 1, 1.5, 2.9, 50, 200])
        elif r < 0.5: p["threshold_ticks"] = rng.choice([0, -1, -5, 0.5, 1.5, -0.5])
        elif r < 0.65: p["order_size_mean"] = rng.choice([0, 0.5, 2.5, 14.5, -1])
        else: p.pop(rng.choice(list(p.keys())))
    return {"agent_type": "MomentumTrader", "count": rng.randint(1, 5), "params": p}


def latency(rng, heavy=False):
    model = rng.choice(["log_normal"] * 5 + ["uniform", "pareto", "deterministic"])
    if model == "log_normal":
        p = {"mean_ns": _num(rng, rng.choice([1000, 5000, 50000, 200000])), "sigma": rng.choice([0.2, 0.5, 0.6, 1.0, 1.5]),
             "min_ns": _num(rng, rng.choice([0, 100, 1000])), "max_ns": _num(rng, rng.choice([1e6, 1e7, 2e7, 1e8]))}
    elif model == "uniform":
        lo = rng.choice([0, 100, 1000, 20000])
        p = {"min_ns": _num(rng, lo), "max_ns": _num(rng, lo + rng.choice([1, 1000, 100000, 5_000_000])), "mean_ns": 5000}
    elif model == "pareto":
        p = {"min_ns": _num(rng, rng.choice([0, 1, 1000, 5000])), "alpha": rng.choice([1.1, 1.5, 2.0, 3.0]),
             "max_ns": _num(rng, rng.choice([1e6, 1e7, 5e7]))}
    else:
        p = {"mean_ns": _num(rng, rng.choice([0, 1, 1000, 5000, 100000])), "min_ns": 0, "max_ns": 1e9}
    if heavy:
        r = rng.random()
        if r < 0.1: p["sigma"] = 0; model = "log_normal"; p.setdefault("mean_ns", 1000)
        elif r < 0.2: model = rng.choice(["LogNormal", "gaussian", "", "fixed", "Uniform"]); p["mean_ns"] = rng.choice([0, 1000, 2500.5, 1500.5])
        elif r < 0.3: model = "deterministic"; p = {"mean_ns": rng.choice([0.5, 1.5, 2.5, 1000.5, 1001.5, -10, 999.4999])}
        elif r < 0.4: model = "uniform"; p = {"min_ns": rng.choice([5000, 1000]), "max_ns": rng.choice([100, 0, 999])}
        elif r < 0.5: model = "log_normal"; p = {"mean_ns": rng.choice([0, -5, 0.5, 1, 1e6, 2e7]), "sigma": rng.choice([0, 0.01, 2.5, 3.0])}
        elif r < 0.6: model = "pareto"; p = {"min_ns": rng.choice([0, 0.0, 1, 3]), "alpha": rng.choice([0.5, 0.9, 1.0, 5.0, 20.0])}
        elif r < 0.7: model = "uniform"; p = {"min_ns": rng.choice([0, 1]), "max_ns": rng.choice([1, 2, 3])}
        elif r < 0.8: p = {}  # all defaults
        elif r < 0.9: model = "log_normal"; p = {"mean_ns": 1000, "sigma": 0.5, "min_ns": 2000, "max_ns": 500}  # min>max
        else: p.pop(rng.choice(list(p.keys())), None) if p else None
    cfg = {"model": model, "params": p}
    if heavy and rng.random() < 0.05:
        cfg.pop("model")
    if heavy and rng.random() < 0.05:
        cfg.pop("params")
    return cfg


def oracle(rng):
    return {"type": "mean_reverting", "params": {
        "initial_price": _num(rng, rng.choice([100000, 100000, 50000, 1000, 250000])),
        "kappa": rng.choice([0.0, 0.05, 0.1, 0.2, 1.0]), "sigma": rng.choice([0.0005, 0.001, 0.002, 0.01]),
        "dt_ns": 1000000, "noise_type": "gaussian", "jump_intensity": rng.choice([0.0, 0.0, 0.5, 2.0]),
        "jump_sigma": rng.choice([0.0, 200.0, 1000.0])}}


def base(rng, idx):
    horizon = rng.choice([1_000_000_000, 2_000_000_000, 3_000_000_000, rng.randint(500_000_000, 5_000_000_000)])
    agents = []
    if rng.random() < 0.85: agents.append(mm(rng))
    agents.append(noise(rng))
    if rng.random() < 0.8: agents.append(value(rng))
    if rng.random() < 0.6: agents.append(momentum(rng))
    rng.shuffle(agents)
    ex = copy.deepcopy(BASE_EXCHANGE)
    return {
        "description": "fuzz", "scenario_family": "fuzz", "schema_version": 2, "horizon_ns": horizon,
        "exchange_config": ex, "oracle_config": oracle(rng), "latency_config": latency(rng),
        "agent_configs": agents,
        "output_config": {"trace_cols": ["t_ns", "agent_id", "msg_type", "side", "price", "size", "order_id"]},
        "scenario_id": f"fz{idx:05d}", "seed": rng.randint(0, 2**32 - 1),
    }


def est_events(s):
    """Rough event-volume estimate (wakeups * orders) to keep reference runtime bounded."""
    h = max(0, int(s["horizon_ns"])) / 1e9 + 1
    tot = 0.0
    for a in s["agent_configs"]:
        p = a.get("params", {})
        try:
            if "rebalance_interval_ns" in p:
                iv = max(1, int(p["rebalance_interval_ns"]))
            else:
                hz = float(p.get("arrival_rate_hz", 1.0)); iv = int(1e9 / hz) if hz > 0 else int(1e9)
                iv = max(1, iv)
        except Exception:
            iv = 1e9
        n = max(0, int(a["count"]))
        per = 2.0
        if a["agent_type"] == "MarketMaker":
            per = 4 * max(1, int(max(1, p.get("depth_levels", 3))))
        tot += n * (h * 1e9 / iv) * per
    return tot


def gen_case(rng: random.Random, idx: int, cat: str):
    s = base(rng, idx)
    tags = [cat]
    P = s["oracle_config"]["params"]
    if cat == "seed":
        s["seed"] = rng.choice([0, 1, 2, 2**31 - 1, 2**31, 2**32 - 1, 2**32 - 2, 12345])
    elif cat == "latency":
        s["latency_config"] = latency(rng, heavy=True)
    elif cat == "oracle_small_price":
        P["initial_price"] = _num(rng, rng.choice([0, 1, 2, 3, 5, 10, 20, 50]))
        P["sigma"] = rng.choice([0.0, 0.001, 0.5, 5.0, 50.0])
        if rng.random() < 0.5:
            P["jump_intensity"] = rng.choice([1.0, 5.0]); P["jump_sigma"] = rng.choice([0.0, 5.0, 100.0])
        for a in s["agent_configs"]:
            if a["agent_type"] == "NoiseTrader":
                a["params"]["price_offset_ticks"] = rng.choice([3, 10, 50])
            if a["agent_type"] == "MarketMaker":
                a["params"]["spread_ticks"] = rng.choice([2, 10, 40])
                a["params"]["depth_levels"] = rng.choice([3, 10])
    elif cat == "oracle_jumps":
        P["jump_intensity"] = rng.choice([0.0, 1e-9, 0.5, 5.0, 50.0, 1000.0, 1e5, 1e7])
        P["jump_sigma"] = rng.choice([0.0, -500.0, 1.0, 200.0, 5000.0, 1e6])
        P["kappa"] = rng.choice([0.0, 1e-9, 0.05, 10.0, 1e3, 1e9, 1e12])
        P["sigma"] = rng.choice([0.0, 1e-6, 0.001, 0.1, 10.0])
        if rng.random() < 0.3: P.pop(rng.choice(["kappa", "sigma", "jump_intensity", "jump_sigma"]))
    elif cat == "sched_jump":
        h = int(s["horizon_ns"])
        t = rng.choice([-1_000_000_000, -1, 0, 1, rng.randint(0, h), h, h - 1, h + 1, h + 500_000_000, 10 * h, 50, 1.5e8])
        P["scheduled_jump"] = {"time_ns": _num(rng, t) if not isinstance(t, float) else t,
                               "magnitude": rng.choice([-20000, -100000, -200000, -1e9, 0, 1, 5000, 1000.7, -999.9])}
        if rng.random() < 0.2: P["scheduled_jump"] = rng.choice([{}, None])
        if rng.random() < 0.3: P["jump_intensity"] = rng.choice([0.5, 5.0])
    elif cat == "exchange_proto":
        ex = s["exchange_config"]
        ex["protocol_enforcement"] = rng.choice([True, True, True, False, 1, 0])
        ch = rng.random()
        if ch < 0.3: ex["stp_policy"] = "cancel_oldest"
        elif ch < 0.55: ex["stp_policy"] = "cancel_newest"
        elif ch < 0.7: ex["stp_policy"] = rng.choice(["foo", "CANCEL_OLDEST", "none", "cancel_both", "decrement"])
        elif ch < 0.8: ex["stp_policy"] = rng.choice(["", None])
        else: ex.pop("stp_policy")
        if rng.random() < 0.6: ex["ack_delay_ns"] = _num(rng, rng.choice([0, 1, 50, 1000, 20000, 2_000_000, 37.9]))
        if rng.random() < 0.6: ex["compute_delay_ns"] = _num(rng, rng.choice([0, 1, 7, 50, 1000, 100000, 3.7]))
        # many MMs to generate self-trades
        if rng.random() < 0.5:
            s["agent_configs"].append({"agent_type": "MarketMaker", "count": 1, "params": {
                "spread_ticks": rng.choice([1, 2, 3]), "depth_levels": 3, "size_per_level": 5,
                "rebalance_interval_ns": rng.choice([500_000, 1_000_000, 3_000_000])}})
            s["horizon_ns"] = min(int(s["horizon_ns"]), 1_500_000_000)
    elif cat == "agent_params":
        f = [noise, mm, value, momentum]
        s["agent_configs"] = [rng.choice(f)(rng, heavy=True) for _ in range(rng.randint(2, 5))]
    elif cat == "horizon":
        s["horizon_ns"] = rng.choice([0, 1, 49, 50, 51, 100, 999, 1_000_000, 50_000_000, 999_999_999, 1_000_000_001,
                                       -1, -1_000_000, rng.randint(1, 3_000_000_000), 2.5e9])
    elif cat == "late_response":
        # latency comparable to the wake interval so responses cross mkt_close / mkt_open
        s["latency_config"] = {"model": rng.choice(["log_normal", "uniform", "deterministic"]),
                               "params": {"mean_ns": rng.choice([5e7, 2e8, 4e8]), "sigma": 0.8,
                                          "min_ns": rng.choice([0, 1e6, 1e8]), "max_ns": rng.choice([5e8, 1.5e9])}}
        for a in s["agent_configs"]:
            if a["agent_type"] == "ValueTrader":
                a["count"] = max(a["count"], 3)
        if not any(a["agent_type"] == "ValueTrader" for a in s["agent_configs"]):
            s["agent_configs"].append(value(rng))
        s["horizon_ns"] = rng.choice([1_000_000_000, 1_500_000_000, 2_000_000_000, 1_234_567_891])
        for a in s["agent_configs"]:
            p = a["params"]
            p.pop("rebalance_interval_ns", None)
            p["arrival_rate_hz"] = rng.choice([2.0, 3.0, 5.0, 7.0, 10])
    elif cat == "types":
        # int vs float everywhere
        def flo(d):
            for k, v in list(d.items()):
                if isinstance(v, bool): continue
                if isinstance(v, int) and rng.random() < 0.6: d[k] = float(v)
                elif isinstance(v, dict): flo(v)
        flo(P); flo(s["latency_config"].get("params", {}))
        for a in s["agent_configs"]:
            flo(a["params"])
            if rng.random() < 0.3: a["count"] = float(a["count"])
        if rng.random() < 0.5: s["horizon_ns"] = float(s["horizon_ns"])
    elif cat == "missing_keys":
        for _ in range(rng.randint(1, 4)):
            c = rng.random()
            if c < 0.3 and P: P.pop(rng.choice(list(P.keys())))
            elif c < 0.4: s["oracle_config"].pop("params", None)
            elif c < 0.7:
                a = rng.choice(s["agent_configs"])
                if a.get("params"): a["params"].pop(rng.choice(list(a["params"].keys())))
            elif c < 0.8:
                a = rng.choice(s["agent_configs"]); a.pop("params", None)
            else:
                s["latency_config"].get("params", {}).pop("min_ns", None)
        if rng.random() < 0.2: s["agent_configs"].append({"agent_type": "NoiseTrader", "count": 0, "params": {}})
    elif cat == "large":
        s["horizon_ns"] = rng.choice([10_000_000_000, 20_000_000_000])
        s["agent_configs"] = [mm(rng), noise(rng), value(rng), momentum(rng), noise(rng)]
        for a in s["agent_configs"]:
            a["count"] = rng.randint(2, 8)
    elif cat == "neg_time":
        c = rng.random()
        if c < 0.4:
            s["latency_config"] = {"model": "uniform", "params": {"min_ns": rng.choice([-5000, -1_000_000, -100]), "max_ns": rng.choice([100, 5000, 2_000_000])}}
        elif c < 0.6:
            s["latency_config"] = {"model": "deterministic", "params": {"mean_ns": rng.choice([-10, -1000, -60]), "min_ns": rng.choice([-2000, -50]), "max_ns": 1e9}}
        else:
            ex = s["exchange_config"]; ex["protocol_enforcement"] = True
            ex["ack_delay_ns"] = rng.choice([-1, -40, -1000, -100000])
            if rng.random() < 0.5: ex["compute_delay_ns"] = rng.choice([0, 10, 1000])
    elif cat == "refcrash":
        c = rng.random()
        a = next((x for x in s["agent_configs"] if x["agent_type"] == "NoiseTrader"), None)
        if c < 0.2 and a: a["params"]["order_size_std"] = -1
        elif c < 0.4 and a: a["params"]["price_offset_ticks"] = rng.choice([-1, -2, -0.5, -1.5])
        elif c < 0.55: s["latency_config"] = {"model": "log_normal", "params": {"mean_ns": 1000, "sigma": -0.5}}
        elif c < 0.7: s["latency_config"] = {"model": "pareto", "params": {"min_ns": 100, "alpha": rng.choice([0, -1, 0.0])}}
        elif c < 0.85:
            s["exchange_config"]["protocol_enforcement"] = True; s["exchange_config"]["compute_delay_ns"] = rng.choice([-1, -50])
        else:
            s["seed"] = rng.choice([-1, 2**32, 2**40])
    elif cat == "proto_delays":
        ex = s["exchange_config"]; ex["protocol_enforcement"] = True
        ex["stp_policy"] = rng.choice(["cancel_newest", "cancel_oldest", "zzz"])
        ex["ack_delay_ns"] = _num(rng, rng.choice([1, 49, 50, 51, 999, 40000, 1_000_000, 10_000_000]))
        ex["compute_delay_ns"] = _num(rng, rng.choice([0, 1, 2, 49, 50, 51, 100, 999, 5000]))
        s["latency_config"] = rng.choice([s["latency_config"], {"model": "deterministic", "params": {"mean_ns": rng.choice([0, 1, 50, 1000])}}])
        s["agent_configs"].append({"agent_type": "MarketMaker", "count": rng.randint(1, 2), "params": {
            "spread_ticks": rng.choice([1, 2]), "depth_levels": rng.choice([1, 3]), "size_per_level": rng.choice([3, 10]),
            "rebalance_interval_ns": rng.choice([1_000_000, 10_000_000, 30_000_000])}})
        s["horizon_ns"] = min(int(s["horizon_ns"]), 2_000_000_000)
    elif cat == "tie_storm":
        # deterministic latency + identical rates -> many exact-time ties (heap tie-break, same-ns quotes)
        s["latency_config"] = {"model": "deterministic", "params": {"mean_ns": rng.choice([0, 1, 100, 1000, 50]), "min_ns": 0, "max_ns": 1e9}}
        hz = rng.choice([10, 20, 5, 8])
        for a in s["agent_configs"]:
            a["params"].pop("rebalance_interval_ns", None); a["params"]["arrival_rate_hz"] = hz
            a["count"] = rng.randint(2, 5)
        if rng.random() < 0.5:
            s["exchange_config"]["protocol_enforcement"] = True
            s["exchange_config"]["stp_policy"] = rng.choice(["cancel_newest", "cancel_oldest"])
            if rng.random() < 0.5: s["exchange_config"]["ack_delay_ns"] = rng.choice([0, 50, 1000])
    # mix: nothing extra
    return s, tags


def generate(n, seed, cats=None, max_events=60000, start_idx=0):
    rng = random.Random(seed)
    cats = cats or CATEGORIES
    out = []
    idx = start_idx
    while len(out) < n:
        cat = cats[len(out) % len(cats)]
        s, tags = gen_case(rng, idx, cat)
        lim = max_events * (8 if cat == "large" else 1)
        if est_events(s) > lim:
            continue
        out.append((s, tags))
        idx += 1
    return out


if __name__ == "__main__":
    import sys
    for s, t in generate(int(sys.argv[1]), int(sys.argv[2])):
        print(json.dumps({"tags": t, "est": est_events(s), "scenario": s}))
