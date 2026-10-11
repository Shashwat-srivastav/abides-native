#!/bin/bash
# Byte comparison of two launcher binaries on every single-scenario unit directory (run inside the
# dev container). usage: cmp_bins.sh <ref binary> <new binary> [env assignments for the new one]
REF=$1; NEW=$2; shift 2
ok=0; bad=0
for d in /units/*/; do
  u=$(basename $d); [ -f $d/scenario.json ] || continue; case $u in *EXAMPLE*) continue;; esac
  rm -rf /dev/shm/a /dev/shm/b
  T3_HUGE=0 T3_PREFAULT=0 $REF simulate --config $d/scenario.json --out /dev/shm/a/trace.parquet >/dev/null 2>&1 || { echo "REF FAILED $u"; continue; }
  env T3_HUGE=0 T3_PREFAULT=0 "$@" $NEW simulate --config $d/scenario.json --out /dev/shm/b/trace.parquet >/dev/null 2>/dev/shm/b.err || { echo "NEW FAILED $u"; bad=$((bad+1)); continue; }
  ha=$(cd /dev/shm/a && sha256sum *.parquet | sha256sum); hb=$(cd /dev/shm/b && sha256sum *.parquet | sha256sum)
  if [ "$ha" = "$hb" ]; then ok=$((ok+1)); else bad=$((bad+1)); echo "DIFF $u"; fi
done
echo "identical $ok, different or failed $bad"
