"""Tasks 3-5: predictions for candidate directions, a discriminating measurement, and what 220K/230K need.

Surviving models (see task2_models.py):
  A  = M14: k, m, e, d  -- streaming writer costs a fixed d ms per single-scenario unit      (FITTED, c ASSUMED)
  B  = M15: k, m, e, r  -- streaming writer costs r ms per 100K rows                          (FITTED, c ASSUMED)
  A16= anchored: k fitted exactly on sub16m, laptop ratios trusted inside the sub16 family,
       sub17t's shortfall is a streaming penalty (so sub17n does not carry it)                (FITTED, c ASSUMED)
  C  = anchored: k fitted exactly on sub17t, no streaming penalty at all; the shortfall of sub17t
       comes from sub17n's own changes (helper thread at creation, branch-free heap)          (FITTED, c ASSUMED)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # needed under python -I
from common import *
import task2_models as t2

CG = [0.36, 0.40, 0.44, 0.471]
TARGETS = [220000.0, 230000.0]


def model_scales(c):
    """Returns {model: (host ms per laptop ms for a non-streaming new-engine build, theta or None)}."""
    thA = t2.fit(["k", "m", "e", "d"], c)
    thB = t2.fit(["k", "m", "e", "r"], c)
    k16 = t2.implied_k("sub16m", c)
    k17 = t2.implied_k("sub17t", c)
    return {"A": (thA["k"] * thA["e"], thA), "B": (thB["k"] * thB["e"], thB), "A16": (k16, None), "C": (k17, None)}


def main(out):
    P = out.append
    p = vec("sub17n", "ms")
    sim = vec("sub17n", "sim")
    o = vec("sub17n", "out")
    dirs = [("(a) sub17n as built", lambda s: [s * x for x in p])]
    for f in (0.10, 0.20, 0.30, 0.50):
        dirs.append(("(b) sim -%d%%" % round(100 * f), lambda s, f=f: [s * (p[i] - f * sim[i]) for i in range(NU)]))
    dirs.append(("(c) out -> 0, writer not streaming", lambda s: [s * (p[i] - o[i]) for i in range(NU)]))
    for dl in (1.0, 3.0, 5.0):
        dirs.append(("(d) -%d ms host per unit" % dl, lambda s, dl=dl: [max(s * x - dl, 0.0) for x in p]))
    dirs.append(("(b+c) sim -30%, out -> 0", lambda s: [s * (p[i] - 0.3 * sim[i] - o[i]) for i in range(NU)]))

    P("== TASK 3: predicted scores (thousands). Every cell = FITTED model at an ASSUMED c ==")
    P("   Base is sub17n's laptop file (sum %.0f ms: sim %.0f, out %.0f; batch units split 75/25, ASSUMED)." % (
        sum(p), sum(sim), sum(o)))
    P("   '(d)' subtracts host milliseconds, not laptop milliseconds.")
    scales = {c: model_scales(c) for c in CG}
    hdr = "%-36s" % "direction" + "".join(" | " + " ".join("%s@%.2f" % (m, c) for c in CG) for m in ("A", "B", "A16", "C"))
    P("%-36s | %-27s | %-27s | %-27s | %-27s" % ("direction  (columns: c=0.36 0.40 0.44 0.471)",
                                                 "A  fixed/unit stream cost", "B  per-row stream cost",
                                                 "A16 anchored on sub16m", "C  no stream cost"))
    table = {}
    for name, fn in dirs:
        row = "%-36s" % name
        for m in ("A", "B", "A16", "C"):
            cells = []
            for c in CG:
                v = score(c, fn(scales[c][m][0]))
                table[(name, m, c)] = v
                cells.append("%6.1f" % (v / 1000))
            row += " | " + " ".join(cells)
        P(row)
    P("")
    P("   host ms per laptop ms used above (FITTED): " + "; ".join(
        "%s: " % m + " ".join("%.2f" % scales[c][m][0] for c in CG) for m in ("A", "B", "A16", "C")))
    P("   streaming penalty (FITTED): A d = " + " ".join("%.1f" % scales[c]["A"][1]["d"] for c in CG) +
      " ms/unit; B r = " + " ".join("%.1f" % scales[c]["B"][1]["r"] for c in CG) + " ms per 100K rows")
    P("   laptop caveat: a second laptop round of one binary moved the sum by 3-13%; a 10% error in sub17n's")
    lo = [score(c, [scales[c]["A16"][0] * 1.1 * x for x in p]) for c in CG]
    hi = [score(c, [scales[c]["A16"][0] * 0.9 * x for x in p]) for c in CG]
    P("   laptop total moves row (a), A16, to " + " ".join("%.1f..%.1f" % (a / 1000, b / 1000) for a, b in zip(lo, hi)))
    P("")
    P("   streaming builds under A and B (penalty kept): sub17t refit check and sub18t prediction")
    for b in ("sub17t", "sub18t"):
        row = "   %-8s" % b
        for m in ("A", "B"):
            cells = []
            for c in CG:
                th = scales[c][m][1]
                cells.append("%6.1f" % (score(c, t2.host_ms(b, th, feat=FEAT["sub17t"])) / 1000))
            row += " | %s: " % m + " ".join(cells)
        P(row + ("   (actual 199.3)" if b == "sub17t" else ""))
    P("")

    P("== TASK 4: what would discriminate ==")
    P("(4a) sub17n (pending). Predicted (thousands): " + "; ".join(
        "%s " % m + "..".join("%.1f" % (table[("(a) sub17n as built", m, c)] / 1000) for c in (CG[0], CG[-1]))
        for m in ("A", "B", "A16", "C")))
    P("     Streaming-penalty models put it above sub16m (203.4); model C puts it below sub17t (199.3).")
    P("(4b) calibration upload: sub16m (or the best build) plus a fixed sleep in every unit. Predicted score")
    P("     (thousands) with k FITTED on sub16m at each ASSUMED c:")
    p16 = vec("sub16m")
    for dl in (25.0, 50.0, 100.0):
        cells = []
        for c in CG:
            k = t2.implied_k("sub16m", c)
            cells.append("c=%.3f: %.1f" % (c, score(c, [k * x + dl for x in p16]) / 1000))
        P("     +%3.0f ms: " % dl + "  ".join(cells))
    P("     Spread across c is only ~0.3%: a fixed sleep measures the slope (about -0.4K per ms) but not c.")
    P("(4b') calibration upload that does identify c: the same build doing its process work twice")
    P("     (simulate twice, write once => roughly +sim; or everything twice => 2x). Predicted (thousands):")
    s16 = vec("sub16m", "sim")
    for lab, fn in (("sim twice (+sim)", lambda k: [k * (p16[i] + s16[i]) for i in range(NU)]),
                    ("all twice (2x)  ", lambda k: [2 * k * x for x in p16])):
        cells = []
        for c in CG:
            k = t2.implied_k("sub16m", c)
            cells.append("c=%.3f: %.1f" % (c, score(c, fn(k)) / 1000))
        P("     %s: " % lab + "  ".join(cells))
    P("     Upload noise of 0.1% is about 0.2K, so this separates c to roughly +-0.005 s.")
    P("(4c) per-unit host times of any one build: regress T_u on p_u over 71 units; the intercept is c.")
    P("")

    P("== TASK 5: process-time reduction needed ==")
    P("(5a) from sub16m as scored (203,394): uniform cut of host process time, or equal ms per unit.")
    P("     k FITTED exactly on sub16m; c ASSUMED; independent of the models above.")
    P("%-6s %-9s | %s" % ("c", "ceiling", "  ".join("%.0fK: cut%%  ms/unit  left ms/unit" % (t / 1000) for t in TARGETS)))
    for c in CG:
        k = t2.implied_k("sub16m", c)
        t16 = [k * x for x in p16]
        cells = []
        for tg in TARGETS:
            if NTOT / NU / c <= tg:
                cells.append("%-36s" % "impossible (ceiling below target)")
                continue
            f = bisect(lambda f: score(c, [(1 - f) * x for x in t16]) - tg, 0.0, 1.0)
            d = bisect(lambda d: score(c, [max(x - d, 0.0) for x in t16]) - tg, 0.0, 2000.0)
            cells.append("%5.1f%%  %6.1f  %6.1f              " % (100 * f, d if d is not None else float("nan"),
                                                               (1 - f) * sum(t16) / NU))
        P("%-6.3f %-9.0f | %s" % (c, NTOT / NU / c, "  ".join(cells)))
    P("")
    P("(5b) from sub17n as each model predicts it: further uniform cut of host process time (%).")
    P("%-6s | %s" % ("c", " | ".join("%-3s 220K   230K " % m for m in ("A", "B", "A16", "C"))))
    for c in CG:
        cells = []
        for m in ("A", "B", "A16", "C"):
            s = scales[c][m][0]
            t = [s * x for x in p]
            cc = []
            for tg in TARGETS:
                if NTOT / NU / c <= tg:
                    cc.append("  n/a ")
                elif score(c, t) >= tg:
                    cc.append("  0.0 ")
                else:
                    f = bisect(lambda f: score(c, [(1 - f) * x for x in t]) - tg, 0.0, 1.0)
                    cc.append("%5.1f " % (100 * f))
            cells.append("    " + " ".join(cc))
        P("%-6.3f | %s" % (c, " | ".join(cells)))
    P("")
    P("(5c) same, expressed as the laptop total (ms over 71 units) a non-streaming build must reach,")
    P("     if host time stays proportional to laptop time inside the sub16 family (A16):")
    for c in CG:
        k = t2.implied_k("sub16m", c)
        cc = []
        for tg in TARGETS:
            if NTOT / NU / c <= tg:
                cc.append("%.0fK: n/a" % (tg / 1000))
            else:
                f = bisect(lambda f: score(c, [(1 - f) * k * x for x in p16]) - tg, 0.0, 1.0)
                cc.append("%.0fK: %.0f ms" % (tg / 1000, (1 - f) * sum(p16)))
        P("     c=%.3f  %s   (sub16m %.0f, sub17n %.0f, sub17t %.0f, sub18t %.0f)" % (
            c, "  ".join(cc), sum(p16), sum(p), sum(vec("sub17t")), sum(vec("sub18t"))))


if __name__ == "__main__":
    o = []
    main(o)
    print("\n".join(o))
