"""Task 1: T_u = c + k * p_u with p_u = laptop ms. Shows that one k cannot serve all builds."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # needed under python -I
from common import *

CG = [0.30, 0.36, 0.40, 0.44, 0.471]


def implied_k(build, c, key="ms"):
    p = vec(build, key)
    return bisect(lambda k: score(c, [k * x for x in p]) - SCORES[build], 0.0, 50.0)


def main(out):
    P = out.append
    P("== TASK 1: T_u = c + k*p_u ==")
    P("laptop totals (ms, sum of 71 units; measured) and host score (given)")
    P("%-8s %8s %8s %8s %8s %9s" % ("build", "ms", "whole", "sim", "out", "score"))
    for b in FIT + ["sub17n"]:
        P("%-8s %8.0f %8.0f %8.0f %8.0f %9s" % (
            b, sum(vec(b)), sum(vec(b, "whole")), sum(vec(b, "sim")), sum(vec(b, "out")),
            ("%.0f" % SCORES[b]) if b in SCORES else "pending"))
    P("laptop repeat of one binary: sub17t %.0f vs sub17t_b %.0f ms (%.1f%%); earlier round trail1 %.0f (%.1f%%)" % (
        sum(vec("sub17t")), sum(vec("sub17t_b")), 100 * (sum(vec("sub17t_b")) / sum(vec("sub17t")) - 1),
        sum(vec("trail1")), 100 * (sum(vec("trail1")) / sum(vec("sub17t")) - 1)))
    P("")
    P("zero-process ceiling = %.0f / c  (exact): " % (NTOT / NU) +
      ", ".join("c=%.3f -> %.0f" % (c, NTOT / NU / c) for c in CG))
    P("")
    P("(1a) k each build needs, alone, to reproduce its score (FITTED exactly per build; c ASSUMED).")
    P("     If the model held, every row would show one k.")
    P("%-6s " % "c" + " ".join("%8s" % b for b in FIT) + "   max/min")
    for c in CG:
        ks = [implied_k(b, c) for b in FIT]
        P("%-6.3f " % c + " ".join("%8.3f" % k for k in ks) + "   %.2f" % (max(ks) / min(ks)))
    P("")
    P("(1b) implied host process time per unit, ms, mean over 71 units = k_b * mean(p)  (FITTED given c)")
    P("%-6s " % "c" + " ".join("%8s" % b for b in FIT))
    for c in CG:
        P("%-6.3f " % c + " ".join("%8.1f" % (implied_k(b, c) * sum(vec(b)) / NU) for b in FIT))
    P("")
    P("(1c) one (c,k) for all six builds, least squares on relative score error")
    for key in ("ms", "whole"):
        pv = {b: vec(b, key) for b in FIT}
        for bounded in (True, False):
            def obj(x):
                c, k = x
                pen = 0.0
                if bounded and not (0.30 <= c <= 0.471):
                    pen = 1e3 * (min(abs(c - 0.30), abs(c - 0.471)) + 1e-3)
                if c <= 0.01 or k < 0:
                    return 1e9
                return pen + sum((score(c, [k * x for x in pv[b]]) / SCORES[b] - 1) ** 2 for b in FIT)
            best = None
            for c0 in (0.32, 0.40, 0.46):
                for k0 in (0.5, 2.0, 5.0):
                    x, v = minimise(obj, [c0, k0], [0.03, 0.5])
                    if best is None or v < best[1]:
                        best = (x, v)
            (c, k), v = best
            pred = {b: score(c, [k * x for x in pv[b]]) for b in FIT}
            res = [100 * (pred[b] / SCORES[b] - 1) for b in FIT]
            rms = (sum(r * r for r in res) / len(res)) ** 0.5
            P("  p=%-5s c %s: c=%.3f k=%.3f (FITTED)  rms %.2f%%  max |res| %.2f%%" % (
                key, "in [0.30,0.471]" if bounded else "free", c, k, rms, max(abs(r) for r in res)))
            P("     build      " + " ".join("%8s" % b for b in FIT))
            P("     actual     " + " ".join("%8.0f" % SCORES[b] for b in FIT))
            P("     predicted  " + " ".join("%8.0f" % pred[b] for b in FIT))
            P("     resid %    " + " ".join("%+8.2f" % r for r in res))
            ra = sorted(FIT, key=lambda b: -SCORES[b])
            rp = sorted(FIT, key=lambda b: -pred[b])
            P("     actual rank    " + " > ".join(ra))
            P("     predicted rank " + " > ".join(rp))
    P("")
    P("(1d) pairwise: the laptop change against the host change (given), and the largest host change any")
    P("     c>=0.30 could produce from that laptop change with the earlier build's own k (bound, FITTED)")
    for a, b in (("sub9", "sub10"), ("sub10", "sub11m"), ("sub11m", "sub13m"), ("sub11m", "sub16m"),
                 ("sub16m", "sub17t")):
        dl = 100 * (sum(vec(b)) / sum(vec(a)) - 1)
        dh = 100 * (SCORES[b] / SCORES[a] - 1)
        rng = []
        for c in CG:
            k = implied_k(a, c)
            rng.append(100 * (score(c, [k * x for x in vec(b)]) / SCORES[a] - 1))
        P("  %-7s -> %-7s laptop %+6.1f%%  host %+5.1f%%  model predicts %+5.1f%% (c=0.30) .. %+5.1f%% (c=0.471)" % (
            a, b, dl, dh, rng[0], rng[-1]))


if __name__ == "__main__":
    o = []
    main(o)
    print("\n".join(o))
