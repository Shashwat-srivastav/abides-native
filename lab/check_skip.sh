#!/bin/bash
# Units whose card says requires_message_ledger = false: run the image the way the harness mounts a
# unit (/input = the unit directory), once reading the card and once with T3_LEDGER=1, then compare.
#   bash lab/check_skip.sh <tag>
set -u
export MSYS_NO_PATHCONV=1
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
# Docker on Windows needs a drive-letter path for bind mounts (Git Bash: pwd -W).
R=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd))
cd "$ROOT"
IMG=agenthon-track3:$1; O=lab/bench/skip_$1; rm -rf $O; mkdir -p $O
RUN="docker run --rm --network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 --memory 16g --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:size=64m,noexec"
for unit in track3-simulation-public-clone/units/t3-gb-*; do
  u=$(basename $unit)
  for mode in skip full; do
    mkdir -p $O/$mode/$u
    e=0; [ $mode = full ] && e=1
    $RUN -e T3_LEDGER=$e -e T3_PHASES=1 -v "$R/$unit:/input:ro" -v "$R/$O/$mode/$u:/output" $IMG simulate --config /input/scenario.json --out /output/trace.parquet > /dev/null 2> $O/${mode}_$u.err || echo "FAILED $mode $u"
  done
  echo "$u  skip: $(grep -o 'parse=.*out=[0-9.]*' $O/skip_$u.err)  | full: $(grep -o 'parse=.*out=[0-9.]*' $O/full_$u.err)"
done
# A unit whose card requires the ledger must still get one when mounted the same way.
u=t3-mr-deep-book-state-size; mkdir -p $O/req
$RUN -v "$R/track3-simulation-public-clone/units/$u:/input:ro" -v "$R/$O/req:/output" $IMG simulate --config /input/scenario.json --out /output/trace.parquet > /dev/null 2>&1; echo "ledger-required unit $u files: $(ls $O/req | tr '\n' ' ')"
docker run --rm -v "$R/track3-simulation-public-clone/units:/units:ro" -v "$R/$O/skip:/skip:ro" -v "$R/$O/full:/full:ro" -v "$R/native/engine:/eng:ro" agenthon-track3:sub9 python /eng/check_skip.py /units /skip /full
