import cProfile, pstats
from t3native import native_sim
cProfile.run('native_sim.simulate("/input/scenario.json", "/tmp/o/trace.parquet")', '/tmp/s.prof')
pstats.Stats('/tmp/s.prof').sort_stats('tottime').print_stats(14)
