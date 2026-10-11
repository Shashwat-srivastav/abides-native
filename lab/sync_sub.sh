#!/bin/sh
# Sync native sources into the submission tree (single source of truth: native/).
set -e
cd "$(dirname "$0")/.."
rm -rf sub/native sub/t3native
mkdir -p sub/native/engine sub/native/rng sub/t3native
cp native/engine/engine.cpp native/engine/launcher.cpp native/engine/pq_fast.hpp native/engine/sha256.hpp native/engine/build.sh sub/native/engine/
cp -r native/engine/pgo_train sub/native/engine/
cp native/rng/np_random.hpp sub/native/rng/
cp native/pkg/t3native/*.py sub/t3native/
cp -r native/pkg/t3native/batch.py sub/t3native/ 2>/dev/null || true
