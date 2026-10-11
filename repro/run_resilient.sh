#!/usr/bin/env bash
# Run the reproduction steps on a machine where Docker Desktop itself may crash (low host memory):
# each step is retried, baseline/candidate resume where they stopped, and Docker Desktop is
# restarted when the daemon is gone. Everything is logged with step markers.
#
#   IMAGE=agenthon-track3:sub4 bash repro/run_resilient.sh <logfile> step1 step2 ...
set -u
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LOG=$1; shift
DOCKER_EXE="${DOCKER_DESKTOP_EXE:-/c/Users/$USERNAME/AppData/Local/Programs/DockerDesktop/Docker Desktop.exe}"

ensure_docker() {
    docker version --format '{{.Server.Version}}' >/dev/null 2>&1 && return 0
    echo "#### docker daemon not reachable, starting Docker Desktop  $(date +%H:%M:%S)" >> "$LOG"
    [ -x "$DOCKER_EXE" ] && ("$DOCKER_EXE" >/dev/null 2>&1 &)
    for _ in $(seq 1 60); do
        docker version --format '{{.Server.Version}}' >/dev/null 2>&1 && { echo "#### docker is up  $(date +%H:%M:%S)" >> "$LOG"; return 0; }
        ping -n 6 127.0.0.1 >/dev/null 2>&1 || ping -c 5 127.0.0.1 >/dev/null 2>&1
    done
    return 1
}

for step in "$@"; do
    tries=0
    while :; do
        tries=$((tries + 1))
        ensure_docker || { echo "######## ABORT: docker would not start" >> "$LOG"; exit 1; }
        echo "######## STEP $step try $tries  $(date +%H:%M:%S)" >> "$LOG"
        RESUME=1 bash "$ROOT/repro/repro.sh" "$step" >> "$LOG" 2>&1
        rc=$?
        echo "######## END $step try $tries rc=$rc  $(date +%H:%M:%S)" >> "$LOG"
        # rc 0 = done; a step that fails while docker is still healthy is a real failure: stop retrying
        if [ $rc -eq 0 ]; then break; fi
        if docker version --format '{{.Server.Version}}' >/dev/null 2>&1 && [ "$step" != baseline ] && [ "$step" != candidate ] && [ "$step" != batch ] && [ "$step" != rng ]; then break; fi
        [ $tries -ge 8 ] && break
    done
done
grep "^######## " "$LOG"
