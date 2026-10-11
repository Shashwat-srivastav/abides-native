"""Generate every figure of the Zenodo/arXiv report from the project's measurement files.

    python paper/make_figures.py

Inputs (all produced by runs described in REPORT.md):
    lab/bench/all_sub4.json, best_sub5_sub6.json (sub4 to sub6, scenario files, best of 5)
    lab/bench/fig_<tag>_<round>.json (sub9 to sub15, unit directories, written by lab/measure_builds.sh)
Host scores, the board, and the hardware-counter and in-memory timing figures of the last uploads are
written out below as read from the score pages and logs (docs/REPORT.md 9.9).
Numbers that exist only in console logs of those runs (per-phase timings, leaderboard, scores)
are written out below with the section of REPORT.md that records them.
Outputs: paper/figures/figNN_*.png (200 dpi) and .svg
"""
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
J = lambda p: json.load(open(ROOT / p))

# ---- palette (validated categorical order; text never wears a series colour)
SURF, INK, INK2, MUTE, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8983", "#e6e5e0"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"
GRAY = "#c9c8c2"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "xtick.color": INK2, "ytick.color": INK2, "xtick.major.size": 0, "ytick.major.size": 0,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "legend.fontsize": 9,
})


def save(fig, name):
    fig.savefig(OUT / (name + ".png"), dpi=200, bbox_inches="tight")
    fig.savefig(OUT / (name + ".svg"), bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def k(v):
    return "{:,.0f}".format(v)


# ------------------------------------------------------------------ measured data
# Every scored upload under the whole-container rule, in upload order (the second upload of the
# sub4 image, 151,386.96, is left out). The names of the last five are the keys of HOST11.
SCORES = [("sub4", "native engine,\nPython image,\nArrow Parquet", 153825.02),
          ("sub5", "own Parquet\nwriter, static\nlauncher", 181495.89),
          ("sub7", "smaller files,\n2.2 MB scratch\nimage", 184857.72),
          ("sub9", "memory work:\nfewer page\nfaults", 183419.75),
          ("sub10", "no ledger on\nsix units that\nneed none", 188687.15),
          ("sub11", "profile-guided\nbuild, memory\nswitches off", 189018.28),
          ("sub13", "streamed\nfiles, pooled\nthreads", 184046.62),
          ("sub16", "trace built in\nfinal order\nduring the run", 203394.47),
          ("sub17", "branch-free\nheap step,\nhelper started\nearly", 196164.84),
          ("sub17", "the same with\nwriter threads\non", 199285.22),
          ("sub16", "same binary,\nhelper thread\noff", 185818.35),
          ("sub18", "leaner engine,\nhelper thread\noff", 193962.28),
          ("sub19a", "sub18's engine,\nsub16's helper\ncode", 199057.73)]
SCORES_HELPER_OFF = (10, 11)  # positions in SCORES of the two uploads made with the helper thread off
BEST = max(s[2] for s in SCORES)  # sub16
LEADER, SECOND = 231024.24, 222058.17
# The first ten of 50 teams as the board showed them last (screenshot from the
# team; the board keeps each team's best score).
BOARD = [("fuzz", 231024), ("VerityLovityFalsityCruelty", 222058), ("abc123", 221088), ("IMAnonymous", 215963),
         ("Yan Su", 214394), ("recently rejected", 211718), ("Proof of Alpha", 211712), ("Cornfield Chase", 210201),
         ("Warkop PuteraPrakoso", 206152), ("S2WISH (sub16)", 203394)]
N_TEAMS = 50
# Uploads that each differ from another scored build in one setting (or nearly so).
# sub19a is sub18's engine with sub16's helper-thread code restored, helper on.
HOST11 = {"sub16": 203394.47, "sub16_helper_off": 185818.35, "sub17_writer_off": 196164.84,
          "sub17_writer_on": 199285.22, "sub18_helper_off": 193962.28, "sub19a": 199057.73}
# Hardware counters, largest unit (t3-gb-mega-throughput), one thread (T3_LAT_THREAD=0 T3_TRAIL=0),
# perf stat -e cycles:u,instructions:u,branch-misses:u; millions; (low, high) of the runs made.
CNT = {"cycles": {"sub16": (934, 945), "sub17": (787, 863)},
       "instructions": {"sub16": (1395, 1395), "sub17": (1324, 1324)},
       "branch misses": {"sub16": (11.59, 11.59), "sub17": (4.93, 5.12)}}
# Test builds without profile feedback, same unit, in the order the changes of sub18 were made (M instructions)
STEPS18 = [("sub17 engine", 1491.7), ("+ 32-byte\ntrace rows", 1470.2),
           ("+ own-order records for\nmarket makers only, one-row\nbuckets, no record for a\nskipped ledger", 1429.0),
           ("+ wakeup rings, blocked\nqueues as sorted vectors", 1381.5)]
# REPORT.md 7.9: phase timing inside the sub4 image, best of 5 (ms)
PH4 = [("gb_mega_throughput", 1168360, 1230, 5.2, 60.2, 173.7, 234.9, 677.4),
       ("gb_pop_horizon_scale", 725591, 746, 3.2, 20.8, 101.2, 133.4, 416.3),
       ("gb_horizon_240s", 555032, 588, 4.3, 16.4, 83.3, 104.4, 329.5),
       ("gb_highfreq_40hz_60s", 500530, 526, 3.8, 14.1, 70.8, 99.6, 292.6),
       ("mr_cancel_replace_churn", 322007, 336, 4.4, 7.8, 29.3, 50.4, 206.4),
       ("mr_deep_book_state_size", 319488, 362, 3.6, 9.0, 39.2, 52.3, 219.1),
       ("gb_pop_128_agents", 303603, 391, 4.4, 11.3, 56.7, 58.4, 219.8),
       ("mp05_cancel_churn_newest", 240829, 287, 4.2, 5.9, 25.0, 37.7, 180.1),
       ("mr_checkpoint_cadence_fine", 161055, 211, 3.5, 4.1, 14.8, 24.9, 133.2),
       ("st01_liquidity_churn_baseline", 72034, 98, 3.8, 3.8, 7.4, 11.5, 49.0)]
# REPORT.md 7.9 / 9.5: whole-process time, best of 5 (ms)
T456 = {"gb_mega_throughput": (1230, 530, 485), "gb_pop_horizon_scale": (746, 318, 290), "gb_horizon_240s": (588, 232, 209),
        "gb_highfreq_40hz_60s": (526, 217, 194), "mr_cancel_replace_churn": (336, 117, 97),
        "mr_deep_book_state_size": (362, 102, 100), "gb_pop_128_agents": (391, 130, 124),
        "mp05_cancel_churn_newest": (287, 77, 77), "mr_checkpoint_cadence_fine": (211, 57, 51),
        "st01_liquidity_churn_baseline": (98, 30, 30)}
FIT_OVERHEAD, FIT_K = 0.551, 0.50  # two-score fit, REPORT.md 9.5

a4 = J("lab/bench/all_sub4.json")
# sub9 and later: lab/measure_builds.sh, each build in the memory mode it was shipped in (sub9 and
# sub10 with huge pages and pre-population, sub11 and later without). Best run per unit over the rounds.
LATER = ["sub9", "sub10", "sub11", "sub13", "sub14", "sub15"]


def later_data(tag):
    runs = [json.load(open(f)) for f in sorted((ROOT / "lab" / "bench").glob("fig_%s_*.json" % tag))]
    return {u: min((r[u] for r in runs if u in r), key=lambda x: x["ms"]) for u in runs[0]}


NEW = {t: later_data(t) for t in LATER}
unit_dir = lambda scenario: "t3-" + scenario.replace("_", "-")
b56 = J("lab/bench/best_sub5_sub6.json")
N = b56["n_events"]
s4 = {u: a4[u]["best_s"] for u in a4}
s5, s6 = b56["best_s"]["sub5"], b56["best_s"]["sub6"]

# ------------------------------------------------------------------ fig 1: scores under the new rule
fig, ax = plt.subplots(figsize=(13.6, 4.6))
xs = list(range(len(SCORES)))
ys = [s[2] for s in SCORES]
i_best = ys.index(BEST)
ax.plot(xs, ys, color=GRAY, lw=1.6, zorder=2)
cols = [ORANGE if i in SCORES_HELPER_OFF else BLUE for i in xs]
ax.scatter(xs, ys, s=74, color=cols, edgecolor=SURF, linewidth=1.5, zorder=4)
for i, v in enumerate(ys):  # labels of the uploads after the best one go below, clear of its line
    ax.text(i, v + (3000 if i <= i_best else -3000), k(v), ha="center", va="bottom" if i <= i_best else "top",
            fontsize=9.6, fontweight="bold")
ax.axhline(LEADER, color=INK2, lw=1.2, ls=(0, (4, 3)), zorder=1)
ax.text(len(SCORES) - 0.52, LEADER + 1500, "leader of the board: " + k(LEADER), ha="right", va="bottom", fontsize=9, color=INK2)
ax.plot([i_best, len(SCORES) - 0.4], [BEST, BEST], color=BLUE, lw=1.0, ls=(0, (4, 3)), zorder=1)
ax.text(len(SCORES) - 0.52, BEST + 1500, "our best (sub16): no later upload passed it", ha="right", va="bottom", fontsize=9, color=INK2)
ax.set_xticks(xs)
ax.set_xticklabels([name + "\n" + what for name, what, _ in SCORES], fontsize=7.0, linespacing=1.25)
ax.set_ylim(145000, 240000)
ax.set_xlim(-0.6, len(SCORES) - 0.4)
ax.yaxis.set_major_formatter(lambda v, _: k(v))
ax.set_ylabel("Development score (events per container-second;\nthe axis does not start at zero)")
ax.set_title("Every scored upload under the whole-container-time rule, in upload order")
handles = [plt.Line2D([], [], marker="o", ls="", color=BLUE, markersize=7), plt.Line2D([], [], marker="o", ls="", color=ORANGE, markersize=7)]
ax.legend(handles, ["build as shipped", "uploaded with the latency helper thread switched off, to measure it"], loc="upper left",
          bbox_to_anchor=(0.0, 0.93))
ax.grid(axis="x", visible=False)
save(fig, "fig01_scores")

# ------------------------------------------------------------------ fig 2: leaderboard
fig, ax = plt.subplots(figsize=(7.6, 4.6))
names = [b[0] for b in BOARD][::-1]
vals = [b[1] for b in BOARD][::-1]
cols = [BLUE if n.startswith("S2WISH") else GRAY for n in names]
ax.barh(range(len(names)), vals, height=0.62, color=cols, zorder=3)
for i, v in enumerate(vals):
    ax.text(v + 2500, i, k(v), va="center", fontsize=8.5, color=INK if cols[i] == BLUE else INK2,
            fontweight="bold" if cols[i] == BLUE else "normal")
ax.text(4000, 0, "rank %d of %d: %.1f%% below the leader, %.1f%% below rank %d"
        % (len(BOARD), N_TEAMS, 100.0 * (1.0 - vals[0] / vals[-1]), 100.0 * (1.0 - vals[0] / vals[1]), len(BOARD) - 1),
        va="center", fontsize=8.2, color=SURF, zorder=4)
ax.set_yticks(range(len(names)))
ax.set_yticklabels(names, fontsize=9)
ax.set_xlim(0, 262000)
ax.xaxis.set_major_formatter(lambda v, _: k(v))
ax.set_xlabel("Development score")
ax.set_title("Track 3 Development board at its last reading (first ten of %d teams)" % N_TEAMS)
ax.grid(axis="y", visible=False)
save(fig, "fig02_leaderboard")

# ------------------------------------------------------------------ fig 3: where the time went in sub4
# Process time with the inputs on an in-memory mount (lab/true_p.py, best of 5, all 71 units). Per unit:
# "ms" = sum of the launcher's phases, "sim" = event loop, "out" = files encoded, hashed and written.
# Sessions as in docs/REPORT.md 9.9.3; only ratios within one session mean anything.
TP = lambda name: J("lab/bench/truep_%s.json" % name)
T18 = TP("sub18")
fig, (ax, axb) = plt.subplots(1, 2, figsize=(11.8, 4.9), sharey=True, gridspec_kw={"width_ratios": [1.5, 1.0]})
labels = ["Parquet write (Arrow)", "output assembly", "event loop", "engine creation", "parse (3 to 5 ms)", "start, library load, exit"]
colors = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN]
rows = PH4[::-1]
left = [0.0] * len(rows)
for li, lab in enumerate(labels):
    vals = []
    for (_, _, total, parse, create, sim, fin, wr) in rows:
        other = total - (parse + create + sim + fin + wr)
        vals.append([wr, fin, sim, create, parse, other][li])
    ax.barh(range(len(rows)), vals, left=left, height=0.62, color=colors[li], label=lab, edgecolor=SURF, linewidth=1.2, zorder=3)
    left = [a + b for a, b in zip(left, vals)]
