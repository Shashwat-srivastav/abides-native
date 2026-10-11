#!/usr/bin/env python3
"""first_divergence.py -- locate the first event where two engines diverge.

Dump mode (streams both files, constant memory apart from the context window):

    python first_divergence.py A.tsv B.tsv [--types D,S,R,W,E,F,K] [--context 10] [--no-tail-count]

    Compares records (lines not starting with '#') in order.  Reports the first differing
    record: its line numbers in A and B, its per-type ordinal, which named fields differ
    (hex floats are also shown in decimal), +-N records of context from both files, and
    per-record-type counts for both files.  --types restricts the comparison to the listed
    record types (records of other types are skipped in BOTH files before pairing).

Trace mode:

    python first_divergence.py --traces dirA dirB [--context 3]

    Compares dirA/trace.parquet vs dirB/trace.parquet and dirA/message_trace.parquet vs
    dirB/message_trace.parquet: sha256, schema (columns + dtypes), row counts, and the first
    differing row (every differing column with both values, plus context rows).

Exit status: 0 = identical, 1 = divergence found, 2 = usage / IO error.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import pathlib
import sys
from collections import Counter, deque

SCHEMA = {
    "K": ["start_time", "stop_time", "n_agents", "default_comp_delay"],
    "W": ["t", "agent", "wake_at", "message_id"],
    "D": ["t", "kind", "disp", "sender", "recipient", "msg_class", "message_id",
          "requeue_to", "batch_id", "order_id", "side", "limit_price", "quantity",
          "fill_price", "payload"],
    "S": ["t", "sender", "recipient", "msg_class", "message_id", "comp_delay", "add_delay",
          "delay", "sent_time", "latency_raw", "latency", "deliver_at", "order_id", "side",
          "limit_price", "quantity", "fill_price", "payload"],
    "R": ["t", "owner", "method", "args", "result"],
    "E": ["t", "agent", "event_type", "order_id", "side", "limit_price", "quantity",
          "fill_price", "payload"],
    "F": ["t", "ts", "v_adj", "pt", "pv", "v"],
}


def _records(path, types):
    """Yield (line_no, fields) for every non-comment record whose type is selected."""
    with open(path, "r", encoding="utf-8", newline="\n") as fh:
        for no, line in enumerate(fh, 1):
            if not line or line[0] == "#" or line == "\n":
                continue
            fields = line.rstrip("\n").split("\t")
            if types is not None and fields[0] not in types:
                continue
            yield no, fields


def _dec(v: str) -> str:
    """Decode python float.hex tokens for display: 0x1.8p+1 -> 3.0 (others unchanged)."""
    out = []
    for tok in v.split(","):
        t = tok.lstrip("-")
        if t.startswith("0x") and "p" in t:
            try:
                out.append(repr(float.fromhex(tok)))
                continue
            except ValueError:
                pass
        out.append(tok)
    return ",".join(out)


def _name(rtype: str, i: int) -> str:
    cols = SCHEMA.get(rtype, [])
    return cols[i] if i < len(cols) else f"col{i + 1}"


def _fmt(tag: str, rec) -> str:
    if rec is None:
        return f"  {tag} <EOF>"
    no, f = rec
    return f"  {tag} L{no:<9d} " + "\t".join(f)


def _field_diff(fa, fb):
    lines = []
    if fa[0] != fb[0]:
        lines.append(f"  record type differs: A={fa[0]!r}  B={fb[0]!r}")
        return lines
    rtype = fa[0]
    n = max(len(fa), len(fb))
    if len(fa) != len(fb):
        lines.append(f"  field count differs: A={len(fa) - 1}  B={len(fb) - 1}")
    for i in range(1, n):
        va = fa[i] if i < len(fa) else "<missing>"
        vb = fb[i] if i < len(fb) else "<missing>"
        if va != vb:
            da, db = _dec(va), _dec(vb)
            extra = f"   (decimal: A={da}  B={db})" if (da != va or db != vb) else ""
            lines.append(f"  field {_name(rtype, i - 1)!r}: A={va}  B={vb}{extra}")
    return lines


def compare_dumps(a: str, b: str, types, ctx: int, tail_count: bool) -> int:
    ia, ib = _records(a, types), _records(b, types)
    hist: deque = deque(maxlen=ctx)
    cnt_a, cnt_b = Counter(), Counter()
    idx = 0
    while True:
        ra = next(ia, None)
        rb = next(ib, None)
        if ra is None and rb is None:
            print(f"IDENTICAL: {idx} records compared" + (f" (types {','.join(sorted(types))})" if types else ""))
            _print_counts(cnt_a, cnt_b)
            return 0
        same = ra is not None and rb is not None and ra[1] == rb[1]
        if same:
            cnt_a[ra[1][0]] += 1
            cnt_b[rb[1][0]] += 1
            hist.append((ra, rb))
            idx += 1
            continue
        # ---- divergence --------------------------------------------------------------
        rtype = (ra or rb)[1][0]
        ordinal = (cnt_a if ra is not None else cnt_b)[rtype] + 1
        print(f"FIRST DIVERGENCE at record #{idx + 1} (0-based {idx})"
              + (f", restricted to types {','.join(sorted(types))}" if types else ""))
        print(f"  A: {a} line {ra[0] if ra else 'EOF'}   B: {b} line {rb[0] if rb else 'EOF'}")
        if ra is not None and rb is not None:
            print(f"  record type {ra[1][0]} #{cnt_a[ra[1][0]] + 1} in A, "
                  f"{rb[1][0]} #{cnt_b[rb[1][0]] + 1} in B")
            for ln in _field_diff(ra[1], rb[1]):
                print(ln)
        elif ra is None:
            print(f"  A ended; B continues with a {rtype} record (#{ordinal} of that type)")
        else:
            print(f"  B ended; A continues with a {rtype} record (#{ordinal} of that type)")
        print(f"\n--- {len(hist)} preceding records (identical in A and B; A line numbers) ---")
        for pa, pb in hist:
            print(_fmt("=", pa) + (f"   [B L{pb[0]}]" if pb[0] != pa[0] else ""))
        fut_a = [ra] + list(itertools.islice(ia, ctx)) if ra else []
        fut_b = [rb] + list(itertools.islice(ib, ctx)) if rb else []
        print(f"\n--- A: divergent record + next {ctx} ---")
        for r in fut_a:
            print(_fmt("A", r))
        if not fut_a:
            print(_fmt("A", None))
        print(f"\n--- B: divergent record + next {ctx} ---")
        for r in fut_b:
            print(_fmt("B", r))
        if not fut_b:
            print(_fmt("B", None))
        for r in fut_a:
            cnt_a[r[1][0]] += 1
        for r in fut_b:
            cnt_b[r[1][0]] += 1
        if tail_count:
            for _, f in ia:
                cnt_a[f[0]] += 1
            for _, f in ib:
                cnt_b[f[0]] += 1
            print("\n--- record counts (whole files) ---")
        else:
            print("\n--- record counts (up to divergence + context only; --no-tail-count) ---")
        _print_counts(cnt_a, cnt_b)
        return 1


def _print_counts(ca: Counter, cb: Counter) -> None:
    print(f"  {'type':<5}{'A':>12}{'B':>12}{'B-A':>10}")
    for t in sorted(set(ca) | set(cb)):
        d = cb[t] - ca[t]
        print(f"  {t:<5}{ca[t]:>12}{cb[t]:>12}{d:>+10}")


# ------------------------------------------------------------------------------------------
# trace mode
# ------------------------------------------------------------------------------------------
def _sha(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _compare_table(pa: pathlib.Path, pb: pathlib.Path, ctx: int) -> bool:
    import pandas as pd

    print(f"=== {pa.name} ===")
    if not pa.exists() or not pb.exists():
        print(f"  missing: A={pa.exists()} B={pb.exists()}")
        return False
    sa, sb = _sha(pa), _sha(pb)
    print(f"  sha256 A={sa}\n  sha256 B={sb}  -> {'EQUAL' if sa == sb else 'DIFFERENT'}")
    if sa == sb:
        return True
    da, db = pd.read_parquet(pa), pd.read_parquet(pb)
    ok = True
    if list(da.columns) != list(db.columns):
        print(f"  columns differ: A={list(da.columns)}  B={list(db.columns)}")
        ok = False
    sch_a = {c: str(t) for c, t in da.dtypes.items()}
    sch_b = {c: str(t) for c, t in db.dtypes.items()}
    for c in sorted(set(sch_a) | set(sch_b)):
        if sch_a.get(c) != sch_b.get(c):
            print(f"  dtype differs for {c!r}: A={sch_a.get(c)}  B={sch_b.get(c)}")
            ok = False
    print(f"  rows: A={len(da)}  B={len(db)}" + ("" if len(da) == len(db) else f"  (B-A={len(db) - len(da):+d})"))
    if len(da) != len(db):
        ok = False
    n = min(len(da), len(db))
    common = [c for c in da.columns if c in db.columns]
    first = None
    diff_cols: dict[str, int] = {}
    for c in common:
        a = da[c].iloc[:n].reset_index(drop=True)
        b = db[c].iloc[:n].reset_index(drop=True)
        try:
            eq = a.eq(b).fillna(False) | (a.isna() & b.isna())
        except (TypeError, ValueError):
            ao, bo = a.astype(object), b.astype(object)
            eq = pd.Series([x == y or (pd.isna(x) and pd.isna(y)) for x, y in zip(ao, bo)])
        bad = (~eq.astype(bool)).to_numpy().nonzero()[0]
        if len(bad):
            diff_cols[c] = int(len(bad))
            if first is None or bad[0] < first:
                first = int(bad[0])
    if first is None and len(da) == len(db):
        print("  all values equal (byte difference is metadata/encoding only)")
        return ok
    if first is None:
        first = n  # the common prefix is identical; divergence is the extra rows
        print(f"  first {n} rows identical; extra rows start at row {n}")
    else:
        ok = False
        print(f"  FIRST DIFFERING ROW: {first}")
        for c in common:
            va = da[c].iloc[first]
            vb = db[c].iloc[first]
            same = (va == vb) if not (pd.isna(va) or pd.isna(vb)) else (pd.isna(va) and pd.isna(vb))
            if not same:
                print(f"    column {c!r}: A={va}  B={vb}")
        print(f"  differing-cell counts over common prefix: {diff_cols}")
    lo, hi = max(0, first - ctx), first + ctx + 1
    with pd.option_context("display.width", 250, "display.max_columns", 50):
        print(f"  --- A rows {lo}..{min(hi, len(da)) - 1} ---")
        print(da.iloc[lo:hi].to_string())
        print(f"  --- B rows {lo}..{min(hi, len(db)) - 1} ---")
        print(db.iloc[lo:hi].to_string())
    return False


def compare_traces(da: str, db: str, ctx: int) -> int:
    A, B = pathlib.Path(da), pathlib.Path(db)
    ok = True
    for name in ("trace.parquet", "message_trace.parquet"):
        ok &= _compare_table(A / name, B / name, ctx)
        print()
    print("TRACES IDENTICAL" if ok else "TRACES DIFFER")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="first_divergence")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--traces", action="store_true", help="a and b are output directories")
    ap.add_argument("--types", default=None, help="comma list of record types to compare")
    ap.add_argument("--context", type=int, default=None, help="context records/rows (10 / 3)")
    ap.add_argument("--no-tail-count", action="store_true",
                    help="do not read the rest of the files after the divergence")
    args = ap.parse_args(argv)
    try:
        if args.traces:
            return compare_traces(args.a, args.b, 3 if args.context is None else args.context)
        types = set(args.types.split(",")) if args.types else None
        return compare_dumps(args.a, args.b, types, 10 if args.context is None else args.context,
                             not args.no_tail_count)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
