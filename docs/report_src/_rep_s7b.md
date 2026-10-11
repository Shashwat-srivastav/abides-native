
### 7.9 Output pipeline rewrite: built-in Parquet writer (sub5) and delta encoding (sub6)

**Why.** The team asked for a score of 300,000. Before changing anything we re-read how the score is formed and measured where a unit's time goes.

*The formula.* The upstream README ("How throughput is measured") states that ranking is by the **arithmetic mean of the per-unit rates** over the roster, each rate being verified events ÷ container time. A mean of rates is dominated by the units with the most events, and for every unit the denominator contains a fixed container cost that we do not control. For the 65 public single scenarios: 7,465,846 events in total, 114,859 per unit on average, and the 8 largest units hold 4,135,440 of them (55%).

*Where the time went in sub4.* Phase timing (`T3_PHASES=1`) inside the sub4 image, best of 5 runs per unit, 4 CPUs, outputs on `/dev/shm`:

| Unit | Events | Process total | parse | create | simulate | finish | Parquet write |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gb_mega_throughput` | 1,168,360 | 1,230 ms | 5.2 | 60.2 | 173.7 | 234.9 | 677.4 |
| `gb_pop_horizon_scale` | 725,591 | 746 ms | 3.2 | 20.8 | 101.2 | 133.4 | 416.3 |
| `gb_horizon_240s` | 555,032 | 588 ms | 4.3 | 16.4 | 83.3 | 104.4 | 329.5 |
| `gb_highfreq_40hz_60s` | 500,530 | 526 ms | 3.8 | 14.1 | 70.8 | 99.6 | 292.6 |
| `mr_cancel_replace_churn` | 322,007 | 336 ms | 4.4 | 7.8 | 29.3 | 50.4 | 206.4 |
| `mr_deep_book_state_size` | 319,488 | 362 ms | 3.6 | 9.0 | 39.2 | 52.3 | 219.1 |
| `gb_pop_128_agents` | 303,603 | 391 ms | 4.4 | 11.3 | 56.7 | 58.4 | 219.8 |
| `mp05_cancel_churn_newest` | 240,829 | 287 ms | 4.2 | 5.9 | 25.0 | 37.7 | 180.1 |
| `mr_checkpoint_cadence_fine` | 161,055 | 211 ms | 3.5 | 4.1 | 14.8 | 24.9 | 133.2 |
| `st01_liquidity_churn_baseline` | 72,034 | 98 ms | 3.8 | 3.8 | 7.4 | 11.5 | 49.0 |

The Parquet write was 50–63% of the process on every one of these units; the event loop was 7–15%. The remainder of each total (process start, loading libarrow/libparquet, exit) was 20–80 ms.

A first, cruder look gave the same picture: two single runs of `st01` in sub4 took 1,581 ms (cold) and 154 ms (warm), the warm one with write 95.7 ms, finish 12.0 ms, simulate 10.4 ms.

**What the verifier requires of the files.** Read from the upstream scorer (`qfbench2_track_simulation/scoring.py`, `batch.py`):

- the trace and the ledger are loaded with `pd.read_parquet` and compared as tables;
- the event count is the Parquet footer's row count;
- `trace_sha256` in `events.json` is compared with the SHA-256 of *the file we wrote* (`_sha256_file(trace_path)`), not with the reference file's hash;
- outputs are capped at 256 MiB per file and in total (`limits.py`, `MAX_OUTPUT_BYTES`).

Nothing compares our file bytes with the reference's. sub1–sub4 produced pyarrow's exact bytes because that was the simplest way to be certain of equality, not because the rules ask for it. The Final's "stable outputs" rule (same bytes across repeats of our own image) is met by any deterministic writer.

**sub5: design.**

| Part | What it is |
|---|---|
| `native/engine/pq_fast.hpp` (292 lines in sub5) | Parquet writer for exactly our two tables. Thrift compact protocol written by hand for `FileMetaData`, `SchemaElement`, `RowGroup`, `ColumnChunk`, `ColumnMetaData`, `PageHeader`, `DataPageHeader`, `DictionaryPageHeader`, `KeyValue`. Row groups of at most 2²⁰ rows (the same split as before), one V1 data page per column chunk, every column OPTIONAL (as pyarrow writes them), format version 2, `created_by` "t3native version 1.0.0", codec UNCOMPRESSED, no statistics, no page index |
| Integer columns | PLAIN. The page is written straight from the engine's column buffer with `writev`; no copy into an intermediate buffer |
| String columns (`msg_type`, `side`, ledger `msg_type`) | One dictionary page holding all names (6, 2 and 13 entries), then RLE_DICTIONARY indices as a single bit-packed run, 4 bits per value (8 bits if a dictionary had more than 16 entries). Written from the engine's integer codes; the engine no longer expands them into strings for the launcher (`g_want_utf8 = false`) |
| Nullable columns (ledger `t_send_ns`, `order_id`, `causal_parent`) | Definition levels as one bit-packed run of width 1, which is the same LSB-first bitmap Arrow uses; only the present values are stored |
| Columns without nulls | Definition levels as one RLE run of ones (3–5 bytes) |
| Key-value metadata | The same `pandas` JSON string as before (this is what makes pandas restore the nullable `Int64` dtypes). The `ARROW:schema` entry is not written; pyarrow derives the same Arrow types from the Parquet schema |
| `native/engine/sha256.hpp` (121 lines) | SHA-256 with the CPU's SHA instructions when present, portable code otherwise (`T3_SHA_PORTABLE=1` forces the portable one). Hash and file write of each file run on two threads in a single run |
| Launcher binary | Linked `-static`, no libarrow/libparquet/libcrypto. 1,403,784 bytes (sub4's was 228,520 bytes plus 61 MB of shared libraries to map) |
| Output stage | `t3_finish` split into `finish_trace` and `finish_ledger`; in a single run each file's assemble → encode → hash + write chain runs on its own thread. In a batch, each market does the two chains one after the other on its worker thread |
| Exit | A single run no longer destroys the engine before `_exit` (freeing several hundred MB only to exit) |
| Size guard | If the two files together exceed 240 MiB the launcher hands the unit to the Python path, which writes snappy-compressed files |

The Python paths are unchanged: `t3native.cli` / `t3native.batch` and the ABIDES reference still write through pyarrow.

**What went wrong on the way (sub5).**

| Problem | Cause | Resolution |
|---|---|---|
| First phase-timing container ran for more than 5 minutes at about 113% CPU and 2.0 of 2.76 GiB before it was killed | The command passed `--out /output` (a directory). The launcher treats `--out` as the trace file path, could not open it, and handed over to the Python path, which was then running `gb_mega_throughput` through Python on a host that was swapping | Passed a file path. Re-tested afterwards with a small scenario: the Python path ends with `IsADirectoryError`, exit code 1, after having written `message_trace.parquet` next to the directory. The harness always passes a file path (the official regression passes), so this is a property of misuse, recorded here because it cost time |
| Static link against OpenSSL failed (`undefined reference to ZSTD_decompress`, …) | Debian's `libcrypto.a` depends on zstd and zlib | Dropped OpenSSL; wrote `sha256.hpp`. Its output is checked on every validated unit, because the checker recomputes each file's hash with Python's `hashlib` and compares it with the declared one |
| Two compile failures, "missing terminating \" character" | Patch scripts sent through a shell here-document turned `\n` inside a string literal into a real line break (the same tool behaviour as in §16.6) | Fixed with the file editor; later patches were written to files first |
| One `bash` command with two here-documents failed to parse | Tool quoting | Wrote the patch script and its payload to files |

**sub5: measured effect.** Best of 5, same conditions as the table above (ms):

| Unit | sub4 total | sub5 total | parse | create | simulate | output stage (wall) | trace: finish / build / emit | ledger: finish / build / emit |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `gb_mega_throughput` | 1,230 | 530 | 3.6 | 41.7 | 197.9 | 252.0 | 105.6 / 3.0 / 55.6 | 112.3 / 46.0 / 92.3 |
| `gb_pop_horizon_scale` | 746 | 318 | 3.8 | 21.5 | 111.1 | 153.2 | 55.2 / 1.6 / 31.6 | 70.1 / 24.4 / 57.0 |
| `gb_horizon_240s` | 588 | 232 | 3.4 | 18.3 | 79.3 | 109.9 | 45.5 / 1.3 / 21.1 | 51.3 / 16.8 / 41.1 |
| `gb_highfreq_40hz_60s` | 526 | 217 | 4.4 | 16.1 | 79.1 | 98.5 | 43.4 / 1.2 / 18.7 | 46.0 / 15.6 / 36.2 |
| `mr_cancel_replace_churn` | 336 | 117 | 3.4 | 8.6 | 37.4 | 54.7 | 29.5 / 0.9 / 14.0 | 23.5 / 9.7 / 20.6 |
| `mr_deep_book_state_size` | 362 | 102 | 3.8 | 7.5 | 36.0 | 45.0 | 23.7 / 0.6 / 11.9 | 18.0 / 8.1 / 17.6 |
| `gb_pop_128_agents` | 391 | 130 | 5.0 | 10.6 | 43.6 | 57.7 | 24.1 / 0.7 / 11.2 | 26.0 / 8.5 / 22.2 |
| `mp05_cancel_churn_newest` | 287 | 77 | 3.4 | 5.8 | 25.3 | 34.1 | 19.7 / 0.5 / 9.5 | 14.6 / 5.4 / 13.3 |
| `mr_checkpoint_cadence_fine` | 211 | 57 | 3.8 | 4.8 | 17.1 | 24.2 | 12.2 / 0.3 / 5.6 | 10.2 / 4.3 / 9.0 |
| `st01_liquidity_churn_baseline` | 98 | 30 | 3.3 | 2.9 | 6.7 | 12.8 | 5.7 / 0.2 / 2.9 | 5.5 / 1.8 / 4.7 |

The step from the first sub5 build (writer replaced, output still sequential) to the final one (parallel output chains) was measured separately on `gb_mega_throughput`: 563 ms → 530 ms; sequentially the phases were finish 171.0, build 30.2, write 100.2 ms.

After sub5 the largest remaining items on a big unit are the event loop (about 37% on `gb_mega`), the ledger chain (the longer of the two output chains) and engine creation including buffer pre-faulting.

**sub6: design.** Three changes on top of sub5 (`pq_fast.hpp` 369 lines, `engine.cpp` 1,549 lines):

1. **Integer columns DELTA_BINARY_PACKED** (blocks of 128 deltas in 4 miniblocks of 32, the layout parquet-cpp itself writes; deltas wrap in the column's own width). Nullable columns encode their present values after the bitmap.
2. **Column chunks encoded on two threads per file** (a shared counter over the row-group × column tasks), then laid out sequentially.
3. **Output columns left uninitialised** (`Raw<T>` instead of `std::vector`, which zero-filled every page before the values were written), and the ledger columns filled on two threads when there are at least 65,536 rows.

Reason for the encoding change: sub5's uncompressed files are large, and every byte is hashed and written inside the timed window. Output size, both files, summed over the 65 scenarios: sub4 289.2 MB (largest unit 45.2 MB), sub5 758.7 MB (largest 126.6 MB), sub6 135.8 MB (largest 22.2 MB).

**sub6: measured effect.** Best of 5 on the ten units (ms): `gb_mega` 485, `gb_pop_horizon_scale` 290, `gb_horizon_240s` 209, `gb_highfreq_40hz_60s` 194, `mr_cancel_replace_churn` 97, `mr_deep_book_state_size` 100, `gb_pop_128_agents` 124, `mp05` 77, `mr_checkpoint_cadence_fine` 51, `st01` 30. For `gb_mega`: output stage 167.4 ms (sub5 252.0); trace chain 104.9 / 40.0 / 21.8, ledger chain 51.1 / 86.0 / 25.8. The ledger's fill halved and both emits fell to about a quarter; encoding costs more than before (build 86 ms against 46 ms on the ledger).

All 65 units, three benchmark runs per image (3, 4 and 4 repeats per unit inside each run), sum of the best time per unit:

| | sub4 (one run, 3 repeats) | sub5 | sub6 |
|---|---:|---:|---:|
| Sum of best process times over 65 units | 10.20 s | 3.41 s | 3.28 s |
| Per-run sums | 10.20 | 3.87, 3.64, 4.13 | 5.65, 3.57, 3.58 |
| Median over units of sub6 ÷ sub5 | | | 1.007 |

The first sub6 run (5.65 s) was 60% slower than the other two and, on its own, suggested sub6 was slower than sub5 (for example `gb_horizon_240s` 485 ms against 247 ms). The same unit had measured 209 ms in the 5-repeat run an hour earlier, so both images were re-run back to back twice more; those runs agree with each other and with the earlier one. The 5.65 s run is kept in the table as an example of what this laptop does under memory pressure (§16.4). Conclusion: sub6 is about 4% faster than sub5 in total and indistinguishable on the median unit; its main benefit is the 5.6-fold smaller output.

**Validation of both images** is in §9.5.
