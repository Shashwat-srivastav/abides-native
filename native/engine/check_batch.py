"""Compare native batch outputs in /tmp/bo with verified reference outputs in /work/bref.

Hashes are recomputed from the files on disk. A unit is OK only if every sub-scenario's two parquet
files match and batch_events.json has the same structure, counts and per-sub hashes.
"""
import glob, hashlib, json, os


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


ok = bad = 0
for agg in sorted(glob.glob("/tmp/bo/*/batch_events.json")):
    u = os.path.basename(os.path.dirname(agg))
    a = json.load(open(agg))
    r = json.load(open(f"/work/bref/{u}/batch_events.json"))
    line = json.load(open(f"/tmp/bo_{u}.json"))
    good = (line == a and list(a) == list(r) and a["n_scenarios"] == r["n_scenarios"]
            and a["total_events"] == r["total_events"] and len(a["per_scenario"]) == len(r["per_scenario"])
            and [list(x) for x in a["per_scenario"]] == [list(x) for x in r["per_scenario"]])
    for x, y in zip(a["per_scenario"], r["per_scenario"]):
        d = f"/tmp/bo/{u}/{x['sub']}"
        ref = json.load(open(f"/work/bref/{u}/{y['sub']}/events.json"))
        ev = json.load(open(d + "/events.json"))
        good &= (x["sub"] == y["sub"] and x["trace_sha256"] == y["trace_sha256"] == sha(d + "/trace.parquet")
                 and sha(d + "/message_trace.parquet") == ref["message_trace_sha256"] == ev["message_trace_sha256"]
                 and ev["n_events"] == ref["n_events"] == x["n_events"] and list(ev) == list(ref))
    ok += good
    bad += not good
    print("OK " if good else "BAD", u, a["n_scenarios"], a["total_events"], round(a["events_per_sec"]))
print("batch identical:", ok, "different:", bad)
