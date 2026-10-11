#!/bin/sh
# Profile-guided build of libt3engine.so. Semantics are unchanged (same source, same
# -ffp-contract=off); the profile only steers inlining/branch layout. Training inputs are flat
# configs (pgo_bins/*.bin, dumped by dump_cfg.py from public scenarios) run through driver.cpp.
# Usage: build_pgo.sh <out.so> [bins_dir]
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(realpath -m "${1:-$HERE/../pkg/t3native/libt3engine.so}")
BINS=$(realpath "${2:-$HERE/pgo_bins}")
FLAGS="-O3 -std=c++17 -ffp-contract=off -fPIC"
W=$(mktemp -d)
cp "$HERE/engine.cpp" "$HERE/driver.cpp" "$W/"
mkdir -p "$W/rng" && cp "$HERE/../rng/np_random.hpp" "$W/rng/"
sed -i 's#"../rng/np_random.hpp"#"rng/np_random.hpp"#' "$W/engine.cpp"
cd "$W"
g++ $FLAGS -fprofile-generate -fprofile-update=single -c engine.cpp -o engine.o
g++ -O2 -fprofile-generate driver.cpp engine.o -o drv
for b in "$BINS"/*.bin; do ./drv "$b" > /dev/null; done
g++ $FLAGS -fprofile-use -fprofile-partial-training -Wno-missing-profile -c engine.cpp -o engine.o
g++ -shared engine.o -o "$OUT"
cd / && rm -rf "$W"
echo "built $OUT (PGO, trained on $(ls "$BINS"/*.bin | wc -l) configs)"
