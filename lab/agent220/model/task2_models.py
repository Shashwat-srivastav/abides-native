"""Task 2: small extensions of T_u = c + k*p_u, each tested against the six scored builds.

General form (per unit u of build b), all times in ms except c (s):
  T = c + k * m^hp_b * e^neweng_b * [(p - out) + q*out]
        + stream_b * (d + r * N_u/1e5 + g * G_u)        (single-scenario units only)
        + tau * thr_b
c is ASSUMED on a grid; the listed parameters are FITTED by least squares on relative score error.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # needed under python -I
from common import *

CG = [0.36, 0.40, 0.44, 0.471]
DEFAULT = dict(k=2.0, q=1.0, m=1.0, e=1.0, d=0.0, r=0.0, g=0.0, tau=0.0)
STEP = dict(k=0.4, q=0.5, m=0.15, e=0.15, d=5.0, r=5.0, g=1.0, tau=2.0)
MODELS = [
    ("M0  k", ["k"]),
    ("M1  k, q (out vs sim)", ["k", "q"]),
    ("M2  k, d (stream, fixed/unit)", ["k", "d"]),
    ("M3  k, r (stream, per 100K rows)", ["k", "r"]),
    ("M4  k, g (stream, per row group)", ["k", "g"]),
    ("M5  k, tau (per thread)", ["k", "tau"]),
    ("M6  k, m (laptop memory mode)", ["k", "m"]),
    ("M7  k, e (new engine factor)", ["k", "e"]),
    ("M8  k, e, d", ["k", "e", "d"]),
    ("M9  k, e, r", ["k", "e", "r"]),
    ("M10 k, e, g", ["k", "e", "g"]),
    ("M11 k, e, tau", ["k", "e", "tau"]),
    ("M12 k, m, d", ["k", "m", "d"]),
    ("M13 k, q, e", ["k", "q", "e"]),
    ("M14 k, m, e, d (5 with c)", ["k", "m", "e", "d"]),
    ("M15 k, m, e, r (5 with c)", ["k", "m", "e", "r"]),
]
_cache = {}


def base(build, key):
    if (build, key) not in _cache:
        _cache[(build, key)] = vec(build, key)
    return _cache[(build, key)]


def host_ms(build, th, p=None, out=None, feat=None):
    """Per-unit host process ms under parameter dict th."""
    f = feat or FEAT[build]
    p = p if p is not None else base(build, "ms")
    o = out if out is not None else base(build, "out")
    scale = th["k"] * (th["m"] if f["hp"] else 1.0) * (th["e"] if f["neweng"] else 1.0)
    G = groups(f["grp"]) if (f["stream"] and th["g"]) else None
    sm = stream_mask()
    t = []
    for i in range(NU):
        x = scale * ((p[i] - o[i]) + th["q"] * o[i]) + th["tau"] * f["thr"]
        if f["stream"] and sm[i]:
            x += th["d"] + th["r"] * N[i] / 1e5 + (th["g"] * G[i] if G else 0.0)
        t.append(x)
    return t


def fit(names, c, builds=FIT):
    def obj(x):
        th = dict(DEFAULT)
        th.update(zip(names, x))
        if th["k"] <= 0 or th["m"] <= 0 or th["e"] <= 0:
            return 1e9
        return sum((score(c, host_ms(b, th)) / SCORES[b] - 1) ** 2 for b in builds)
    best = None
    for k0 in (0.8, 2.0, 3.5):
        x0 = [k0 if n == "k" else DEFAULT[n] for n in names]
        x, v = minimise(obj, x0, [STEP[n] for n in names])
        if best is None or v < best[1]:
            best = (x, v)
    th = dict(DEFAULT)
    th.update(zip(names, best[0]))
    return th


def residuals(th, c, builds=FIT):
    return [100 * (score(c, host_ms(b, th)) / SCORES[b] - 1) for b in builds]


def implied_k(build, c):
    p = base(build, "ms")
    return bisect(lambda k: score(c, [k * x for x in p]) - SCORES[build], 0.0, 50.0)


def main(out):
    P = out.append
    P("== TASK 2: extended models ==")
    P("(2a) anchored pairs. k is FITTED exactly on the earlier build of the pair (c ASSUMED), applied to the")
    P("     later build's laptop ms; the penalty is whatever is then needed to hit the later build's score.")
    P("     Pair A = sub11m -> sub13m (streaming after the run, 65,536-row groups).")
    P("     Pair B = sub16m -> sub17t (streaming during the run, 4,096-row groups; also contains sub17n's changes).")
    sm = stream_mask()
    P("%-6s | %-23s | %-23s | %-23s" % ("c", "fixed ms/unit  A    B", "ms per 100K rows A    B", "ms per row group A    B"))
    for c in CG:
        row = []
        for a, b in (("sub11m", "sub13m"), ("sub16m", "sub17t")):
            k = implied_k(a, c)
            p = base(b, "ms")
            G = groups(FEAT[b]["grp"])
            fx = bisect(lambda d: score(c, [k * p[i] + d * sm[i] for i in range(NU)]) - SCORES[b], -50, 500)
            rw = bisect(lambda r: score(c, [k * p[i] + r * sm[i] * N[i] / 1e5 for i in range(NU)]) - SCORES[b], -50, 500)
            gg = bisect(lambda g: score(c, [k * p[i] + g * G[i] for i in range(NU)]) - SCORES[b], -5, 100)
            row.append((fx, rw, gg))
        A, B = row
        P("%-6.3f | %10.1f %10.1f  | %10.1f %10.1f  | %10.2f %10.3f" % (c, A[0], B[0], A[1], B[1], A[2], B[2]))
    P("     A form is consistent when A and B agree. Fixed and per-row agree within 7-50% (best at high c);")
    P("     per-row-group disagrees 9-16x (sub17t writes about 12x more groups for a similar total penalty).")
    P("")
    P("(2b) the same pairs read as a multiplier on host process time instead (FITTED; c ASSUMED):")
    P("     ratio = [k needed by later build] / [k of earlier build]; 1.00 means the laptop ratio transfers.")
    pairs = (("sub9", "sub10"), ("sub10", "sub11m"), ("sub11m", "sub13m"), ("sub13m", "sub16m"),
             ("sub11m", "sub16m"), ("sub16m", "sub17t"))
    P("%-6s " % "c" + " ".join("%16s" % (a + ">" + b) for a, b in pairs))
    for c in CG:
        P("%-6.3f " % c + " ".join("%16.2f" % (implied_k(b, c) / implied_k(a, c)) for a, b in pairs))
    P("")
    P("(2c) joint fits to six scores. rms and max are relative score errors in %. 'free' = 6 - fitted - 1 (c).")
    P("     Upload noise is stated as ~0.1%; a model 'fits' only if its residuals are of that order.")
    res_tab = {}
    for name, names in MODELS:
        P("  " + name)
        for c in CG:
            th = fit(names, c)
            rs = residuals(th, c)
            rms = (sum(x * x for x in rs) / len(rs)) ** 0.5
            res_tab[(name, c)] = (th, rms)
            P("    c=%.3f  %-44s rms %5.2f  max %5.2f  free %d | %s" % (
                c, " ".join("%s=%.3g" % (n, th[n]) for n in names), rms, max(abs(x) for x in rs),
                6 - len(names) - 1, " ".join("%+5.1f" % x for x in rs)))
    P("    (residual columns: " + " ".join(FIT) + ")")
    return res_tab


if __name__ == "__main__":
    o = []
    main(o)
    print("\n".join(o))
