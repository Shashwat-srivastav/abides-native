#!/bin/bash
# The last-resort ABIDES path under the benchmark's runtime restrictions (read-only root, uid 65534,
# 64 MiB noexec /tmp, no network): forces it with T3_NO_LAUNCHER=1 T3_FORCE_REFERENCE=1 on one
# single unit and one batch unit, and compares the tables with the unit's reference outputs.
#   bash lab/ref_path_check.sh <tag>
set -u
export MSYS_NO_PATHCONV=1
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
R=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd))
cd "$ROOT"
IMG=agenthon-track3:$1; O=lab/bench/refpath_$1; rm -rf $O; mkdir -p $O/single $O/batch
U=track3-simulation-public-clone/units
RUN="docker run --rm --network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 --memory 16g --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:size=64m,noexec -e T3_NO_LAUNCHER=1 -e T3_FORCE_REFERENCE=1"
$RUN -v "$R/$U/t3-s001-price-time-priority:/input:ro" -v "$R/$O/single:/output" $IMG \
  simulate --config /input/scenario.json --out /output/trace.parquet > $O/single.out 2> $O/single.err
echo "single rc=$? files=$(ls $O/single | tr '\n' ' ')"; grep -i "error\|read-only\|falling back" $O/single.err | head -3
$RUN -v "$R/$U/t3-gbatch-dense-3/scenarios:/input/scenarios:ro" -v "$R/$O/batch:/output" $IMG \
  simulate-batch --batch-dir /input/scenarios --out-dir /output > $O/batch.out 2> $O/batch.err
echo "batch rc=$? entries=$(ls $O/batch | wc -l)"; grep -i "error\|read-only" $O/batch.err | head -3
docker run --rm -v "$R/$O/single:/new:ro" -v "$R/$U/t3-s001-price-time-priority:/ref:ro" $IMG python -c "
import pyarrow.parquet as pq
for f in ('trace.parquet', 'message_trace.parquet'):
    try:
        a = pq.read_table('/new/' + f); b = pq.read_table('/ref/' + f)
        print(f, 'rows', a.num_rows, 'equal to reference:', a.equals(b))
    except Exception as e:
        print(f, 'not compared:', type(e).__name__, e)
"
