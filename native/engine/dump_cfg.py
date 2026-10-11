import sys, json, numpy as np
sys.path.insert(0, "/native/pkg"); from t3native import native_sim
ci, cf, ai, af = native_sim.build_native_config(json.load(open(sys.argv[1])))
with open(sys.argv[2], "wb") as f:
    for a in (ci, cf):
        np.array([a.size], np.int64).tofile(f); a.tofile(f)
    np.array([len(ai)], np.int64).tofile(f); ai.tofile(f); af.tofile(f)