for i, r in enumerate(rows):
    ax.text(r[2] + 12, i, "%d ms  (write %d%%, loop %d%%)" % (r[2], round(100 * r[7] / r[2]), round(100 * r[5] / r[2])),
            va="center", fontsize=8.2, color=INK2)
ax.set_yticks(range(len(rows)))
ax.set_yticklabels(["%s\n%s events" % (r[0], k(r[1])) for r in rows], fontsize=7.8, linespacing=1.1)
ax.set_xlim(0, 1850)
ax.set_xlabel("whole-process time, laptop, best of 5 runs (ms)")
ax.set_title("sub4: the Parquet write is the largest part", fontsize=11)
ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.45, -0.14), columnspacing=1.2, handlelength=1.2)
ax.grid(axis="y", visible=False)
left = [0.0] * len(rows)
for lab, col, get in [("files encoded, hashed and written (own writer)", BLUE, lambda d: d["out"]),
                      ("event loop", AQUA, lambda d: d["sim"]),
                      ("parse and engine creation", YELLOW, lambda d: d["ms"] - d["out"] - d["sim"])]:
    vals = [get(T18[unit_dir(r[0])]) for r in rows]
    axb.barh(range(len(rows)), vals, left=left, height=0.62, color=col, label=lab, edgecolor=SURF, linewidth=1.2, zorder=3)
    left = [a + b for a, b in zip(left, vals)]
for i, r in enumerate(rows):
    d = T18[unit_dir(r[0])]
    axb.text(d["ms"] + 5, i, "%d ms  (files %d%%, loop %d%%)" % (round(d["ms"]), round(100 * d["out"] / d["ms"]), round(100 * d["sim"] / d["ms"])),
             va="center", fontsize=8.2, color=INK2)
axb.set_xlim(0, 430)
axb.set_xlabel("sum of the launcher's phases, laptop, inputs in memory,\nbest of 5 runs (ms); the scale differs from the left panel")
axb.set_title("sub18, same units: the event loop is the largest part", fontsize=11)
axb.legend(ncol=1, loc="upper center", bbox_to_anchor=(0.5, -0.2), handlelength=1.2)
axb.grid(axis="y", visible=False)
fig.tight_layout(w_pad=1.5)
save(fig, "fig03_sub4_phases")

# ------------------------------------------------------------------ fig 4: process time per unit, four versions
# Left: whole-process time, inputs read from the unit folders (includes the laptop's input mount).
# Right: sum of the launcher's phases, inputs in memory, three builds measured in one session
# (truep_sub16_b.json, truep_sub17n_b.json, truep_sub18.json). The two panels are different measurements.
fig, (ax, axb) = plt.subplots(1, 2, figsize=(11.8, 4.7), sharey=True, gridspec_kw={"width_ratios": [1.35, 1.0]})
units = list(T456)[::-1]
SES_C = [("sub16", TP("sub16_b"), YELLOW), ("sub17", TP("sub17n_b"), GREEN), ("sub18", T18, INK2)]
for i, u in enumerate(units):
    vs = [d[unit_dir(u)]["ms"] for _, d, _ in SES_C]
    axb.plot([min(vs), max(vs)], [i, i], color=GRID, lw=2.2, zorder=2)
    for n, (lab, _, col) in enumerate(SES_C):
        axb.scatter([vs[n]], [i], s=58, color=col, zorder=4 + n, edgecolor=SURF, linewidth=1.5, label=lab if i == 0 else None)
    axb.text(max(vs) + 9, i, "%d → %d → %d ms" % tuple(round(v) for v in vs), va="center", fontsize=8.0, color=INK2)
axb.set_xlim(0, 480)
axb.set_xlabel("sum of the launcher's phases, inputs in memory,\nbest of 5 (ms); helper thread on, writer threads off;\nthe scale differs from the left panel")
axb.set_title("sub16, sub17, sub18: one later session", fontsize=11)
axb.legend(loc="lower right", ncol=3, handletextpad=0.3, columnspacing=1.0)
axb.grid(axis="y", visible=False)
for i, u in enumerate(units):
    a, b, _ = T456[u]
    c, d = NEW["sub11"][unit_dir(u)]["ms"], NEW["sub15"][unit_dir(u)]["ms"]
    ax.plot([min(a, b, c, d), a], [i, i], color=GRID, lw=2.2, zorder=2)
    for v, col, lab, z in ((a, ORANGE, "sub4", 4), (b, BLUE, "sub5", 4), (c, AQUA, "sub11", 5), (d, MAGENTA, "sub15", 6)):
        ax.scatter([v], [i], s=58, color=col, zorder=z, edgecolor=SURF, linewidth=1.5, label=lab if i == 0 else None)
    ax.text(a + 22, i, "%d → %d → %d → %d ms" % (a, b, round(c), round(d)), va="center", fontsize=8.0, color=INK2)
