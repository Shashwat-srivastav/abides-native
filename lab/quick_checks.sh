#!/bin/bash
# Fast correctness checks of a full image before the long validation.
#   bash lab/quick_checks.sh <tag> [reference tag for the negative-latency cases, default sub13]
# 1. tables of the 65 public scenarios against the stored reference outputs
# 2. the six units that need no ledger (lab/check_skip.sh)
# 3. repeat-run byte stability, and equality with the files written without writer threads
# 4. the stored fuzz cases with a negative latency (lab/bench/failcases), launcher only and with no
#    Python reachable, against the same cases run by the reference tag
set -u
export MSYS_NO_PATHCONV=1
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
R=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd))
cd "$ROOT"
IMG=agenthon-track3:$1; REF=agenthon-track3:${2:-sub13}
echo "== tables"; docker run --rm --cpus 4 -v "$R/track3-upstream/regression_suite/scenarios:/sc:ro" -v "$R/repro/out/candidate:/stored:ro" -v "$R/native/engine:/eng:ro" $IMG python /eng/check_fast.py /sc /stored 2>&1 | tail -1
echo "== no-ledger units"; bash lab/check_skip.sh $1 2>&1 | tail -1
echo "== byte stability"; docker run --rm --cpus 4 -v "$R/track3-upstream/regression_suite/scenarios:/sc:ro" $IMG sh -c 'for n in gb_mega_throughput mr_deep_book_state_size eq_deterministic_baseline mp05_cancel_churn_newest as01_base_mix; do a=""; ok=1; for i in 1 2 3 4 5 6; do rm -rf /dev/shm/o; simulate --config /sc/$n.json --out /dev/shm/o/trace.parquet >/dev/null 2>&1; h=$(sha256sum /dev/shm/o/trace.parquet /dev/shm/o/message_trace.parquet | cut -c1-16 | tr "\n" " "); [ -z "$a" ] && a="$h"; [ "$a" = "$h" ] || ok=0; done; rm -rf /dev/shm/o; T3_TRAIL=0 simulate --config /sc/$n.json --out /dev/shm/o/trace.parquet >/dev/null 2>&1; h=$(sha256sum /dev/shm/o/trace.parquet /dev/shm/o/message_trace.parquet | cut -c1-16 | tr "\n" " "); [ "$a" = "$h" ] && same=1 || same=0; echo "$n stable=$ok same_without_writer_threads=$same"; done'
echo "== negative-latency cases"
O=lab/bench/fc_out; rm -rf $O; mkdir -p $O/ref $O/new $O/new_nt
RUNALL='n=0; for f in /fc/*.json; do b=$(basename $f .json); PATH=/nonexistent /usr/local/bin/simulate --config $f --out /o/$b/trace.parquet >/dev/null 2>/o/$b.err && n=$((n+1)); done; echo "handled by the launcher itself: $n of $(ls /fc | wc -l)"'
docker run --rm -v "$R/lab/bench/failcases:/fc:ro" -v "$R/$O/ref:/o" $REF sh -c "$RUNALL" | sed "s/^/reference ${2:-sub13}: /"
docker run --rm -v "$R/lab/bench/failcases:/fc:ro" -v "$R/$O/new:/o" $IMG sh -c "$RUNALL" | sed "s/^/$1: /"
docker run --rm -e T3_TRAIL=0 -v "$R/lab/bench/failcases:/fc:ro" -v "$R/$O/new_nt:/o" $IMG sh -c "$RUNALL" | sed "s/^/$1 without writer threads: /"
docker run --rm -v "$R/$O:/o:ro" -v "$R/native/engine:/eng:ro" $REF python /eng/cmp_dirs.py /o/ref /o/new | tail -2 | sed "s/^/against the reference: /"
docker run --rm -v "$R/$O:/o:ro" -v "$R/native/engine:/eng:ro" $REF python /eng/cmp_dirs.py /o/ref /o/new_nt | tail -2 | sed "s/^/without writer threads, against the reference: /"
