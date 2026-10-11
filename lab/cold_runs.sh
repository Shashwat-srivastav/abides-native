#!/bin/bash
# One fresh container per run, started the way the harness starts a unit (runtime restrictions,
# /input = the unit directory, output on a bind mount), with the launcher's phase line captured.
# This is the cold case the leaderboard measures; loops inside one container measure a warm one.
#   bash lab/cold_runs.sh <tag> <repeats> <unit> [docker run options...]
set -u
export MSYS_NO_PATHCONV=1
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
R=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd))
cd "$ROOT"
tag=$1; reps=$2; unit=$3; shift 3
O=lab/bench/cold_out; mkdir -p $O
# COLD_OUT=tmpfs writes the output to memory instead of the (slow, Windows-backed) bind mount.
OUTMOUNT="-v $R/$O:/output"
[ "${COLD_OUT:-}" = tmpfs ] && OUTMOUNT="--mount type=tmpfs,destination=/output,tmpfs-mode=1777"
for i in $(seq $reps); do
  rm -rf $O/*
  docker run --rm --network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 --memory 16g --cap-drop ALL \
    --security-opt no-new-privileges --tmpfs /tmp:size=64m,noexec -e T3_PHASES=1 "$@" \
    -v "$R/track3-simulation-public-clone/units/$unit:/input:ro" $OUTMOUNT \
    agenthon-track3:$tag simulate --config /input/scenario.json --out /output/trace.parquet 2>&1 >/dev/null \
    | grep -E "^parse=|^res:" | sed -E 's/ \| reserved.*//; s/ \| trace finish.*//' | tr '\n' ' '
  echo
done
