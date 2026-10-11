import time, sys; T0 = time.perf_counter()
import json, pathlib
t_imp0 = time.perf_counter()
from t3native import native_sim, writer   # numpy + pyarrow
t_imp1 = time.perf_counter()
for out in ("/tmp/o", "/output"):
    pathlib.Path(out).mkdir(parents=True, exist_ok=True)
    t = time.perf_counter(); ev = native_sim.simulate("/input/scenario.json", out + "/trace.parquet"); t2 = time.perf_counter()
    print(f"{out:8s} simulate() total {t2 - t:.3f}s  engine {ev['wall_clock_sec']:.3f}s  n={ev['n_events']}")
print(f"imports {t_imp1 - t_imp0:.3f}s; process-to-imports {t_imp0 - T0:.3f}s")
