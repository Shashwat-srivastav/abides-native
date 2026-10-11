"""Compare two builds from bench_unit_dirs.py results: best time per unit over the given rounds.

    python lab/cmp_bench.py <prefix> <tagA> <tagB> <rounds, e.g. abc>
reads lab/bench/<prefix>_<tag>_<round>.json
"""
import json
import pathlib
import sys

B = pathlib.Path(__file__).resolve().parent / "bench"
prefix, ta, tb, rounds = sys.argv[1:5]


def best(tag):
    runs = [json.load(open(B / ("%s_%s_%s.json" % (prefix, tag, r)))) for r in rounds]
    return {u: min(run[u]["ms"] for run in runs) for u in runs[0]}


a, b = best(ta), best(tb)
for u in a:
    print("%-32s %s %7.1f  %s %7.1f  %+5.1f%%" % (u, ta, a[u], tb, b[u], (b[u] / a[u] - 1) * 100))
sa, sb = sum(a.values()), sum(b.values())
print("sum %.1f -> %.1f  %+.1f%%" % (sa, sb, (sb / sa - 1) * 100))
