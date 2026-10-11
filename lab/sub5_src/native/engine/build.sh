#!/bin/sh
# Builds libt3engine.so next to the t3native package. -ffp-contract=off is REQUIRED for bit-exactness.
set -e
cd "$(dirname "$0")"
g++ -O2 -std=c++17 -ffp-contract=off -fPIC -shared -pthread -o ../pkg/t3native/libt3engine.so engine.cpp
