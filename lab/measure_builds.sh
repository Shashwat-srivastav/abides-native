#!/bin/bash
# Warm measurements of several builds on the 65 single-scenario units, for the report's figures.
#   bash lab/measure_builds.sh <rounds> <repeats> <tag[:off]> [tag[:off] ...]
# ":off" runs the build with the memory switches off (T3_HUGE=0 T3_PREFAULT=0), the mode sub11 and
# later were shipped in. Rounds are interleaved across builds; results go to
# lab/bench/fig_<tag>_<round>.json (best time, page faults, peak memory, output bytes per unit).
# Run on a quiet machine. These are warm runs inside one container (see bench_unit_dirs.py).
set -u
export MSYS_NO_PATHCONV=1
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
R=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd))
cd "$ROOT"
rounds=$1; reps=$2; shift 2
U=$(ls track3-simulation-public-clone/units | grep -v EXAMPLE | grep -v gbatch | tr '\n' ' ')
for round in $(seq $rounds); do
  for spec in "$@"; do
    tag=${spec%%:*}; env=""
    [ "$spec" != "$tag" ] && env="-e T3_HUGE=0 -e T3_PREFAULT=0"
    docker run --rm --cpus 4 --shm-size 2g $env -v "$R/track3-simulation-public-clone/units:/units:ro" \
      -v "$R/native/engine:/eng:ro" -v "$R/lab/bench:/bench" agenthon-track3:$tag \
      python /eng/bench_unit_dirs.py /units /bench/fig_${tag}_$round.json $reps $U > /dev/null 2>&1
    echo "round $round $tag done: $(python -c "import json;d=json.load(open('lab/bench/fig_${tag}_$round.json'));print(len(d),'units, sum %.0f ms'%sum(v['ms'] for v in d.values()))")"
  done
done
