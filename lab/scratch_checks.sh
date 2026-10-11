#!/bin/bash
# Checks of a scratch image (launcher only) before it is pushed.
#   bash lab/scratch_checks.sh <scratch tag> <full tag it was built from>
# binary identity with the validated full image, the 6 batch units under the runtime restrictions,
# the organizers' regression suite, and the six units that need no ledger.
set -u
export MSYS_NO_PATHCONV=1
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
R=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd))
cd "$ROOT"
S=agenthon-track3:$1; F=agenthon-track3:$2
O=lab/bench/val_$1; rm -rf $O; mkdir -p $O
a=$(docker run --rm $F sha256sum /usr/local/bin/simulate | cut -c1-64)
c=$(docker create $S); docker cp $c:/usr/local/bin/simulate $O/simulate.bin >/dev/null; docker rm $c >/dev/null
b=$(sha256sum $O/simulate.bin | sed 's/^\\//' | cut -c1-64); rm -f $O/simulate.bin
[ "$a" = "$b" ] && echo "binary identical to $2: yes" || echo "binary identical to $2: NO ($a / $b)"
for unit in track3-simulation-public-clone/units/t3-gbatch-*; do
  u=$(basename $unit); mkdir -p $O/batch/$u
  docker run --rm --network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 --memory 16g --cap-drop ALL \
    --security-opt no-new-privileges --tmpfs /tmp:size=64m,noexec -v "$R/$unit/scenarios:/input/scenarios:ro" \
    -v "$R/$O/batch/$u:/output" $S simulate-batch --batch-dir /input/scenarios --out-dir /output > /dev/null 2> $O/batch_$u.err || echo "FAILED $u"
done
docker run --rm -v "$R/$O/batch:/new:ro" -v "$R/repro/out/batch_candidate:/old:ro" -v "$R/native/engine:/eng:ro" $F python /eng/check_batch_tables.py /new /old | tail -1
IMAGE=$S OUT=$ROOT/repro/out_$1 bash repro/repro.sh official > $O/official.log 2>&1; echo "official rc=$? $(grep total_scenarios $O/official.log | tail -1)"
bash lab/check_skip.sh $1 2>&1 | tail -1
