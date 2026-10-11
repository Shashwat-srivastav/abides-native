import time, hashlib, pyarrow.parquet as pq; T = time.perf_counter
for f in ("trace.parquet", "message_trace.parquet"):
    tb = pq.read_table("/tmp/o/" + f)
    t = T(); pq.write_table(tb, "/tmp/w.parquet", compression="snappy"); w = T() - t
    t = T(); pq.write_table(tb, "/tmp/w2.parquet", compression="snappy", use_dictionary=False); w2 = T() - t
    t = T(); pq.write_table(tb, "/tmp/w3.parquet", compression="snappy", write_statistics=False); w3 = T() - t
    t = T(); h = hashlib.sha256(open("/tmp/w.parquet", "rb").read()).hexdigest(); hs = T() - t
    import os
    print(f"{f:24s} rows={tb.num_rows} write={w:.3f}s  no-dict={w2:.3f}s  no-stats={w3:.3f}s  sha={hs:.3f}s  size={os.path.getsize('/tmp/w.parquet')/1e6:.1f}MB")
