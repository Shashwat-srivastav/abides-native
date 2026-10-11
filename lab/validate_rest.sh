#!/bin/bash
# The two long stages of validate_image.sh (official regression, stored fuzz corpus), for a run
# whose first stages already finished.  usage: validate_rest.sh <tag>
set -u
export MSYS_NO_PATHCONV=1
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
R=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd))
cd "$ROOT"
IMG=agenthon-track3:$1; O=lab/bench/val_$1; mkdir -p $O
echo "== official regression"; IMAGE=$IMG OUT=$ROOT/repro/out_$1 bash repro/repro.sh official > $O/official.log 2>&1; echo "rc=$? $(grep "total_scenarios" $O/official.log | tail -1)"
echo "== fuzz corpus"; docker run --rm --cpus 4 -v "$R/native/fuzz:/fz:ro" $IMG python /fz/recheck_stored.py /fz > $O/fuzz.log 2>&1; echo "rc=$?"; tail -4 $O/fuzz.log
echo "== DONE"