ax.set_yticks(range(len(units)))
ax.set_yticklabels(units, fontsize=8.2)
ax.set_xlim(0, 1800)
ax.set_xlabel("whole-process time, inputs from the unit folders, warm, best run (ms)")
ax.set_title("sub4, sub5, sub11, sub15: whole process on the laptop", fontsize=11)
ax.legend(loc="lower right", ncol=4, handletextpad=0.3, columnspacing=1.0)
ax.grid(axis="y", visible=False)
fig.tight_layout(w_pad=1.5)
save(fig, "fig04_per_unit_time")

# ------------------------------------------------------------------ fig 5: total process time and output size, sub4 to sub15
tags5 = ["sub4", "sub5", "sub6"] + LATER
time5 = [sum(s4.values()), sum(s5.values()), sum(s6.values())] + [sum(v["ms"] for v in NEW[t].values()) / 1e3 for t in LATER]
size5 = [289.2, 758.7, 135.8] + [sum(v["out_bytes"] for v in NEW[t].values()) / 1e6 for t in LATER]
# Sums of single benchmark rounds (s), the spread behind each bar: sub4 has one round, sub5 and sub6
# three (REPORT.md 7.9), sub9 and later the two rounds of lab/measure_builds.sh.
round5 = [[sum(s4.values())], [3.871, 3.638, 4.126], [5.650, 3.570, 3.583]] + [
    [sum(v["ms"] for v in json.load(open(f)).values()) / 1e3 for f in sorted((ROOT / "lab" / "bench").glob("fig_%s_*.json" % t))]
    for t in LATER]
top5 = [max(r) for r in round5]
# Inputs in memory, all 71 units, sum of the launcher's phases (REPORT.md 9.9.3). One group per session.
MEM5 = [("session B\n(older binaries)", GRAY, [("sub9", "sub9s"), ("sub10", "sub10s"), ("sub11", "sub11m"), ("sub13", "sub13m")]),
        ("session A", BLUE, [("sub16", "sub16"), ("sub17\nwriter off", "sub17n"), ("sub17\nwriter on", "sub17t")]),
        ("session C\n(later, slower)", AQUA, [("sub16", "sub16_b"), ("sub17\nwriter off", "sub17n_b"), ("sub18", "sub18")])]
fig, axes = plt.subplots(3, 1, figsize=(7.6, 8.6))
for ax, title, unit, vals, tops, fmt in [
        (axes[0], "Whole-process time, 65 units, inputs from the unit folders (laptop, warm)", "seconds", time5, top5, "%.2f"),
        (axes[2], "Output size, 65 units (not recorded for sub16 and later)", "MB (Parquet files written)", size5, size5, "%.0f")]:
    ax.bar(range(len(vals)), vals, width=0.56, color=BLUE, zorder=3)
    for i, v in enumerate(vals):
        if tops is top5:  # the round sums are drawn above the bar, so its value goes inside
            ax.text(i, v - 0.3, fmt % v, ha="center", va="top", fontsize=9, fontweight="bold", color=SURF, zorder=6)
        else:
            ax.text(i, v + max(vals) * 0.025, fmt % v, ha="center", fontsize=9, fontweight="bold")
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(tags5)
    ax.set_ylim(0, max(vals) * 1.16)
    ax.set_ylabel(unit)
    ax.set_title(title, fontsize=11)
    ax.grid(axis="x", visible=False)
for i, r in enumerate(round5):
    if len(r) > 1:
        axes[0].plot([i, i], [min(r), max(r)], color=INK, lw=1.3, zorder=5)
        axes[0].scatter([i] * len(r), r, s=14, color=INK, zorder=6)
axes[0].text(8.4, 11.3, "bar: sum of each unit's best run; dots: sum of each single round\n"
             "(sub6: one round of three 58% slower; sub10: two rounds 14% apart)",
             ha="right", va="top", fontsize=8.4, color=INK2, linespacing=1.3)
ax, x, ticks = axes[1], 0.0, []
for ses, col, builds in MEM5:
    x0 = x
    for lab, name in builds:
        v = sum(u["ms"] for u in TP(name).values()) / 1e3
        ax.bar(x, v, width=0.56, color=col, zorder=3)
        ax.text(x, v + 0.06, "%.2f" % v, ha="center", fontsize=9, fontweight="bold")
        ticks.append((x, lab))
        x += 1.0
    ax.text((x0 + x - 1.0) / 2.0, 2.98, ses, ha="center", va="top", fontsize=8.4, color=INK2, linespacing=1.2)
    if ses != MEM5[-1][0]:
        ax.axvline(x - 0.2, color=GRID, lw=1.2, zorder=1)
    x += 0.6
ax.set_xticks([t[0] for t in ticks])
ax.set_xticklabels([t[1] for t in ticks], fontsize=8.2, linespacing=1.15)
ax.set_ylim(0, 3.05)
ax.set_ylabel("seconds")
ax.set_title("Sum of launcher phases, 71 units, inputs in memory: compare within a session only", fontsize=11)
ax.grid(axis="x", visible=False)
fig.tight_layout(h_pad=2.0)
save(fig, "fig05_totals")

# ------------------------------------------------------------------ fig 6: the container-time budget per unit (fitted model)
# Events of every public unit, 65 single and 6 batch (lab/true_p.py on sub16; the count is the same for every build).
N71 = {u: v["n_events"] for u, v in J("lab/bench/truep_sub16.json").items()}
MEAN71 = sum(N71.values()) / len(N71)  # a container that did no work would score MEAN71 / fixed cost
BOUND71 = MEAN71 / LEADER              # so the leader's score bounds the fixed cost (s)
fig, ax = plt.subplots(figsize=(7.6, 4.4))
sel = sorted(N, key=lambda u: -N[u])
pick = sel[:6] + [sel[len(sel) // 2 - 1], sel[len(sel) // 2], sel[-2], sel[-1]]
pick = pick[::-1]
fixed = [FIT_OVERHEAD * 1e3] * len(pick)
proc4 = [FIT_K * s4[u] * 1e3 for u in pick]
proc5 = [FIT_K * s5[u] * 1e3 for u in pick]
ax.barh(range(len(pick)), fixed, height=0.62, color=GRAY, label="fixed container cost as fitted (0.551 s): above the bound, so wrong", edgecolor=SURF, linewidth=1.2, zorder=3)
ax.barh(range(len(pick)), proc5, left=fixed, height=0.62, color=BLUE, label="our process, sub5, at the fitted 0.5 × laptop time", edgecolor=SURF, linewidth=1.2, zorder=3)
ax.barh(range(len(pick)), [a - b for a, b in zip(proc4, proc5)], left=[f + p for f, p in zip(fixed, proc5)], height=0.62,
        color=ORANGE, label="additional process time in sub4, same factor", edgecolor=SURF, linewidth=1.2, zorder=3)
for i, u in enumerate(pick):
    ax.text(fixed[i] + proc4[i] + 14, i, "%s events" % k(N[u]), va="center", fontsize=8.2, color=INK2)
# what refuted the fit: the whole roster's mean events per unit over the leader's score bounds the fixed cost
ax.axvline(BOUND71 * 1e3, color=INK, lw=1.3, ls=(0, (4, 3)), zorder=4, label="largest fixed cost the leader's score allows (%.3f s)" % BOUND71)
ax.text(1480, 1.5, "REFUTED\n\nThe fitted fixed cost is larger than any\nfixed cost the leader's score allows, and\nno later score fits a factor of 0.5.\nKept as the record of the first reading.",
        fontsize=8.2, color=INK, ha="right", va="center", linespacing=1.35, zorder=6,
        bbox=dict(boxstyle="round,pad=0.5", fc=SURF, ec=INK, lw=1.0))
ax.set_yticks(range(len(pick)))
ax.set_yticklabels(pick, fontsize=8.2)
ax.set_xlim(0, 1500)
ax.set_xlabel("container time per unit under the refuted fit (ms)")
ax.set_title("REFUTED fit of sub4 and sub5: modelled container time per unit")
ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.15), ncol=1, handlelength=1.6)
ax.grid(axis="y", visible=False)
save(fig, "fig06_budget")

