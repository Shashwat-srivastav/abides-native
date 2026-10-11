import json, random
rng = random.Random(11)
for i in range(60):
    h = rng.choice([300_000_000, 700_000_000, 1_000_000_000, 1_300_000_007])
    P = {"initial_price": rng.choice([100000, 5000, 200]), "kappa": rng.choice([0.0, 0.5, 20.0, 1e4]), "sigma": rng.choice([1e-6, 0.001, 0.05]),
         "jump_intensity": rng.choice([2e4, 1e5, 3e5]), "jump_sigma": rng.choice([0.0, -500.0, 50.0, 3000.0])}
    if rng.random() < 0.6:
        P["scheduled_jump"] = {"time_ns": rng.choice([0, 1, rng.randint(0, h), h // 2, h - 1]), "magnitude": rng.choice([-20000, 5000, -3, 100000])}
    s = {"description": "t", "scenario_family": "fuzz", "schema_version": 2, "horizon_ns": h,
         "exchange_config": {"symbol": "SYM", "stp_policy": "cancel_newest"},
         "oracle_config": {"type": "mean_reverting", "params": P},
         "latency_config": {"model": rng.choice(["log_normal", "uniform", "pareto"]), "params": {"mean_ns": 5000, "sigma": 0.8, "min_ns": 1000, "max_ns": 3e6, "alpha": 1.5}},
         "agent_configs": [
             {"agent_type": "MarketMaker", "count": 1, "params": {"spread_ticks": 4, "depth_levels": 2, "size_per_level": 10, "rebalance_interval_ns": 20_000_000}},
             {"agent_type": "NoiseTrader", "count": 3, "params": {"order_size_mean": 8, "order_size_std": 2, "price_offset_ticks": 4, "arrival_rate_hz": 15}},
             {"agent_type": "ValueTrader", "count": rng.randint(4, 10), "params": {"order_size_mean": 20, "threshold_ticks": rng.choice([0, 2]), "arrival_rate_hz": rng.choice([50, 100, 200])}},
             {"agent_type": "MomentumTrader", "count": 2, "params": {"order_size_mean": 10, "threshold_ticks": 1, "lookback": 3, "arrival_rate_hz": 20}}],
         "scenario_id": f"t_jump{i}", "seed": rng.randint(0, 2**32 - 1)}
    print(json.dumps({"scenario": s, "tags": ["targeted_dense_megashock"]}))
