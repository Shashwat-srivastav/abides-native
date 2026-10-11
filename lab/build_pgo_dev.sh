#!/bin/bash
# The image's profile-guided launcher build (sub/Dockerfile), run inside the dev container.
# usage: build_pgo_dev.sh <output binary>
set -e
rm -rf /tmp/pgob && mkdir -p /tmp/pgob && cp -r /native/engine /native/rng /tmp/pgob/ 2>/dev/null
cd /tmp/pgob/engine
F="-std=c++17 -ffp-contract=off -pthread"
g++ -O3 $F -fprofile-generate -fprofile-update=atomic -DT3_PGO_GEN -c launcher.cpp -o launcher.o
g++ -O3 $F -fprofile-generate -static launcher.o -o /tmp/t3gen
for f in pgo_train/flat/*.json pgo_train/t3-gb-*/scenario.json; do
  rm -rf /tmp/pgo_out; /tmp/t3gen simulate --config "$f" --out /tmp/pgo_out/trace.parquet > /dev/null
done
g++ -O3 $F -fprofile-use -fprofile-partial-training -fprofile-correction -Wno-missing-profile -c launcher.cpp -o launcher.o
g++ -O3 $F -static launcher.o -o "$1"
ls -la "$1"