# ------------------------------------------------------------------ fig 7: concentration of events across units
fig, ax = plt.subplots(figsize=(7.6, 3.8))
ev = sorted(N71.values(), reverse=True)  # the whole Development roster, batch units included
tot = sum(ev)
cum, run = [], 0
for v in ev:
    run += v
    cum.append(100 * run / tot)
ax.plot(range(1, len(ev) + 1), cum, color=BLUE, lw=2, zorder=3)
ax.scatter([8], [cum[7]], s=64, color=BLUE, edgecolor=SURF, linewidth=2, zorder=4)
ax.annotate("the 8 largest units hold %.1f%% of all events" % cum[7], xy=(8, cum[7]), xytext=(15, cum[7] - 16),
            fontsize=9.5, color=INK, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax.set_xlim(0, len(ev) + 1)
ax.set_ylim(0, 104)
ax.set_xlabel("public units (65 single-scenario and 6 batch), largest first")
ax.set_ylabel("cumulative share of events (%)")
ax.set_title("Events are concentrated in a few units (%s events over %d units)" % (k(tot), len(ev)))
save(fig, "fig07_concentration")

# ------------------------------------------------------------------ fig 8: score model and ceiling
# Left: the first fit, as made (two scores, the 65 single units only), against the bound that refutes it.
# Right: the best single (c, k) over six later builds, lab/agent220/model/results.txt (1c), p = process
# time with the inputs in memory: c = 0.471 s, k = 1.375, rms 3.23%, largest residual 6.29%.
RESID8 = [("sub9", 2.51), ("sub10", 1.23), ("sub11", -1.21), ("sub13", 3.68), ("sub16", -6.29),
          ("sub17,\nwriter\nthreads on", -0.50)]
fig, (ax, axr) = plt.subplots(1, 2, figsize=(11.6, 4.3), gridspec_kw={"width_ratios": [1.45, 1]})
ohs = [0.30 + 0.01 * i for i in range(46)]
score = lambda t, oh, kk: sum(N[u] / (oh + kk * t[u]) for u in N) / len(N)
ax.axvspan(BOUND71, 0.75, color=GRAY, alpha=0.38, lw=0, zorder=0)
ax.plot(ohs, [score(s4, o, FIT_K) for o in ohs], color=ORANGE, lw=2, label="fit through sub4's score", zorder=3)
ax.plot(ohs, [score(s5, o, FIT_K) for o in ohs], color=BLUE, lw=2, label="fit through sub5's score", zorder=3)
ax.plot(ohs, [MEAN71 / o for o in ohs], color=INK2, lw=1.4, ls=(0, (4, 3)), label="zero process time, 71 units (ceiling)", zorder=3)
ax.axvline(FIT_OVERHEAD, color=INK2, lw=0.9, ls=(0, (1, 2)), zorder=2)
for v, lab, col, ty in [(153825, "sub4 scored 153,825", ORANGE, 112000), (181496, "sub5 scored 181,496", BLUE, 128000)]:
    ax.scatter([FIT_OVERHEAD], [v], s=64, color=col, edgecolor=SURF, linewidth=2, zorder=5)
    ax.annotate(lab, xy=(FIT_OVERHEAD, v), xytext=(0.315, ty), fontsize=8.6, color=INK, va="center",
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.7, shrinkB=5, relpos=(1.0, 0.5)), zorder=6)
ax.axhline(LEADER, color=INK, lw=0.9, zorder=2)
ax.text(0.745, LEADER + 3500, "leader 231,024", fontsize=8.6, color=INK, ha="right")
ax.scatter([BOUND71], [LEADER], s=30, color=INK, zorder=6)
ax.text(BOUND71 + 0.008, 345000, "excluded: here even a container that\ndid no work scores below the leader\n(fixed cost above %.3f s)" % BOUND71,
        fontsize=8.4, color=INK, ha="left", va="top", linespacing=1.3)
ax.text(FIT_OVERHEAD + 0.008, 290000, "fitted 0.551 s:\nin the excluded range", fontsize=8.4, color=INK, ha="left", va="top", linespacing=1.3)
ax.set_xlim(0.30, 0.75)
ax.set_ylim(100000, 360000)
ax.yaxis.set_major_formatter(lambda v, _: k(v))
ax.set_xlabel("fixed container cost per unit, c (s)")
ax.set_ylabel("modelled score")
ax.set_title("REFUTED first fit: two scores, c = 0.551 s, k = 0.50", fontsize=11)
ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.17), ncol=3, fontsize=8.4, handlelength=1.6, columnspacing=1.2)

axr.bar(range(len(RESID8)), [r for _, r in RESID8], width=0.56, color=BLUE, zorder=3)
for i, (_, r) in enumerate(RESID8):
    axr.text(i, r + (0.3 if r > 0 else -0.3), "%+.1f" % r, ha="center", va="bottom" if r > 0 else "top", fontsize=9.5, fontweight="bold")
axr.axhline(0, color=INK2, lw=0.9, zorder=4)
axr.set_xticks(range(len(RESID8)))
axr.set_xticklabels([b for b, _ in RESID8], fontsize=8.4)
axr.set_ylim(-12.4, 5.6)
axr.set_ylabel("modelled minus actual score (%)")
axr.set_title("One (c, k) for six later builds does not fit either", fontsize=11)
axr.text(0.03, 0.04, "best single fit: c = 0.471 s, k = 1.375\nrms error 3.2%, largest 6.3%;\nthe order of the builds is not reproduced",
         transform=axr.transAxes, fontsize=8.4, color=INK, va="bottom", linespacing=1.3)
axr.grid(axis="x", visible=False)
fig.tight_layout(w_pad=2.4)
fig.suptitle("score = events ÷ (c + k × laptop process time): no single pair (c, k) describes the scored builds",
             x=0.012, y=1.035, ha="left", fontsize=12, fontweight="bold")
save(fig, "fig08_model")

# ------------------------------------------------------------------ fig 9: engine cost per event (CPU counters)
# REPORT.md 7.7: mean over the 65 scenarios, counters read around the simulation call (minimum of 5 repetitions).
# (step, cycles per event drawn, its label, instructions per event). Step C with the helper thread
# switched off: 470 cycles per event; its instruction count in that mode was not recorded.
steps = [("sub3\nengine", 559, "557–561", 1010), ("A", 455, "445–464", 773), ("B", 437, "437", 761), ("C\n(sub4)", 352, "352", 576)]
C_THREAD_OFF = 470
fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.9))
for ax, col, title, unit in [(axes[0], 1, "Cycles per trace event: −37%", "CPU cycles per trace event"),
                             (axes[1], 3, "Instructions per trace event: −43%", "instructions per trace event")]:
    vals = [s[col] for s in steps]
    ax.bar(range(4), vals, width=0.52, color=BLUE, zorder=3)
    for i, s in enumerate(steps):
        ax.text(i, vals[i] + max(vals) * 0.02, s[2] if col == 1 else k(s[3]), ha="center", fontsize=9.5, fontweight="bold")
    ax.set_xticks(range(4))
    ax.set_xticklabels([s[0] for s in steps], fontsize=8.8)
    ax.set_ylim(0, max(vals) * 1.17)
    ax.yaxis.set_major_formatter(lambda v, _: k(v))
    ax.set_ylabel(unit)
    ax.set_title(title, fontsize=11)
    ax.grid(axis="x", visible=False)
axes[0].plot([3 - 0.26, 3 + 0.26], [C_THREAD_OFF, C_THREAD_OFF], color=INK, lw=1.4, ls=(0, (3, 2)), zorder=5)
axes[0].text(3, C_THREAD_OFF + 12, "%d with the\nhelper thread off" % C_THREAD_OFF, ha="center", va="bottom", fontsize=7.8, color=INK2, linespacing=1.15)
fig.text(0.5, 0.0, "A: compact records, split heaps      B: per-agent blocked queues      C: latency draws on a helper thread",
         ha="center", va="bottom", fontsize=8.6, color=INK2)
fig.suptitle("Engine rewrite from sub3 to sub4, mean over the 65 scenarios, outputs unchanged", x=0.012, ha="left", fontsize=12, fontweight="bold")
fig.tight_layout(w_pad=2.4, rect=(0, 0.05, 1, 0.95))
save(fig, "fig09_cycles")

