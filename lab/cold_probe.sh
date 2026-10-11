#!/bin/bash
# Whole `docker run` time of fresh containers for arbitrary commands in the full image, to see
# which kind of work (time, memory, threads, output bytes) costs extra outside the process.
# usage: cold_probe.sh <tag> <reps>      (commands are listed below)
set -u
export MSYS_NO_PATHCONV=1
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)
R=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd))
IMG=agenthon-track3:$1; N=$2
U=$R/track3-simulation-public-clone/units
run() {  # label unit command...
    local label=$1 unit=$2; shift 2
    local line="$label:"
    for i in $(seq 1 $N); do
        s=$(date +%s%N)
        docker run --rm --network none --read-only --user 65534:65534 --pids-limit 256 --cpus 4 --memory 16g --cap-drop ALL --tmpfs /tmp:size=64m,noexec ${EXTRA:-} --tmpfs /output:size=600m,uid=65534 -v "$U/$unit:/input:ro" $IMG "$@" > /dev/null 2>&1
        e=$(date +%s%N)
        line="$line $(( (e-s)/1000000 ))"
    done
    echo "$line"
}
A=t3-as01-base-mix
run true $A true
run sleep0.1 $A sleep 0.1
run write8MB $A sh -c 'head -c 8000000 /dev/zero > /output/x'
run python $A python -c 'pass'
run py_mem60MB $A python -c 'x=bytearray(60000000)'
run py_threads $A python -c 'import threading,time
for _ in range(6): threading.Thread(target=time.sleep,args=(0.02,)).start()'
run py_spin4x50ms $A python -c 'import os,time
for _ in range(3):
    if os.fork()==0:
        t=time.time()
        while time.time()-t<0.05: pass
        os._exit(0)
t=time.time()
while time.time()-t<0.05: pass'
run sim_as01 $A simulate --config /input/scenario.json --out /output/trace.parquet
run sim_as01_nohelp $A env T3_FEED=0 simulate --config /input/scenario.json --out /output/trace.parquet
run true $A true
