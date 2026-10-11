#!/bin/bash
# usage: run_reg.sh <image> <outdir>
cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../track3-simulation-public-clone"
export PYTHONPATH=".;../toolkit-v2.5.1/common"
python regression_suite/run_regression.py --candidate-image "$1" --scenarios-dir ../lab/sc_small --output-dir "$2/small" --workers 3 > "$2.small.log" 2>&1
python regression_suite/run_regression.py --candidate-image "$1" --scenarios-dir ../lab/sc_large --output-dir "$2/large" --workers 1 > "$2.large.log" 2>&1
echo done