# ------------------------------------------------------------------ fig 10: page faults and peak memory, sub9 to sub15
BIG = "t3-gb-mega-throughput"
fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.6))
for ax, title, unit, vals in [
        (axes[0], "Page faults, 65 units", "thousand minor faults", [sum(v["minflt"] for v in NEW[t].values()) / 1e3 for t in LATER]),
        (axes[1], "Peak memory, largest unit", "MB resident (gb_mega_throughput)", [NEW[t][BIG]["maxrss_mb"] for t in LATER])]:
    cols = [BLUE if t in ("sub9", "sub10") else AQUA for t in LATER]
    ax.bar(range(len(vals)), vals, width=0.56, color=cols, zorder=3)
    for i, v in enumerate(vals):
        ax.text(i, v + max(vals) * 0.025, "%.0f" % v, ha="center", fontsize=9.5, fontweight="bold")
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(LATER, fontsize=8.6)
    ax.set_ylim(0, max(vals) * 1.18)
    ax.set_ylabel(unit)
    ax.set_title(title, fontsize=11)
    ax.grid(axis="x", visible=False)
handles = [plt.Rectangle((0, 0), 1, 1, color=BLUE), plt.Rectangle((0, 0), 1, 1, color=AQUA)]
fig.legend(handles, ["run with huge pages and pre-populated buffers", "run with both switched off"],
           loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.04))
fig.suptitle("sub9 to sub15, laptop counts; the totals were not recorded for sub16 and later",
             x=0.012, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout(w_pad=3, rect=(0, 0.06, 1, 0.95))
save(fig, "fig10_memory")

# ------------------------------------------------------------------ fig 11: fuzz corpus coverage
# Replay of the stored corpus in the full image of each build (native/fuzz/recheck_stored.py), last lines of
# lab/bench/fuzz_sub6.log, fuzz_sub7.log, validate_sub<N>.log and val_sub17/fuzz.log:
# (build, handled by the launcher, handed to the Python path, handed on to the reference path, cases reached).
# Every case of a completed replay reproduces the recorded reference hashes.
FUZZ_N = 1318
rows11 = [("sub6", 358, 960, 0, 1318), ("sub7", 1295, 23, 0, 1318), ("sub8", 1295, 23, 0, 1318), ("sub9", 1296, 22, 0, 1318),
          ("sub10", 1295, 23, 0, 1318), ("sub11", 1295, 23, 0, 1318), ("sub12", 1295, 23, 0, 1318), ("sub13", 1295, 23, 0, 1318),
          ("sub14", 1266, 23, 29, 1318), ("sub15", 0, 0, 0, 400), ("sub16", 1296, 22, 0, 1318), ("sub17", 1293, 25, 0, 1318),
          ("sub18", 1291, 27, 0, 1318), ("sub19a", 1296, 22, 0, 1318)]
STOPPED11 = {"sub15": "stopped at 400 of 1,318: replay interrupted,\nbuild never uploaded"}
fig, ax = plt.subplots(figsize=(7.6, 5.4))
for i, (lab, own, handed, ref, reached) in enumerate(rows11):
    if reached < FUZZ_N:  # no breakdown was printed: draw only how far the replay got
        ax.barh(i, reached, height=0.56, color=SURF, edgecolor=INK2, linewidth=1.0, hatch="////", zorder=3)
        ax.text(reached + 16, i, STOPPED11[lab], va="center", color=INK, fontsize=7.6, linespacing=1.2,
                fontweight="bold" if lab == "sub16" else "normal", zorder=5)
        continue
    ax.barh(i, own, height=0.56, color=BLUE, edgecolor=SURF, linewidth=1.2, zorder=3)
    ax.barh(i, handed, left=own, height=0.56, color=GRAY, edgecolor=SURF, linewidth=1.2, zorder=3)
    ax.barh(i, ref, left=own + handed, height=0.56, color=ORANGE, edgecolor=SURF, linewidth=1.2, zorder=3)
    ax.text(own / 2, i, k(own), ha="center", va="center", color="white", fontsize=9, fontweight="bold")
    if handed > 80:
        ax.text(own + handed / 2, i, k(handed), ha="center", va="center", color=INK, fontsize=9)
    else:
        ax.text(FUZZ_N + 14, i, "%d + %d" % (handed, ref) if ref else k(handed), va="center", color=INK, fontsize=9,
                fontweight="bold" if ref else "normal")
ax.text(FUZZ_N + 14, 0, "handed\nover:", va="center", color=INK2, fontsize=8, linespacing=1.15)
handles = [plt.Rectangle((0, 0), 1, 1, color=BLUE), plt.Rectangle((0, 0), 1, 1, color=GRAY), plt.Rectangle((0, 0), 1, 1, color=ORANGE),
           plt.Rectangle((0, 0), 1, 1, fc=SURF, ec=INK2, hatch="////", lw=1.0)]
ax.legend(handles, ["handled by the launcher", "handed to the Python path", "handed on to the reference path (sub14)",
                    "replay not completed: cases reached"], loc="upper center", bbox_to_anchor=(0.46, -0.13), ncol=2)
ax.set_yticks(range(len(rows11)))
ax.set_yticklabels([r[0] for r in rows11])
ax.set_ylim(len(rows11) - 0.45, -0.75)
ax.set_xlim(0, 1470)
ax.set_xticks([0, 200, 400, 600, 800, 1000, 1200, FUZZ_N])
ax.set_xlabel("stored fuzz cases with recorded reference hashes\n(every completed replay reproduces the reference on all 1,318)")
ax.set_title("Who processes the 1,318 stored fuzz cases, build by build")
ax.grid(axis="y", visible=False)
save(fig, "fig11_fuzz")

# ------------------------------------------------------------------ fig 12: measurement noise on the development machine
fig, (ax, axb) = plt.subplots(2, 1, figsize=(7.6, 5.6), gridspec_kw={"height_ratios": [1.0, 1.25]})
runs = {"sub5": [3.871, 3.638, 4.126], "sub6": [5.650, 3.570, 3.583]}
for i, (lab, vs) in enumerate(runs.items()):
    ax.scatter(vs, [i] * 3, s=70, color=BLUE, edgecolor=SURF, linewidth=1.5, zorder=4)
    close = sorted(vs)[1] - sorted(vs)[0] < 0.05  # two runs too close to label apart
    for v in ([sorted(vs)[2]] if close else vs):
        ax.text(v, i + 0.2, "%.2f" % v, ha="center", fontsize=8.5, color=INK2)
    if close:
        ax.text(sorted(vs)[1] + 0.05, i + 0.2, "%.2f and %.2f" % tuple(sorted(vs)[:2]), ha="left", fontsize=8.5, color=INK2)
ax.annotate("one run 58% slower than its repeats:\nmachine under memory pressure, not the code", xy=(5.65, 1), xytext=(4.55, 0.25),
            fontsize=9, color=INK, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax.set_yticks(range(2))
ax.set_yticklabels(list(runs))
ax.set_ylim(-0.5, 1.6)
ax.set_xlim(3.2, 6.0)
ax.set_xlabel("whole-process time summed over 65 units in one benchmark run (s)")
ax.set_title("Three benchmark runs of one image (inputs from the unit folders)", fontsize=11)
ax.grid(axis="y", visible=False)
# The later method (inputs in memory, 71 units, best of 5): the same build measured in two sessions
# (truep_<name>.json and truep_<name>_b.json; REPORT.md 9.9.3 gives the sub16 and sub17 writer-off pairs).
PAIRS12 = [("sub17, writer\nthreads on", "sub17t"), ("sub17, writer\nthreads off", "sub17n"), ("sub16", "sub16")]
for i, (lab, name) in enumerate(PAIRS12):
    v1, v2 = [sum(u["ms"] for u in TP(name + sfx).values()) / 1e3 for sfx in ("", "_b")]
    axb.plot([v1, v2], [i, i], color=GRID, lw=2.2, zorder=2)
    axb.scatter([v1], [i], s=70, color=BLUE, edgecolor=SURF, linewidth=1.5, zorder=4, label="first session" if i == 0 else None)
    axb.scatter([v2], [i], s=70, color=ORANGE, edgecolor=SURF, linewidth=1.5, zorder=4, label="a later session" if i == 0 else None)
    for v, ha in ((v1, "right" if v1 < v2 else "left"), (v2, "left" if v1 < v2 else "right")):
        axb.text(v + (-0.035 if ha == "right" else 0.035), i + 0.2, "%.2f" % v, ha=ha, fontsize=8.5, color=INK2)
    axb.text(2.36, i, "%+.0f%%" % (100.0 * (v2 / v1 - 1.0)), ha="left", va="center", fontsize=9.5, fontweight="bold")
axb.set_yticks(range(len(PAIRS12)))
axb.set_yticklabels([p[0] for p in PAIRS12], fontsize=9, linespacing=1.15)
axb.set_ylim(-0.6, 2.75)
axb.set_xlim(1.1, 2.55)
axb.set_xlabel("sum of the launcher's phases over 71 units, best of 5 runs per unit (s)")
axb.set_title("The same build in two sessions (inputs in memory)", fontsize=11)
axb.legend(loc="lower right", ncol=2, handletextpad=0.3, columnspacing=1.0)
axb.grid(axis="y", visible=False)
fig.tight_layout(h_pad=2.0)
save(fig, "fig12_noise")

# ------------------------------------------------------------------ fig 13: old-rule history (log scale)
fig, ax = plt.subplots(figsize=(7.6, 3.2))
old = [("ABIDES baseline", 4862), ("sub1: native engine", 4260093), ("sub2: pre-fault,\ntiming scope, batch fix", 8340072)]
ax.bar(range(3), [o[1] for o in old], width=0.5, color=GRAY, zorder=3)
for i, (_, v) in enumerate(old):
    ax.text(i, v * 1.25, k(v), ha="center", fontsize=10.5, fontweight="bold", zorder=5,
            bbox=dict(facecolor=SURF, edgecolor="none", pad=1.0))
for i in (1, 2):  # the step from the bar before, as a ratio
    ax.text(i - 0.5, 2.2e5, "×%s" % ("%.0f" % (old[i][1] / old[i - 1][1]) if old[i][1] / old[i - 1][1] > 10
                                     else "%.2f" % (old[i][1] / old[i - 1][1])), ha="center", fontsize=9.5, color=INK2)
ax.axhline(1e7, color=INK2, lw=1.0, ls=(0, (4, 3)), zorder=2)
ax.text(0.5, 1.3e7, "cap per unit under that rule: 10,000,000", ha="center", fontsize=8.6, color=INK2)
ax.set_yscale("log")
ax.set_ylim(1000, 6e7)
ax.set_xticks(range(3))
ax.set_xticklabels([o[0] for o in old], fontsize=9)
ax.set_ylabel("self-reported events/s (log scale)")
ax.set_title("Scores under the first scoring rule (no longer ranked)")
ax.grid(axis="x", visible=False)
save(fig, "fig13_old_rule")


# ------------------------------------------------------------------ fig 15: laptop prediction against host score, step by step
# (docs/REPORT.md 9.8.6) laptop: change in warm process time; host: change in score. One upload each.
tot = lambda t: sum(v["ms"] for v in NEW[t].values())
chg = lambda x, y: 100.0 * (tot(y) / tot(x) - 1.0)  # change in summed warm process time, 65 units, shipped modes
pct_host = lambda a, b: 100.0 * (HOST11[b] / HOST11[a] - 1.0)  # change in score between two of the last uploads
STEPS = [("sub4 → sub5\ninterpreter and\nArrow encoder\nremoved", -67.0, 18.0),
         ("sub5 → sub7\nsmaller files,\n2.2 MB image", -4.0, 1.9),
         ("sub7 → sub9\nfewer page\nfaults", -23.0, -0.8),
         # interleaved A/B on the six units concerned (docs/REPORT.md 9.8.3); the 65-unit sums
         # of the later measurement run differ by less than that run's own spread
         ("sub9 → sub10\nno ledger on\nsix heavy units\n(those units)", -11.9, 2.9),
         ("sub10 → sub11\nprofile-guided\nbuild, memory\nswitches off", chg("sub10", "sub11"), 0.2),
         ("sub11 → sub13\nstreamed files,\none encoding\nthread per file", chg("sub11", "sub13"), -2.6),
         # sub11 → sub16: the laptop comparisons gave 4 to 7% less process time (a range; the bar
         # is solid up to the low end and lighter up to the high end). The two sub17 steps: process time over all
         # 71 units, best of 5, inputs in memory, one session (lab/bench/truep_sub16.json, truep_sub17n.json,
         # truep_sub17t.json: 1.895 s, 1.627 s, 1.348 s).
         ("sub11 → sub16\ntrace in final\norder during\nthe run", (-7.0, -4.0), 7.6),
         # sub16 → sub17 was timed in two sessions: 1.895 → 1.627 s and, in a later and slower one,
         # 2.228 → 2.152 s (truep_sub16_b.json, truep_sub17n_b.json). Both are shown, as a range.
         ("sub16 → sub17\nbranch-free heap\nstep, changed\nhelper start-up",
          (100.0 * (1.627 / 1.895 - 1.0), 100.0 * (2.152 / 2.228 - 1.0)), pct_host("sub16", "sub17_writer_off")),
         ("sub17: writer\nthreads during\nthe run\nswitched on", 100.0 * (1.348 / 1.627 - 1.0),
          pct_host("sub17_writer_off", "sub17_writer_on")),
         # sub19a was never timed on the laptop with the inputs in memory: no laptop bar.
         ("sub16 → sub19a\nsub18's engine\nunder sub16's\nhelper code", None, pct_host("sub16", "sub19a"))]
fig, ax = plt.subplots(figsize=(12.2, 4.8))
w = 0.36
for i, (lab, lap, host) in enumerate(STEPS):
    lo = None if lap is None else -max(lap) if isinstance(lap, tuple) else -lap  # smallest saving measured
    if lo is not None and lo * host < 0:
        ax.axvspan(i - 0.46, i + 0.46, color=GRID, alpha=0.6, lw=0, zorder=0)
        ax.text(i, 76.5, "opposite signs", ha="center", va="top", fontsize=7.8, color=INK2)
    if isinstance(lap, tuple):
        hi = -min(lap)
        ax.bar(i - w / 2, lo, width=w, color=GRAY, zorder=3)
        ax.bar(i - w / 2, hi - lo, bottom=lo, width=w, color=GRAY, alpha=0.45, zorder=3)
        ax.text(i - 0.03, hi + 2.5, "+%.0f–%.0f" % (lo, hi), ha="right", va="bottom", fontsize=8.6, color=INK2)
    elif lap is not None:
        ax.bar(i - w / 2, -lap, width=w, color=GRAY, zorder=3, label="laptop: process time saved (%)" if i == 0 else None)
        ax.text(i - w / 2, -lap + (2.5 if -lap >= 0 else -2.5), "%+.0f" % -lap, ha="center", va="bottom" if -lap >= 0 else "top", fontsize=8.6, color=INK2)
    else:
        ax.text(i - w / 2, 2.5, "not\nmeasured", ha="center", va="bottom", fontsize=7.6, color=MUTE)
    ax.bar(i + w / 2, host, width=w, color=BLUE, zorder=3, label="scoring host: score change (%)" if i == 0 else None)
    ax.text(i + w / 2, host + (2.5 if host >= 0 else -2.5), "%+.1f" % host, ha="center", va="bottom" if host >= 0 else "top",
            fontsize=9, fontweight="bold")
ax.axhline(0, color=INK2, lw=0.9, zorder=4)
ax.set_xticks(range(len(STEPS)))
ax.set_xticklabels([s[0] for s in STEPS], fontsize=7.1, linespacing=1.2)
ax.set_ylim(-16, 80)
ax.set_ylabel("percent")
ax.set_title("What the laptop predicted and what the scoring host returned, step by step")
ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.9))
ax.grid(axis="x", visible=False)
save(fig, "fig15_laptop_vs_host")

