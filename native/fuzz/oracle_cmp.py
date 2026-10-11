import sys, json, os, subprocess, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/native/pkg"); sys.path.insert(0, "/opt")
os.chdir("/tmp")
rec = json.loads(open(sys.argv[1]).readline()); s = rec["scenario"]
json.dump(s, open("/tmp/s.json", "w"))
# native oracle dump
env = dict(os.environ, T3_ORACLE_DUMP="1")
p = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0,'/native/pkg'); from t3native import native_sim; native_sim.simulate('/tmp/s.json','/tmp/nat/trace.parquet')"], env=env, capture_output=True, text=True)
nat = [l.split() for l in p.stderr.splitlines() if l.startswith("F ")]
from abides_core import abides
from abides_fork.config import build_config
from abides_fork.simulate import reset_abides_counters
reset_abides_counters(); cfg = build_config(s); orc = cfg["custom_properties"]["oracle"]
abides.run(cfg)
ref = orc.f_log["ABM"][1:]
print("n native", len(nat), "n ref", len(ref), "types", sorted({type(r["FundamentalTime"]).__name__ for r in ref}))
for i, (a, b) in enumerate(zip(nat, ref)):
    ts_n = float(a[2]) if a[1] == "f" else int(a[2])
    bt = b["FundamentalTime"]
    same = (isinstance(ts_n, float) == (not isinstance(bt, (int, __import__("numpy").integer)))) and float(ts_n) == float(bt) and (isinstance(ts_n, float) or ts_n == bt) and int(a[4]) == b["FundamentalValue"]
    if not same:
        print("first diff at", i)
        for j in range(max(0, i - 4), min(len(ref), i + 3)):
            print("  nat", nat[j] if j < len(nat) else None, " ref", repr(ref[j]["FundamentalTime"]), ref[j]["FundamentalValue"])
        break
else:
    print("no diff in common prefix")
