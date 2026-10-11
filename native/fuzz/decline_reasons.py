"""Why does the launcher hand stored fuzz cases to the Python path?

    python decline_reasons.py <dir_with_jsonl>
Runs only the launcher on every replayable case, with PATH emptied so the hand-over cannot start
Python (the launcher then exits 127 right after printing its reason). Prints a histogram.
"""
import collections
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recheck_stored import load  # noqa: E402  (its main() is guarded below)

cases, _ = load(sys.argv[1])
hist, examples = collections.Counter(), {}
for d in cases:
    json.dump(d["scenario"], open("/tmp/dr.json", "w"))
    r = subprocess.run(["/usr/local/bin/simulate", "--config", "/tmp/dr.json", "--out", "/tmp/dr/trace.parquet"],
                       capture_output=True, text=True, env={"PATH": "/nonexistent"})
    m = re.search(r"using the Python path \((.*)\)", r.stderr)
    why = m.group(1) if m else ("handled by the launcher" if r.returncode == 0 else "exit %d: %s" % (r.returncode, r.stderr[-80:]))
    why = re.sub(r"[-+]?\d+(\.\d+)?(e[-+]?\d+)?", "N", why)
    hist[why] += 1
    examples.setdefault(why, d["id"])
for why, n in hist.most_common():
    print("%6d  %-70s e.g. %s" % (n, why, examples[why]))
