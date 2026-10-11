import sys, json, warnings, os
warnings.filterwarnings("ignore")
sys.path.insert(0, "/opt")
os.chdir("/tmp")
from abides_core import abides
from abides_fork.config import build_config
from abides_fork.simulate import reset_abides_counters
for l in open(sys.argv[1]):
    s = json.loads(l)["scenario"]
    reset_abides_counters()
    cfg = build_config(s)
    orc = cfg["custom_properties"]["oracle"]
    mkt_close = cfg["agents"][0].mkt_close
    abides.run(cfg)
    fl = orc.f_log["ABM"]
    after = [f for f in fl if f["FundamentalTime"] >= mkt_close]
    print(s["scenario_id"], "oracle.mkt_close-mkt_close(s)=", (orc.mkt_close - mkt_close)/1e9, "n_f", len(fl), "after_close", len(after), after[:3])
