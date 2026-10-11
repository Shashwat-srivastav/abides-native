import time, resource; T = time.perf_counter; t0 = T()
from t3native import native_sim
t1 = T(); ev = native_sim.simulate("/input/scenario.json", "/tmp/o/trace.parquet"); t2 = T()
print(f"imports {t1-t0:.2f}  simulate {t2-t1:.2f}  engine {ev['wall_clock_sec']:.2f}  peakRSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f}MiB")
