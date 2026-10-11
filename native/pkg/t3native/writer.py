"""pandas-free parquet writer producing byte-identical files to abides_fork's ``DataFrame.to_parquet``.

``DataFrame.to_parquet(path, compression="snappy", index=False)`` (pandas 1.5.3, pyarrow engine) is
``pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, compression="snappy")``. For the
two fixed schemas below, ``from_pandas`` yields one chunk per column and a constant ``b"pandas"``
schema-metadata blob (no row-dependent content: ``index_columns`` is empty), so building the same
Arrow table directly and calling the same writer reproduces the file byte for byte -- without paying
the ~0.6 s pandas import on every container start.
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa
from pyarrow import _parquet

_TRACE_PANDAS_MD = (
    '{"index_columns": [], "column_indexes": [], "columns": ['
    '{"name": "t_ns", "field_name": "t_ns", "pandas_type": "int64", "numpy_type": "int64", "metadata": null}, '
    '{"name": "agent_id", "field_name": "agent_id", "pandas_type": "int32", "numpy_type": "int32", "metadata": null}, '
    '{"name": "msg_type", "field_name": "msg_type", "pandas_type": "unicode", "numpy_type": "string", "metadata": null}, '
    '{"name": "side", "field_name": "side", "pandas_type": "unicode", "numpy_type": "string", "metadata": null}, '
    '{"name": "price", "field_name": "price", "pandas_type": "int64", "numpy_type": "int64", "metadata": null}, '
    '{"name": "size", "field_name": "size", "pandas_type": "int64", "numpy_type": "int64", "metadata": null}, '
    '{"name": "order_id", "field_name": "order_id", "pandas_type": "int64", "numpy_type": "int64", "metadata": null}], '
    '"creator": {"library": "pyarrow", "version": "15.0.2"}, "pandas_version": "1.5.3"}'
)
_MSG_PANDAS_MD = (
    '{"index_columns": [], "column_indexes": [], "columns": ['
    '{"name": "seq", "field_name": "seq", "pandas_type": "int64", "numpy_type": "int64", "metadata": null}, '
    '{"name": "t_recv_ns", "field_name": "t_recv_ns", "pandas_type": "int64", "numpy_type": "int64", "metadata": null}, '
    '{"name": "t_send_ns", "field_name": "t_send_ns", "pandas_type": "int64", "numpy_type": "Int64", "metadata": null}, '
    '{"name": "latency_ns", "field_name": "latency_ns", "pandas_type": "int64", "numpy_type": "int64", "metadata": null}, '
    '{"name": "src_id", "field_name": "src_id", "pandas_type": "int32", "numpy_type": "int32", "metadata": null}, '
    '{"name": "dst_id", "field_name": "dst_id", "pandas_type": "int32", "numpy_type": "int32", "metadata": null}, '
    '{"name": "message_id", "field_name": "message_id", "pandas_type": "int64", "numpy_type": "int64", "metadata": null}, '
    '{"name": "msg_type", "field_name": "msg_type", "pandas_type": "unicode", "numpy_type": "string", "metadata": null}, '
    '{"name": "order_id", "field_name": "order_id", "pandas_type": "int64", "numpy_type": "Int64", "metadata": null}, '
    '{"name": "causal_parent", "field_name": "causal_parent", "pandas_type": "int64", "numpy_type": "Int64", "metadata": null}], '
    '"creator": {"library": "pyarrow", "version": "15.0.2"}, "pandas_version": "1.5.3"}'
)

TRACE_SCHEMA = pa.schema(
    [("t_ns", pa.int64()), ("agent_id", pa.int32()), ("msg_type", pa.string()), ("side", pa.string()),
     ("price", pa.int64()), ("size", pa.int64()), ("order_id", pa.int64())],
    metadata={b"pandas": _TRACE_PANDAS_MD.encode()},
)
MSG_SCHEMA = pa.schema(
    [("seq", pa.int64()), ("t_recv_ns", pa.int64()), ("t_send_ns", pa.int64()), ("latency_ns", pa.int64()),
     ("src_id", pa.int32()), ("dst_id", pa.int32()), ("message_id", pa.int64()), ("msg_type", pa.string()),
     ("order_id", pa.int64()), ("causal_parent", pa.int64())],
    metadata={b"pandas": _MSG_PANDAS_MD.encode()},
)


def utf8_from_buffers(off_ptr: int, data_ptr: int, nbytes: int, count: int, owner) -> pa.Array:
    """Zero-copy utf8 array over engine-owned (offsets, data) buffers; `owner` keeps them alive."""
    offsets = pa.foreign_buffer(off_ptr, 4 * (count + 1), base=owner)
    data = pa.foreign_buffer(data_ptr, max(int(nbytes), 0), base=owner)
    return pa.Array.from_buffers(pa.string(), count, [None, offsets, data])


def ints(values: np.ndarray, typ: pa.DataType) -> pa.Array:
    """Zero-copy primitive array. (``pa.array(ndarray)`` would lazily import pandas to sniff for a
    Series -- ~0.6 s per container start.)"""
    return pa.Array.from_buffers(typ, len(values), [None, pa.py_buffer(np.ascontiguousarray(values))])


def nullable_int64(values: np.ndarray, present: np.ndarray) -> pa.Array:
    """int64 with an Arrow validity bitmap (LSB-first); values in null slots are never written."""
    bitmap = np.packbits(present.astype(bool, copy=False), bitorder="little")
    return pa.Array.from_buffers(
        pa.int64(), len(values), [pa.py_buffer(bitmap), pa.py_buffer(np.ascontiguousarray(values))]
    )


def _write_table(table: pa.Table, path) -> None:
    """``pq.write_table(table, path, compression="snappy")`` without its lazy pandas import.

    Calls the low-level writer with exactly the arguments ``pyarrow.parquet.ParquetWriter``
    (pyarrow 15.0.2) passes for those defaults, so the byte stream is identical; the sink type does
    not affect the bytes written.
    """
    sink = pa.OSFile(str(path), "wb")
    try:
        writer = _parquet.ParquetWriter(
            sink, table.schema,
            version="2.6", compression="snappy", use_dictionary=True, write_statistics=True,
            use_deprecated_int96_timestamps=False, compression_level=None, use_byte_stream_split=False,
            column_encoding=None, writer_engine_version="V2", data_page_version="1.0",
            use_compliant_nested_type=True, encryption_properties=None, write_batch_size=None,
            dictionary_pagesize_limit=None, store_schema=True, write_page_index=False,
            write_page_checksum=False, sorting_columns=None,
        )
        writer.write_table(table, row_group_size=None)
        writer.close()
    finally:
        sink.close()


def write_trace(path, cols: dict) -> None:
    _write_table(pa.Table.from_arrays([cols[n] for n in TRACE_SCHEMA.names], schema=TRACE_SCHEMA), path)


def write_message_trace(path, cols: dict) -> None:
    _write_table(pa.Table.from_arrays([cols[n] for n in MSG_SCHEMA.names], schema=MSG_SCHEMA), path)
