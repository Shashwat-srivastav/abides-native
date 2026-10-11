#!/usr/bin/env bash
# Reproduce the Track 3 results: build, correctness (byte identity), official regression, batch units,
# RNG bit-exactness, and throughput. Works in Git Bash on Windows and in bash on Linux.
#
#   bash repro/repro.sh <step> [args]
#
# Steps (run in this order the first time):
#   env                 print toolchain versions and check prerequisites
#   build               build the submission image  -> $IMAGE  (default agenthon-track3:repro)
#   baseline            run the ORIGINAL ABIDES image on all 65 public scenarios  -> out/baseline
#   candidate           run the submission image on all 65 scenarios               -> out/candidate
#   identity            compare candidate vs baseline (byte identity + events/s)   (needs both above)
#   batch               baseline + candidate on the 6 batch units, then compare    -> out/batch_*
#   official            organizer's run_regression.py on the submission image      -> out/official
#   rng                 numpy-RandomState bit-exactness matrix for the C++ RNG (about 10 min)
#   ab [rounds]         interleaved throughput A/B: baseline vs candidate images (self-reported events/s)
#   all                 env build baseline candidate identity batch official
#
# Environment overrides:
#   IMAGE           submission image tag to build/test   (default agenthon-track3:repro)
#   BASELINE_IMAGE  original ABIDES image                (default slashalpha/agenthon-track3:dev)
#   PUBLIC_REPO     track3-simulation-public checkout with scenarios, units and reference traces
#                   (default <root>/track3-simulation-public-clone)
#   HARNESS_REPO    current organizer harness for `official`   (default <root>/track3-upstream)
#   TOOLKIT         qfbench2_common checkout, tag v2.5.1       (default <root>/toolkit-v2.5.1/common)
#   ONLY            comma-separated scenario stems to restrict baseline/candidate (quick runs)
#   RESUME=1        baseline/candidate keep scenarios already finished by an interrupted run
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=${OUT:-$ROOT/repro/out}
IMAGE=${IMAGE:-agenthon-track3:repro}
BASELINE_IMAGE=${BASELINE_IMAGE:-slashalpha/agenthon-track3:dev}
PUBLIC_REPO=${PUBLIC_REPO:-$ROOT/track3-simulation-public-clone}
HARNESS_REPO=${HARNESS_REPO:-$ROOT/track3-upstream}
TOOLKIT=${TOOLKIT:-$ROOT/toolkit-v2.5.1/common}
SCEN=$PUBLIC_REPO/regression_suite/scenarios
UNITS=$PUBLIC_REPO/units
ONLY=${ONLY:-}
export MSYS_NO_PATHCONV=1   # Git Bash: do not rewrite /container/paths

# Docker on Windows wants E:/... style mount sources; on Linux the path is used as-is.
dpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }
pysep() { if command -v cygpath >/dev/null 2>&1; then echo ";"; else echo ":"; fi; }
mkdir -p "$OUT"

run_all_in_container() {  # <image> <mode> <outdir>
    local image=$1 mode=$2 out=$3
    local resume=""
    if [ "${RESUME:-0}" = 1 ]; then resume="--resume"; else rm -rf "$out"; fi
    mkdir -p "$out"
    docker run --rm --network none \
        -v "$(dpath "$SCEN"):/scenarios:ro" -v "$(dpath "$out"):/out" \
        -v "$(dpath "$ROOT/repro"):/repro:ro" \
        "$image" python /repro/in_container_run.py --mode "$mode" --out /out --only "$ONLY" $resume
}

step_env() {
    echo "root:            $ROOT"
    echo "public repo:     $PUBLIC_REPO ($(git -C "$PUBLIC_REPO" rev-parse HEAD 2>/dev/null || echo 'not a git checkout'))"
    echo "scenarios:       $(ls "$SCEN"/*.json | grep -vc index.json) (expect 65)"
    echo "batch units:     $(ls -d "$UNITS"/t3-gbatch-* | wc -l) (expect 6)"
    echo "docker:          $(docker version --format '{{.Server.Version}}')"
    echo "python (host):   $(python --version 2>&1)"
    echo "harness repo:    $HARNESS_REPO ($(git -C "$HARNESS_REPO" rev-parse --short HEAD 2>/dev/null || echo missing))"
    echo "toolkit:         $TOOLKIT ($(git -C "$TOOLKIT/.." describe --tags 2>/dev/null || echo missing))"
}