# ------------------------------------------------------------------ fig 16: what the leader's score says about the fixed cost
N_ALL, UNITS_ALL = 7728572, 71  # public Development roster: 65 single-scenario units and 6 batch units
mean_n = N_ALL / UNITS_ALL
fig, ax = plt.subplots(figsize=(7.6, 4.0))
cs = [0.30 + 0.002 * i for i in range(151)]
ax.plot(cs, [mean_n / c for c in cs], color=INK, lw=2, zorder=3)
ax.annotate("score of a submission\nthat does no work at all", xy=(0.345, mean_n / 0.345), xytext=(0.365, 338000),
            fontsize=8.8, color=INK, va="center", arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
bound = mean_n / LEADER
ax.axvspan(bound, 0.60, color=GRAY, alpha=0.35, zorder=1, lw=0)
ax.text(bound + 0.006, 352000, "ruled out by the leader's score:\nfixed cost above %.3f s" % bound, fontsize=8.6, color=INK2, va="top")
for v, lab, col, above in [(LEADER, "leader: %s" % k(LEADER), INK2, False),
                           (240000, "240,000: needs a fixed cost below %.3f s" % (mean_n / 240000), ORANGE, True),
                           (BEST, "our best, sub16: %s" % k(BEST), BLUE, True)]:
    ax.axhline(v, color=col, lw=1.2, ls=(0, (4, 3)), zorder=2)
    ax.text(0.302, v + (3000 if above else -3500), lab, fontsize=8.6, color=INK, va="bottom" if above else "top")
ax.scatter([bound], [LEADER], s=64, color=INK, edgecolor=SURF, linewidth=2, zorder=5)
ax.set_xlim(0.30, 0.60)
ax.set_ylim(150000, 370000)
ax.yaxis.set_major_formatter(lambda v, _: k(v))
ax.set_xlabel("fixed container cost per unit (s)")
ax.set_ylabel("Development score")
ax.set_title("An upper limit on the fixed cost: %s events per unit ÷ leader's score" % k(mean_n), fontsize=11)
ax.grid(axis="x", visible=False)
save(fig, "fig16_fixed_cost_bound")

# ------------------------------------------------------------------ fig 17: the uploads that differ in one setting
PREV_BEST = 189018.28  # sub11
fig, ax = plt.subplots(figsize=(8.6, 4.5))
pct = lambda a, b: 100.0 * (b / a - 1.0)
# What sub19a would have scored had the helper been worth on sub18's engine what it is worth on sub16's.
# Arithmetic on three scores, drawn hollow; it is not a measurement.
IF_BOTH = HOST11["sub18_helper_off"] * HOST11["sub16"] / HOST11["sub16_helper_off"]
rows17 = [("sub16's engine\n(one binary)", [("sub16_helper_off", ORANGE, "helper off"), ("sub16", BLUE, "sub16: helper on")],
           "latency helper thread: %+.1f%% (same binary, one environment variable)"
           % pct(HOST11["sub16_helper_off"], HOST11["sub16"])),
          ("sub17 binary\n(helper on, started\nat engine creation)",
           [("sub17_writer_off", BLUE, "writer threads off"), ("sub17_writer_on", BLUE, "writer threads on")],
           "writer threads during the run: %+.1f%%; sub17 against sub16, both without them: %+.1f%%"
           % (pct(HOST11["sub17_writer_off"], HOST11["sub17_writer_on"]), pct(HOST11["sub16"], HOST11["sub17_writer_off"]))),
          ("sub18's engine\n(sub18 with helper off;\nsub19a = that engine\nwith sub16's helper code)",
           [("sub18_helper_off", ORANGE, "sub18: helper off"), ("sub19a", BLUE, "sub19a: helper on")],
           "engine alone, helper off on both: %+.1f%% over sub16's. The same helper code on top: %+.1f%%, not %+.1f%%.\n"
           "sub19a against sub16: %+.1f%%. Had both gains held, sub19a would have scored %s."
           % (pct(HOST11["sub16_helper_off"], HOST11["sub18_helper_off"]), pct(HOST11["sub18_helper_off"], HOST11["sub19a"]),
              pct(HOST11["sub16_helper_off"], HOST11["sub16"]), pct(HOST11["sub16"], HOST11["sub19a"]), k(IF_BOTH)))]
ax.plot([HOST11["sub19a"], IF_BOTH], [0, 0], color=GRID, lw=2.2, ls=(0, (2, 2)), zorder=2)
ax.scatter([IF_BOTH], [0], s=64, facecolor=SURF, edgecolor=BLUE, linewidth=1.6, zorder=4)
ax.text(IF_BOTH, 0.15, k(IF_BOTH) + "\nif both gains had held", ha="center", va="bottom", fontsize=8.2, color=INK2, linespacing=1.2)
for i, (lab, pts, note) in enumerate(rows17[::-1]):
    vs = [HOST11[key] for key, _, _ in pts]
    if len(vs) > 1:
        ax.plot([min(vs), max(vs)], [i, i], color=GRID, lw=2.2, zorder=2)
    for n, (key, col, what) in enumerate(pts):
        ax.scatter([HOST11[key]], [i], s=64, color=col, zorder=4, edgecolor=SURF, linewidth=1.5)
        ha = "center" if len(pts) == 1 else ("right" if n == 0 else "left")
        ax.text(HOST11[key] + (0 if ha == "center" else (300 if ha == "right" else -300)), i + 0.15,
                k(HOST11[key]) + "\n" + what, ha=ha, va="bottom", fontsize=8.2, color=INK, linespacing=1.2)
    ax.text(183300, i - 0.2, note, ha="left", va="top", fontsize=8.0, color=INK2, zorder=5,
            bbox=dict(facecolor=SURF, edgecolor="none", pad=1.5))
ax.axvline(PREV_BEST, color=INK2, lw=1.0, ls=(0, (4, 3)), zorder=1)
ax.text(PREV_BEST + 250, 2.92, "previous best\n(sub11): " + k(PREV_BEST), fontsize=7.8, color=INK2, va="top", linespacing=1.2)
handles = [plt.Line2D([], [], marker="o", ls="", color=BLUE, markersize=7), plt.Line2D([], [], marker="o", ls="", color=ORANGE, markersize=7),
           plt.Line2D([], [], marker="o", ls="", markerfacecolor=SURF, markeredgecolor=BLUE, markeredgewidth=1.6, markersize=7)]
ax.legend(handles, ["latency helper thread on", "latency helper thread off", "arithmetic, not a score"], loc="upper center",
          bbox_to_anchor=(0.5, -0.17), ncol=3)
ax.set_yticks(range(len(rows17)))
ax.set_yticklabels([r[0] for r in rows17[::-1]], fontsize=8.2, linespacing=1.2)
ax.set_ylim(-0.8, 3.0)
ax.set_xlim(183000, 216500)
ax.xaxis.set_major_formatter(lambda v, _: k(v))
ax.set_xlabel("Development score (the axis does not start at zero)")
ax.set_title("The last six uploads by engine: the helper thread's gain did not carry over")
ax.grid(axis="y", visible=False)
save(fig, "fig17_host_pairs")

# ------------------------------------------------------------------ fig 18: hardware counters on the largest unit
# Top row: builds as shipped (profile-guided), CNT. Bottom row: test builds without profile feedback in the
# order the changes of sub18 were made (REPORT.md 9.9.7); millions, (low, high) of the runs made, None = not
# recorded. No counter run of the shipped sub18 or of sub19a is in the record, so neither is drawn.
T18C = {"cycles": [(830, 850), (797, 805), (750, 750), (733, 733)],
        "instructions": [(v, v) for _, v in STEPS18],
        "branch misses": [None, (5.12, 5.12), (4.71, 4.71), (4.35, 4.35)]}
fig = plt.figure(figsize=(9.6, 7.0))
gs = fig.add_gridspec(2, 3)
head18 = []
for r, (xl, col) in enumerate([(["sub16", "sub17"], BLUE), (["sub17\nengine", "+ 1", "+ 2", "+ 3"], AQUA)]):
    for j, (name, unit) in enumerate([("cycles", "million cycles"), ("instructions", "million instructions"),
                                      ("branch misses", "million branch misses")]):
        ax = fig.add_subplot(gs[r, j])
        data = [CNT[name][b] for b in xl] if r == 0 else T18C[name]
        top = max(d[1] for d in data if d)
        f = (lambda v: "%.2f" % v) if top < 100 else (lambda v: "{:,.0f}".format(v))
        for i, d in enumerate(data):
            if d is None:
                ax.text(i, top * 0.03, "not\nrecorded", ha="center", va="bottom", fontsize=7.6, color=MUTE, linespacing=1.15)
                continue
            lo, hi = d
            ax.bar(i, lo, width=0.6, color=col, zorder=3)
            if hi > lo:
                ax.bar(i, hi - lo, bottom=lo, width=0.6, color=col, alpha=0.35, zorder=3)
            ax.text(i, hi + top * 0.03, f(lo) if hi == lo else f(lo) + "–" + f(hi), ha="center", fontsize=9 if r == 0 else 7.8, fontweight="bold")
        ax.set_xticks(range(len(xl)))
        ax.set_xticklabels(xl, fontsize=10 if r == 0 else 8.6, linespacing=1.15)
        ax.set_xlim(-0.6, len(xl) - 0.4)
        ax.set_ylim(0, top * 1.18)
        if top > 100:
            ax.yaxis.set_major_formatter(lambda v, _: k(v))
        ax.set_ylabel(unit)
        ax.set_title(name.capitalize(), fontsize=11)
        ax.grid(axis="x", visible=False)
        if j == 0:
            head18.append(ax)
fig.suptitle("Hardware counters on the largest unit, one thread (helper and writer threads off)",
             x=0.012, ha="left", fontsize=12, fontweight="bold")
fig.tight_layout(h_pad=5.0, w_pad=1.6, rect=(0, 0.09, 1, 0.92))
for ax, txt in zip(head18, ["sub16 and sub17 as shipped (profile-guided builds); a lighter band is the range of the runs made",
                            "From sub17 to sub18, change by change (test builds without profile feedback, so not comparable with the top row)"]):
    fig.text(0.012, ax.get_position().y1 + 0.052, txt, ha="left", va="bottom", fontsize=9.6, color=INK)
fig.text(0.012, 0.012, "+ 1: 32-byte trace rows\n+ 2: own-order records for market makers only, one-row trace buckets, no record for a skipped ledger\n"
         "+ 3: wakeup rings, blocked queues as sorted vectors (the state of sub18's engine)",
         ha="left", va="bottom", fontsize=8.6, color=INK2, linespacing=1.35)
save(fig, "fig18_counters")

# ------------------------------------------------------------------ fig 14: what is timed, what runs inside it, the exact layers
from matplotlib.patches import FancyArrowPatch, Polygon

TINT = "#dbe8f9"   # our own stages
WASH = "#eef4fc"   # background of the zoomed panel
STONE = "#f1f0ec"  # fallback layers


def box(ax, x0, x1, y0, y1, text, fc, ec=None, fs=7.8, bold=False, tc=INK, ls="-", z=3):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=0.008", fc=fc,
                                ec=ec or fc, lw=1.0, ls=ls, zorder=z))
    ax.text((x0 + x1) / 2, (y0 + y1) / 2, text, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", color=tc, zorder=z + 1, linespacing=1.3)


def arrow(ax, x0, y0, x1, y1, style="-|>", lw=1.0, color=INK2):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style, mutation_scale=9, lw=lw, color=color,
                                 shrinkA=0, shrinkB=0, zorder=5))


