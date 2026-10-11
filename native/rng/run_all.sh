#!/bin/bash
# Full bit-exactness matrix. Run inside t3-native-dev:  bash run_all.sh [N_BULK] [N_MIXED] [N_CHAIN]
set -u
NB=${1:-1000000}; NM=${2:-2000000}; NC=${3:-100000}
CXXFLAGS=${CXXFLAGS:-"-std=c++17 -O2 -ffp-contract=off"}
cd "$(dirname "$0")"
g++ $CXXFLAGS -o /tmp/test_rng test_rng.cpp || exit 2
echo "flags: $CXXFLAGS"
fail=0
BULK_SEEDS="0 1 2 42 2147483647 2147483648 4294967295 3141592653 271828182 1618033988 987654321 123456789"
MIXED_SEEDS="0 1 4294967295 20240927 3735928559 7"
CHAIN_SEEDS="0 1 2 3 4 5 42 1000 65535 65536 123456 999999 2147483647 2147483648 4294967294 4294967295 17 31337 8675309 1234567890"
for s in $BULK_SEEDS; do
  python gen_ref.py bulk $s $NB /tmp/ref.bin >/dev/null || fail=1
  /tmp/test_rng /tmp/ref.bin | tail -1 | sed "s|^|bulk seed=$s: |" ; [ ${PIPESTATUS[0]} -eq 0 ] || fail=1
  rm -f /tmp/ref.bin
done
for s in $MIXED_SEEDS; do
  python gen_ref.py mixed $s $NM /tmp/ref.bin >/dev/null || fail=1
  /tmp/test_rng /tmp/ref.bin | tail -1 | sed "s|^|mixed seed=$s: |" ; [ ${PIPESTATUS[0]} -eq 0 ] || fail=1
  rm -f /tmp/ref.bin
done
for s in $CHAIN_SEEDS; do
  python gen_ref.py chain $s $NC /tmp/ref.bin >/dev/null || fail=1
  /tmp/test_rng /tmp/ref.bin | tail -1 | sed "s|^|chain seed=$s: |" ; [ ${PIPESTATUS[0]} -eq 0 ] || fail=1
  rm -f /tmp/ref.bin
done
echo "OVERALL: $([ $fail -eq 0 ] && echo PASS || echo FAIL)"
exit $fail