step_build() {
    docker build --platform=linux/amd64 -t "$IMAGE" "$(dpath "$ROOT/sub")"
    echo "built $IMAGE: $(docker inspect --format '{{.Id}}' "$IMAGE")"
}

step_baseline()  { docker pull "$BASELINE_IMAGE" >/dev/null 2>&1 || true; run_all_in_container "$BASELINE_IMAGE" reference "$OUT/baseline"; }
step_candidate() { run_all_in_container "$IMAGE" submission "$OUT/candidate"; }
step_identity()  { python "$(dpath "$ROOT/repro/compare.py")" "$(dpath "$OUT/baseline")" "$(dpath "$OUT/candidate")" --json "$(dpath "$OUT/identity.json")"; }

step_batch() {
    for which in baseline candidate; do
        local image=$BASELINE_IMAGE; [ "$which" = candidate ] && image=$IMAGE
        for unit in "$UNITS"/t3-gbatch-*; do
            local u; u=$(basename "$unit"); local o="$OUT/batch_$which/$u"
            rm -rf "$o"; mkdir -p "$o"
            docker run --rm --network none -v "$(dpath "$unit/scenarios"):/input/scenarios:ro" \
                -v "$(dpath "$o"):/output" "$image" \
                simulate-batch --batch-dir /input/scenarios --out-dir /output > /dev/null
            echo "$which $u done"
        done
    done
    python "$(dpath "$ROOT/repro/compare.py")" "$(dpath "$OUT/batch_baseline")" "$(dpath "$OUT/batch_candidate")" --json "$(dpath "$OUT/batch.json")"
}

step_official() {
    # One worker: the harness itself needs ~200 MB per worker and the large scenarios ~2 GB in Docker.
    # HARNESS_REPO = current organizer harness; TOOLKIT = qfbench2_common (v2.5.1) checkout; the
    # reference traces come from PUBLIC_REPO. BLAS threads are limited to keep the harness small.
    rm -rf "$OUT/official"
    ( cd "$HARNESS_REPO" && OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
        PYTHONPATH=".$(pysep)$(dpath "$TOOLKIT")$(pysep)${PYTHONPATH:-}" python regression_suite/run_regression.py \
        --candidate-image "$IMAGE" --scenarios-dir regression_suite/scenarios \
        --reference-dir "$(dpath "$PUBLIC_REPO/regression_suite/reference_traces")" \
        --output-dir "$(dpath "$OUT/official")" --workers 1 )
    python - "$(dpath "$OUT/official/report.json")" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
print({k: r[k] for k in r if k != "results"})
EOF
}

step_rng() {
    docker build -q -t t3-rng-test -f "$(dpath "$ROOT/repro/Dockerfile.rng")" "$(dpath "$ROOT/repro")" > /dev/null
    docker run --rm -v "$(dpath "$ROOT/native/rng"):/rng" t3-rng-test bash /rng/run_all.sh
}

step_ab() {
    local rounds=${1:-3}
    for r in $(seq 1 "$rounds"); do
        for which in baseline candidate; do
            local image=$BASELINE_IMAGE mode=reference
            [ "$which" = candidate ] && image=$IMAGE && mode=submission
            run_all_in_container "$image" "$mode" "$OUT/ab/$which-$r" > /dev/null
            python - "$(dpath "$OUT/ab/$which-$r/summary.json")" "$which" "$r" <<'EOF'
import json, statistics, sys
rows = json.load(open(sys.argv[1]))
e = [r["events_per_sec"] for r in rows]
print(f"round {sys.argv[3]} {sys.argv[2]:9s} mean {statistics.mean(e):>14,.0f}  median {statistics.median(e):>14,.0f}  units {len(e)}")
EOF
        done
    done
}

case "${1:-}" in
    env) step_env ;;
    build) step_build ;;
    baseline) step_baseline ;;
    candidate) step_candidate ;;
    identity) step_identity ;;
    batch) step_batch ;;
    official) step_official ;;
    rng) step_rng ;;
    ab) shift; step_ab "${1:-3}" ;;
    all) step_env; step_build; step_baseline; step_candidate; step_identity; step_batch; step_official ;;
    *) sed -n '2,27p' "$0"; exit 2 ;;
esac
