#!/bin/bash
# Build the full image <tag> from an engine variant file, leaving native/ as it was.
# usage: build_variant.sh <tag> <engine source file>
cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.."
cp native/engine/engine.cpp lab/bench/_engine_keep.cpp
cp "$2" native/engine/engine.cpp && bash lab/sync_sub.sh
cp lab/bench/_engine_keep.cpp native/engine/engine.cpp && rm lab/bench/_engine_keep.cpp
(cd sub && docker build --build-arg T3_TRAIL=0 -t agenthon-track3:$1 . > ../lab/bench/build_$1.log 2>&1) && echo "built $1" || echo "BUILD FAILED $1"
