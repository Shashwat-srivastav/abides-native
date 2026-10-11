"""Three-way differential check on fuzz cases, inside a submission image.

    python recheck_launcher.py <cases_dir_or_glob> [max_cases]

For every case: run the exact ABIDES reference, the image's real `simulate` command (the launcher),
and the Python native path (launcher disabled). A case is IDENTICAL only if every path that succeeds
agrees with the reference on both parquet SHA-256s recomputed from disk; if the reference itself
fails, the launcher must fail too (it hands such inputs to the reference path).
"""
import glob, hashlib, json, os, random, subprocess, sys, time

sys.path.insert(0, "/opt")
src = sys.argv[1]
files = sorted(glob.glob(src if any(c in src for c in "*?[") else os.path.join(src, "*.json")))
if len(sys.argv) > 2 and len(files) > int(sys.argv[2]):
    random.Random(12345).shuffle(files)
    files = sorted(files[: int(sys.argv[2])])


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, out, env=None):
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(out + "/*"):
        os.remove(f)
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(cmd + ["--out", out + "/trace.parquet"], capture_output=True, text=True, env=e)
    if r.returncode != 0 or not os.path.exists(out + "/events.json"):
        return None, r.stderr
    return (sha(out + "/trace.parquet"), sha(out + "/message_trace.parquet"), json.load(open(out + "/events.json"))["n_events"]), r.stderr


ref_code = "import sys; sys.path.insert(0,'/opt'); from abides_fork.simulate import simulate; simulate(sys.argv[1], sys.argv[3])"
tally = {}
t0 = time.time()
for f in files:
    cid = os.path.basename(f)[:-5]
    ref, _ = run([sys.executable, "-c", ref_code, f], f"/tmp/fz/r/{cid}")
    lau, lerr = run(["simulate", "--config", f], f"/tmp/fz/l/{cid}")
    pyn, perr = run(["simulate", "--config", f], f"/tmp/fz/p/{cid}", {"T3_NO_LAUNCHER": "1"})
    how = "python-path" if "using the Python path" in lerr else "launcher"
    if "falling back to ABIDES reference" in lerr:
        how = "abides-fallback"
    if ref is None:
        verdict = "BOTH_FAIL" if lau is None and pyn is None else "REF_FAIL_CANDIDATE_OK"
    elif lau == ref and pyn == ref:
        verdict = "IDENTICAL"
    else:
        verdict = "DIFF"
    key = f"{verdict} via {how}"
    tally[key] = tally.get(key, 0) + 1
    print(f"{cid:28s} {verdict:22s} {how:16s} n={ref[2] if ref else '-'}", flush=True)
print(f"\ncases={len(files)} seconds={time.time() - t0:.0f}")
for k in sorted(tally):
    print(f"  {tally[k]:5d}  {k}")
