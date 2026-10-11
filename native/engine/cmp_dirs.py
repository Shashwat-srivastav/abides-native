"""Compare two directories of per-case outputs: /a/<case>/{trace,message_trace}.parquet against /b/<case>/...

    python cmp_dirs.py <a> <b>
A case counts as equal when both files exist on both sides and read back as the same tables
(names, Arrow types, pandas metadata, Table.equals, DataFrame.equals).
"""
import os
import sys

import pandas as pd
import pyarrow.parquet as pq

a, b = sys.argv[1:3]


def same(x, y):
    tx, ty = pq.read_table(x), pq.read_table(y)
    return (tx.schema.names == ty.schema.names and [f.type for f in tx.schema] == [f.type for f in ty.schema]
            and tx.schema.metadata.get(b"pandas") == ty.schema.metadata.get(b"pandas") and tx.equals(ty)
            and pd.read_parquet(x).equals(pd.read_parquet(y)))


ok = bad = 0
for d in sorted(os.listdir(a)):
    if not os.path.isdir(os.path.join(a, d)):
        continue
    files = ("trace.parquet", "message_trace.parquet")
    good = all(os.path.exists(os.path.join(p, d, f)) for p in (a, b) for f in files) and \
        all(same(os.path.join(a, d, f), os.path.join(b, d, f)) for f in files)
    ok += good
    bad += not good
    if not good:
        print("DIFFERENT", d)
print("equal %d, different %d" % (ok, bad))
sys.exit(1 if bad else 0)
