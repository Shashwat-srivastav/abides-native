#!/bin/bash
# Build the full image <tag> (writer threads off) and run the whole validation; log in lab/bench.
# usage: build_validate.sh <tag>
cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.."
(cd sub && docker build --build-arg T3_TRAIL=0 -t agenthon-track3:$1 . > ../lab/bench/build_$1.log 2>&1) || { echo "BUILD FAILED" > lab/bench/validate_$1.log; exit 1; }
bash lab/validate_image.sh $1 > lab/bench/validate_$1.log 2>&1
