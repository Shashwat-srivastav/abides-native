import sys, traceback
class F:
    def find_spec(self, name, path=None, target=None):
        if name == "pandas":
            traceback.print_stack(limit=12)
        return None
sys.meta_path.insert(0, F())
sys.path.insert(0, "/native/pkg")
from t3native import native_sim
native_sim.simulate("/sc/s001_price_time_priority.json", "/tmp/o/trace.parquet")
print("pandas imported:", "pandas" in sys.modules)
