#!/bin/bash
# Whole `docker run` time of fresh containers under the Development runtime restrictions, next to
# the time the process itself reports, so the part spent outside the process can be seen.
# usage: cold_total.sh <tag> <reps> <unit>...      (unit "noop" runs the image with a bad verb)
set -u
export MSYS_NO_PATHCONV=1
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
R=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd))
IMG=agenthon-track3:$1; N=$2; shift 2
OUTFS=${COLD_OUT:-tmpfs}
for u in "$@"; do
    line="$u:"
    for i in $(seq 1 $N); do
        if [ "$OUTFS" = tmpfs ]; then OM="--tmpfs /output:size=600m,uid=65534"; else rm -rf "$ROOT/lab/bench/_cold_out"; mkdir -p "$ROOT/lab/bench/_cold_out"; OM="-v $R/lab/bench/_cold_out:/output"; fi
        if [ "$u" = noop ]; then ARGS="nothing"; IN="-v $R/track3-simulation-public-clone/units/t3-as01-base-mix:/input:ro"; else ARGS="simulate --config /input/scenario.json --out /output/trace.parquet"; IN="-v $R/track3-simulation-public-clone/units/$u:/input:ro"; fi
        s=$(date +%s%N)
        docker run --rm --network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 --memory 16g --cap-drop ALL --tmpfs /tmp:size=64m,noexec ${EXTRA:-} $OM $IN $IMG $ARGS > /dev/null 2>&1
        e=$(date +%s%N)
        line="$line $(( (e-s)/1000000 ))"
    done
    echo "$line"
done