def panel(ax, y, letter, title):
    ax.text(0.02, y, letter, fontsize=9.5, fontweight="bold", va="center")
    ax.text(0.05, y, title, fontsize=9.5, fontweight="bold", va="center")


fig, ax = plt.subplots(figsize=(7.6, 5.6))
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

# ---- A: the measured window. Widths are schematic: for a median unit our process is a small part.
panel(ax, 0.965, "A", "What the harness times: one fresh container per unit, run once")
arrow(ax, 0.02, 0.895, 0.98, 0.895, style="<|-|>")
ax.text(0.50, 0.912, "container time measured by the harness; its fixed part is at most 0.47 s per unit",
        fontsize=7.8, color=INK2, ha="center", va="bottom")
box(ax, 0.02, 0.50, 0.785, 0.875, "create container, attach GPU, start\n(fixed, the same for every team)", GRAY)
box(ax, 0.505, 0.655, 0.785, 0.875, "our process", BLUE, bold=True, tc="white", fs=8.4)
box(ax, 0.66, 0.98, 0.785, 0.875, "notice exit, remove container\n(fixed)", GRAY)
ax.text(0.98, 0.765, "widths not to scale", fontsize=6.8, color=MUTE, ha="right", va="top")

# ---- B: inside our process, one lane per thread, time running to the right
ax.add_patch(Polygon([(0.505, 0.785), (0.655, 0.785), (0.98, 0.70), (0.02, 0.70)], closed=True, fc=WASH, ec="none", zorder=1))
ax.add_patch(FancyBboxPatch((0.02, 0.268), 0.96, 0.432, boxstyle="round,pad=0,rounding_size=0.008", fc=WASH, ec="none", zorder=1))
panel(ax, 0.668, "B", "Inside our process, as in sub16 and sub19a (time runs right)")
ax.texts[-2].set_x(0.035)
ax.texts[-1].set_x(0.065)
lanes = [("main thread", 0.565), ("helper thread", 0.485), ("trace file", 0.405), ("ledger file", 0.325)]
for name, y in lanes:
    ax.text(0.035, y + 0.0325, name, fontsize=7.6, color=INK2, va="center")
    ax.plot([0.185, 0.965], [y + 0.0325, y + 0.0325], color="#cfdcee", lw=0.8, zorder=2)
