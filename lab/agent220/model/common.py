"""Shared data and helpers for the score-model study (pure Python, no third-party modules).

score(build) = mean over 71 units of N_u / T_u,   T_u = c + host process time of the unit.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.normpath(os.path.join(HERE, "..", "..", "bench"))

# Host scores (given). sub7 has no laptop file; sub17n is pending.
SCORES = {
    "sub7": 184858.0,
    "sub9": 183420.0,
    "sub10": 188687.0,
    "sub11m": 189018.0,
    "sub13m": 184047.0,
    "sub16m": 203394.0,
    "sub17t": 199285.0,
}
FILES = {
    "sub9": "truep_sub9s.json",
    "sub10": "truep_sub10s.json",
    "sub11m": "truep_sub11m.json",
    "sub13m": "truep_sub13m.json",
    "sub16m": "truep_sub16.json",
    "sub17n": "truep_sub17n.json",
    "sub17t": "truep_sub17t.json",
    "sub17t_b": "truep_sub17t_b.json",
    "trail0": "truep_sub17_trail0.json",
    "trail1": "truep_sub17_trail1.json",
    "sub18t": "truep_sub18t.json",
}
FIT = ["sub9", "sub10", "sub11m", "sub13m", "sub16m", "sub17t"]  # builds with score and file

# Build descriptors. Everything here is ASSUMED from the build descriptions, not measured.
FEAT = {
    #            hp: laptop ran with huge pages/prefault on (host showed these are worth nothing)
    #            stream: streaming writer; grp: rows per row group of that writer
    #            neweng: trace built in final order during the run
    #            thr: helper threads created per single-scenario run (rough guess)
    "sub9":   dict(hp=1, stream=0, grp=0,     neweng=0, thr=7),
    "sub10":  dict(hp=1, stream=0, grp=0,     neweng=0, thr=7),
    "sub11m": dict(hp=0, stream=0, grp=0,     neweng=0, thr=7),
    "sub13m": dict(hp=0, stream=1, grp=65536, neweng=0, thr=4),
    "sub16m": dict(hp=0, stream=0, grp=0,     neweng=1, thr=4),
    "sub17n": dict(hp=0, stream=0, grp=0,     neweng=1, thr=4),
    "sub17t": dict(hp=0, stream=1, grp=4096,  neweng=1, thr=3),
}
BATCH_OUT_FRAC = 0.25  # ASSUMED share of a batch unit's laptop ms that is output (batch units have no split)
NO_LEDGER = {"t3-gb-mega-throughput", "t3-gb-pop-horizon-scale", "t3-gb-horizon-240s",
             "t3-gb-highfreq-40hz-60s", "t3-gb-pop-128-agents", "t3-gb-base-30agent-30s"}


def load():
    d = {b: json.load(open(os.path.join(BENCH, f))) for b, f in FILES.items()}
    units = sorted(d["sub16m"])
    for b in d:
        assert sorted(d[b]) == units, b
    return d, units


D, UNITS = load()
N = [D["sub16m"][u]["n_events"] for u in UNITS]
NTOT = sum(N)
IS_BATCH = ["sim" not in D["sub16m"][u] for u in UNITS]
NU = len(UNITS)


def vec(build, key="ms"):
    """Per-unit laptop ms. For batch units 'out' and 'sim' are split with BATCH_OUT_FRAC (assumed)."""
    out = []
    for i, u in enumerate(UNITS):
        r = D[build][u]
        if key == "ms":
            out.append(r["ms"])
        elif key == "whole":
            out.append(r["whole_ms"])
        elif key == "out":
            out.append(r["out"] if "out" in r else BATCH_OUT_FRAC * r["ms"])
        elif key == "sim":
            out.append(r["sim"] if "sim" in r else (1 - BATCH_OUT_FRAC) * r["ms"])
        else:
            raise KeyError(key)
    return out


def groups(grp):
    """Row groups written per unit by a streaming writer (ASSUMED: ledger has as many rows as the trace;
    no ledger on the six gb units; batch units do not stream)."""
    g = []
    for i, u in enumerate(UNITS):
        if IS_BATCH[i] or not grp:
            g.append(0.0)
        else:
            files = 1 if u in NO_LEDGER else 2
            g.append(files * math.ceil(N[i] / grp))
    return g


def stream_mask():
    return [0.0 if b else 1.0 for b in IS_BATCH]


def score(c, t_ms):
    """c in seconds, t_ms = per-unit host process time in ms."""
    return sum(n / (c + max(t, 0.0) / 1000.0) for n, t in zip(N, t_ms)) / NU


def bisect(f, lo, hi, it=80):
    """root of a monotone f on [lo, hi]; returns None when there is no sign change."""
    flo, fhi = f(lo), f(hi)
    if flo == 0:
        return lo
    if flo * fhi > 0:
        return None
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def nelder_mead(f, x0, step, iters=4000, tol=1e-14):
    n = len(x0)
    pts = [list(x0)]
    for i in range(n):
        p = list(x0)
        p[i] += step[i]
        pts.append(p)
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        pts = [pts[i] for i in order]
        vals = [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) < tol:
            break
        cen = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
        refl = [cen[j] + (cen[j] - pts[-1][j]) for j in range(n)]
        fr = f(refl)
        if fr < vals[0]:
            exp = [cen[j] + 2 * (cen[j] - pts[-1][j]) for j in range(n)]
            fe = f(exp)
            if fe < fr:
                pts[-1], vals[-1] = exp, fe
            else:
                pts[-1], vals[-1] = refl, fr
        elif fr < vals[-2]:
            pts[-1], vals[-1] = refl, fr
        else:
            con = [cen[j] + 0.5 * (pts[-1][j] - cen[j]) for j in range(n)]
            fc = f(con)
            if fc < vals[-1]:
                pts[-1], vals[-1] = con, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]
                    vals[i] = f(pts[i])
    i = min(range(n + 1), key=lambda i: vals[i])
    return pts[i], vals[i]


def minimise(f, x0, step, restarts=4):
    x, v = nelder_mead(f, x0, step)
    for _ in range(restarts):
        x, v = nelder_mead(f, x, [s * 0.3 for s in step])
    return x, v
