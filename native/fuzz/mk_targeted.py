import json, sys, copy
base = {"description":"t","scenario_family":"fuzz","schema_version":2,"horizon_ns":1000000000,
 "exchange_config":{"symbol":"SYM","stp_policy":"cancel_newest"},
 "oracle_config":{"type":"mean_reverting","params":{"initial_price":100000,"kappa":0.0,"sigma":1.0,"jump_intensity":0.0,"jump_sigma":0.0}},
 "latency_config":{"model":"deterministic","params":{"mean_ns":300000000,"min_ns":0,"max_ns":1e12}},
 "agent_configs":[
  {"agent_type":"MarketMaker","count":1,"params":{"spread_ticks":4,"depth_levels":2,"size_per_level":10,"rebalance_interval_ns":100000000}},
  {"agent_type":"NoiseTrader","count":2,"params":{"order_size_mean":5,"order_size_std":1,"price_offset_ticks":3,"arrival_rate_hz":7}},
  {"agent_type":"ValueTrader","count":5,"params":{"order_size_mean":10,"threshold_ticks":0,"arrival_rate_hz":3.3}}],
 "scenario_id":"t_lateclose","seed":7}
out=[]
for i,(lat,sig) in enumerate([(3e8,1.0),(2e8,10.0),(4.5e8,5.0),(1e8,50.0)]):
    s=copy.deepcopy(base); s["scenario_id"]=f"t_late{i}"; s["latency_config"]["params"]["mean_ns"]=lat
    s["oracle_config"]["params"]["sigma"]=sig; s["seed"]=100+i
    out.append({"scenario":s,"tags":["targeted_late_close"]})
for r in out: print(json.dumps(r))
