#!/bin/bash
# Full validation of a submission image: tables (65), repeat-run bytes, batch (6, runtime
# restrictions), official regression, stored fuzz corpus.  usage: validate_image.sh <tag> <outdir>
set -u
export MSYS_NO_PATHCONV=1
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
# Docker on Windows needs a drive-letter path for bind mounts (Git Bash: pwd -W).
R=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd))
cd "$ROOT"
IMG=agenthon-track3:$1; O=lab/bench/val_$1; rm -rf $O; mkdir -p $O
echo "== tables 65"; docker run --rm --cpus 4 -v "$R/track3-upstream/regression_suite/scenarios:/sc:ro" -v "$R/repro/out/candidate:/stored:ro" -v "$R/native/engine:/eng:ro" $IMG python /eng/check_fast.py /sc /stored > $O/tables.log 2>&1; echo "rc=$? $(tail -1 $O/tables.log)"
echo "== repeat-run bytes"; docker run --rm --cpus 4 -v "$R/track3-upstream/regression_suite/scenarios:/sc:ro" $IMG sh -c 'ok=0; bad=0; for f in /sc/*.json; do n=$(basename $f .json); [ $n = index ] && continue; a=""; same=1; for i in 1 2 3; do rm -rf /dev/shm/o; simulate --config $f --out /dev/shm/o/trace.parquet >/dev/null 2>&1; h=$(sha256sum /dev/shm/o/trace.parquet /dev/shm/o/message_trace.parquet | cut -c1-64 | tr "\n" " "); [ -z "$a" ] && a="$h"; [ "$a" = "$h" ] || same=0; done; if [ $same = 1 ]; then ok=$((ok+1)); else bad=$((bad+1)); echo "DIFF $n"; fi; done; echo "identical across 3 runs: $ok, differing: $bad"' 2>&1 | tail -3
echo "== batch 6 under restrictions"; for unit in track3-simulation-public-clone/units/t3-gbatch-*; do u=$(basename $unit); mkdir -p $O/batch/$u; docker run --rm --network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 --tmpfs /tmp:size=64m,noexec -v "$R/$unit/scenarios:/input/scenarios:ro" -v "$R/$O/batch/$u:/output" $IMG simulate-batch --batch-dir /input/scenarios --out-dir /output > /dev/null 2> $O/batch_$u.err || echo "FAILED $u"; done
docker run --rm -v "$R/$O/batch:/new:ro" -v "$R/repro/out/batch_candidate:/old:ro" -v "$R/native/engine:/eng:ro" $IMG python /eng/check_batch_tables.py /new /old | tail -1
echo "== single + forced fallback under restrictions"; for env in T3_X=0 T3_NO_LAUNCHER=1; do rm -rf $O/rt; mkdir -p $O/rt; docker run --rm --network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 --tmpfs /tmp:size=64m,noexec -e $env -v "$R/track3-upstream/regression_suite/scenarios:/input:ro" -v "$R/$O/rt:/output" $IMG simulate --config /input/mp07_heavy_flow_oldest.json --out /output/trace.parquet > /dev/null 2>&1; echo "$env rc=$? files=$(ls $O/rt | wc -l)"; done
echo "== official regression"; IMAGE=$IMG OUT=$ROOT/repro/out_$1 bash repro/repro.sh official > $O/official.log 2>&1; echo "rc=$? $(grep "total_scenarios" $O/official.log | tail -1)"
echo "== fuzz corpus"; docker run --rm --cpus 4 -v "$R/native/fuzz:/fz:ro" $IMG python /fz/recheck_stored.py /fz > $O/fuzz.log 2>&1; echo "rc=$?"; tail -4 $O/fuzz.log
echo "== DONE"
