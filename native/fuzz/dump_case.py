"""Write stored fuzz cases out as scenario files.

    python dump_case.py <dir_with_jsonl> <out_dir> <id> [id ...]
    python dump_case.py <dir_with_jsonl> <out_dir> --declined "<reason substring>"
The second form runs the launcher on every replayable case (as decline_reasons.py does) and
writes those whose hand-over reason contains the substring.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recheck_stored import load  # noqa: E402

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
cases, _ = load(src)
if sys.argv[3] == "--declined":
    want = sys.argv[4]
    n = 0
    for d in cases:
        json.dump(d["scenario"], open("/tmp/dc.json", "w"))
        r = subprocess.run(["/usr/local/bin/simulate", "--config", "/tmp/dc.json", "--out", "/tmp/dc/trace.parquet"],
                           capture_output=True, text=True, env={"PATH": "/nonexistent"})
        m = re.search(r"using the Python path \((.*)\)", r.stderr)
        if m and want in m.group(1):
            json.dump(d["scenario"], open(os.path.join(out, "%s_%d.json" % (d["id"], n)), "w"))
            n += 1
    print("written", n)
else:
    ids = set(sys.argv[3:])
    n = 0
    for d in cases:
        if d["id"] in ids:
            json.dump(d["scenario"], open(os.path.join(out, "%s_%d.json" % (d["id"], n)), "w"))
            n += 1
    print("written", n)
