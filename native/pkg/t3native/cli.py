"""``simulate`` verb: native engine first, exact ABIDES reference path on any unsupported input."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


def simulate(config: str, out: str, seed: Optional[int] = None) -> dict:
    from t3native import native_sim

    try:
        return native_sim.simulate(config, out, seed)
    except Exception as exc:  # any native-side surprise: the reference path is always exact
        print(f"t3native: falling back to ABIDES reference ({type(exc).__name__}: {exc})", file=sys.stderr)
    from abides_fork.simulate import simulate as reference_simulate

    return reference_simulate(config, out, seed)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="simulate")
    ap.add_argument("verb", nargs="?", default="simulate", choices=["simulate"])
    ap.add_argument("--config", required=True, help="path to scenario.json")
    ap.add_argument("--out", required=True, help="output path for trace.parquet")
    ap.add_argument("--seed", type=int, default=None, help="override scenario seed")
    args = ap.parse_args(argv)
    print(json.dumps(simulate(args.config, args.out, args.seed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