ym, yh, yt, yl = [y for _, y in lanes]
H = 0.065
box(ax, 0.190, 0.262, ym, ym + H, "parse\nscenario", TINT, ec=BLUE, fs=7.0)
box(ax, 0.274, 0.360, ym, ym + H, "build\nconfig", TINT, ec=BLUE, fs=7.0)
box(ax, 0.375, 0.640, ym, ym + H, "event loop: dispatch, order\nbook, trace in final order", TINT, ec=BLUE, fs=7.0)
box(ax, 0.890, 0.965, ym, ym + H, "result,\nexit", TINT, ec=BLUE)
arrow(ax, 0.262, ym + H / 2, 0.274, ym + H / 2)
arrow(ax, 0.360, ym + H / 2, 0.375, ym + H / 2)
# the helper as shipped in sub16 and restored in sub19a: created with the engine and parked on a condition
# variable, woken by the event loop when the run starts, spinning (pause, then yield) while its ring is full
box(ax, 0.262, 0.360, yh, yh + H, "parked until\nthe run starts", WASH, ec=BLUE, ls=(0, (3, 2)), fs=6.0, tc=INK2)
box(ax, 0.375, 0.640, yh, yh + H, "latency draws ahead, ring of\n2¹³ values; spins when full", TINT, ec=BLUE, fs=7.0)
arrow(ax, 0.360, yh + H / 2, 0.375, yh + H / 2)
ax.text(0.7645, yh + H / 2, "helper late at the start:\nthe loop draws for itself\nfor the whole run", fontsize=6.3, color=INK2,
        ha="center", va="center", linespacing=1.25, zorder=6, bbox=dict(boxstyle="square,pad=0.1", fc=WASH, ec="none"))
box(ax, 0.675, 0.855, yt, yt + H, "3–4 encoder threads,\nhash, one write", TINT, ec=BLUE, fs=7.0)
box(ax, 0.675, 0.855, yl, yl + H, "2 encoder threads,\nhash, one write", TINT, ec=BLUE, fs=7.0)
arrow(ax, 0.640, ym + H / 2, 0.890, ym + H / 2)
for y in (yt, yl):  # the output chains start when the event loop ends and are joined before exit
    ax.plot([0.657, 0.657], [ym + H / 2, y + H / 2], color=INK2, lw=1.0, zorder=5)
    arrow(ax, 0.657, y + H / 2, 0.675, y + H / 2)
    ax.plot([0.855, 0.872, 0.872], [y + H / 2, y + H / 2, ym + H / 2], color=INK2, lw=1.0, zorder=5)
# behind a switch (sub15; scored once, as sub17 with writer threads on): one writer thread per file during the event loop
box(ax, 0.375, 0.640, yl, yt + H, "only with T3_TRAIL=1\n(default 0): a writer thread\nper file works here, on\nrows already final", WASH, ec=BLUE,
    ls=(0, (3, 2)), fs=7.0, tc=INK2)
ax.text(0.965, 0.295, "no ledger on the six units whose card needs none  ·  helper only for costly latency draws and with two usable CPUs\n"
        "batch units: up to four markets at once, one thread each, no helper",
        fontsize=6.6, color=INK2, ha="right", va="center", linespacing=1.3)

# ---- C: the three exact layers
panel(ax, 0.235, "C", "Three layers that produce the same tables")
yc0, yc1 = 0.085, 0.185
box(ax, 0.020, 0.300, yc0, yc1, "C++ launcher\nstatic binary,\nown Parquet writer", TINT, ec=BLUE)
box(ax, 0.400, 0.660, yc0, yc1, "Python + native engine\npyarrow writer", STONE, ec=MUTE)
box(ax, 0.760, 0.980, yc0, yc1, "original ABIDES\nreference path", STONE, ec=MUTE)
for x0, x1 in ((0.300, 0.400), (0.660, 0.760)):
    arrow(ax, x0 + 0.006, (yc0 + yc1) / 2, x1 - 0.006, (yc0 + yc1) / 2)
    ax.text((x0 + x1) / 2, (yc0 + yc1) / 2 + 0.014, "only if it\ndeclines", fontsize=6.8, color=INK2, ha="center", va="bottom", linespacing=1.2)
ax.plot([0.020, 0.300], [0.060, 0.060], color=BLUE, lw=1.4, solid_capstyle="butt")
ax.text(0.020, 0.050, "scratch image (every scored build from sub7 on): this layer only.\nA declined input exits with status 127; the unit scores zero.",
        fontsize=7.0, color=INK2, va="top", linespacing=1.3)
ax.plot([0.020, 0.980], [0.000, 0.000], color=MUTE, lw=1.4, solid_capstyle="butt")
ax.text(0.980, 0.012, "full image (scored as sub4, sub5; used to\nvalidate every build): all three layers", fontsize=7.0, color=INK2,
        ha="right", va="bottom", linespacing=1.3)
save(fig, "fig14_system")
print("done")
