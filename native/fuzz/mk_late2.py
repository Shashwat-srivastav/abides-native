import json, copy, random
rng = random.Random(5)
base = json.load(open("cases/base_late.json")) if False else None
out=[]
for i in range(40):
    s = {"description":"t","scenario_family":"fuzz","schema_version":2,"horizon_ns":rng.choice([1000000000,1500000000,2000000000]),
     "exchange_config":{"symbol":"SYM","stp_policy":"cancel_newest"},
     "oracle_config":{"type":"mean_reverting","params":{"initial_price":100000,"kappa":rng.choice([2.0,10.0,50.0]),"sigma":rng.choice([0.5,2.0,10.0]),"jump_intensity":rng.choice([0.0,3.0]),"jump_sigma":500.0}},
     "latency_config":{"model":"uniform","params":{"min_ns":1000000,"max_ns":rng.choice([2e8,4e8,6e8])}},
     "agent_configs":[
      {"agent_type":"MarketMaker","count":1,"params":{"spread_ticks":4,"depth_levels":2,"size_per_level":10,"rebalance_interval_ns":50000000}},
      {"agent_type":"NoiseTrader","count":2,"params":{"order_size_mean":5,"order_size_std":1,"price_offset_ticks":3,"arrival_rate_hz":7}},
      {"agent_type":"ValueTrader","count":6,"params":{"order_size_mean":10,"threshold_ticks":rng.choice([0,5,20]),"arrival_rate_hz":rng.choice([3.3,5,9])}}],
     "scenario_id":f"t_lateB{i}","seed":rng.randint(0,2**32-1)}
    out.append({"scenario":s,"tags":["targeted_late_close"]})
for r in out: print(json.dumps(r))
