"""Native fast path for the ``simulate`` verb.

Runs the scenario through ``libt3engine.so`` (a bit-exact C++ reimplementation of the ABIDES paths
the abides_fork adapter exercises) and writes the same ``trace.parquet`` / ``message_trace.parquet``
/ ``events.json`` as ``abides_fork.simulate``. Every parameter is derived with the exact Python
expressions of ``abides_fork/config.py`` so float conversions and truncations match.

Anything the native engine is not certified for raises ``Unsupported`` and the caller falls back to
the reference ABIDES path, which is always exact.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import pathlib
import resource
import time
from typing import Any, Optional

import numpy as np

_LIB_PATH = pathlib.Path(os.environ.get("T3_ENGINE_LIB", pathlib.Path(__file__).with_name("libt3engine.so")))

_DATE_NS = 1612483200000000000  # pd.to_datetime("20210205")
_MKT_OPEN_OFFSET_NS = 34_200_000_000_000  # str_to_ns("09:30:00")
_ONE_SECOND_NS = 1_000_000_000
_ORACLE_CLOSE_OFFSET_NS = 57_600_000_000_000  # str_to_ns("16:00:00"): config.oracle_close
_DEFAULT_COMPUTATION_DELAY = 50

_KIND = {"NoiseTrader": 1, "MarketMaker": 2, "ValueTrader": 3, "MomentumTrader": 4}
_TRACE_NAMES = ["ORDER_SUBMITTED", "ORDER_ACCEPTED", "ORDER_CANCELLED", "PARTIAL_FILL", "ORDER_FILLED", "QUOTE_UPDATE"]
_SIDE_NAMES = ["BID", "ASK"]


class Unsupported(Exception):
    """The scenario uses a feature the native engine is not certified for."""


class _Result(ctypes.Structure):
    _fields_ = [
        ("n_trace", ctypes.c_int64),
        ("t_ns", ctypes.POINTER(ctypes.c_int64)),
        ("price", ctypes.POINTER(ctypes.c_int64)),
        ("size", ctypes.POINTER(ctypes.c_int64)),
        ("order_id", ctypes.POINTER(ctypes.c_int64)),
        ("agent_id", ctypes.POINTER(ctypes.c_int32)),
        ("msg_type", ctypes.POINTER(ctypes.c_int8)),
        ("side", ctypes.POINTER(ctypes.c_int8)),
        ("n_ledger", ctypes.c_int64),
        ("l_seq", ctypes.POINTER(ctypes.c_int64)),
        ("l_t_recv", ctypes.POINTER(ctypes.c_int64)),
        ("l_t_send", ctypes.POINTER(ctypes.c_int64)),
        ("l_latency", ctypes.POINTER(ctypes.c_int64)),
        ("l_message_id", ctypes.POINTER(ctypes.c_int64)),
        ("l_order_id", ctypes.POINTER(ctypes.c_int64)),
        ("l_causal", ctypes.POINTER(ctypes.c_int64)),
        ("l_src", ctypes.POINTER(ctypes.c_int32)),
        ("l_dst", ctypes.POINTER(ctypes.c_int32)),
        ("l_msg_type", ctypes.POINTER(ctypes.c_int8)),
        ("l_has_send", ctypes.POINTER(ctypes.c_int8)),
        ("l_has_order", ctypes.POINTER(ctypes.c_int8)),
        ("l_has_causal", ctypes.POINTER(ctypes.c_int8)),
        ("sim_seconds", ctypes.c_double),
        ("owner", ctypes.c_void_p),
        ("tr_msg_off", ctypes.c_void_p),
        ("tr_side_off", ctypes.c_void_p),
        ("l_msg_off", ctypes.c_void_p),
        ("tr_msg_data", ctypes.c_void_p),
        ("tr_side_data", ctypes.c_void_p),
        ("l_msg_data", ctypes.c_void_p),
        ("tr_msg_bytes", ctypes.c_int64),
        ("tr_side_bytes", ctypes.c_int64),
        ("l_msg_bytes", ctypes.c_int64),
    ]


_lib = None


def _load():
    global _lib
    if _lib is None:
        lib = ctypes.CDLL(str(_LIB_PATH))
        lib.t3_create.restype = ctypes.c_void_p
        lib.t3_create.argtypes = [
            ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(ctypes.c_double), ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(ctypes.c_double),
        ]
        lib.t3_simulate.restype = ctypes.c_int
        lib.t3_simulate.argtypes = [ctypes.c_void_p]
        lib.t3_finish.restype = ctypes.POINTER(_Result)
        lib.t3_finish.argtypes = [ctypes.c_void_p]
        lib.t3_destroy.argtypes = [ctypes.c_void_p]
        lib.t3_free.argtypes = [ctypes.POINTER(_Result)]
        lib.t3_msg_name.restype = ctypes.c_char_p
        lib.t3_msg_name.argtypes = [ctypes.c_int]
        _lib = lib
    return _lib


def _interval_ns(params: dict[str, Any]) -> int:  # config._interval_ns + ScheduledAgent clamp
    if "rebalance_interval_ns" in params:
        v = int(params["rebalance_interval_ns"])
    else:
        hz = float(params.get("arrival_rate_hz", 1.0))
        v = int(1e9 / hz) if hz > 0 else int(1e9)
    return int(max(1, v))


_BIG = 2**52  # keep every engine int64/double conversion exact and every time sum far from overflow


def _check_domain(ci, cf, ai, af, model) -> None:
    """Reject inputs outside the engine's certified numeric domain.

    Covers (a) configs on which the reference itself raises (numpy argument checks, kernel
    ValueError on a negative computation delay) -- falling back reproduces that behaviour exactly --
    and (b) magnitudes where Python's unbounded ints / float->int conversions could differ from the
    engine's int64 arithmetic.
    """
    (_seed, _d, stop, mkt_open, mkt_close, _cd, ack, comp, _stp, ref_price, _hj, sj_time, sj_mag, _lc, _oc) = (
        int(x) for x in ci)
    kappa, fund_vol, ms_lambda, ms_mean, _mv, mean_ns, lsig, lmin, lmax, alpha, _mu = (float(x) for x in cf)
    if comp < 0:
        raise Unsupported("negative exchange computation delay (reference kernel raises ValueError)")
    if abs(mkt_close - mkt_open) > 2**60 or abs(ack) > 2**60 or comp > 2**60 or abs(sj_time) > 2**61:
        raise Unsupported("time value outside int64-safe range")
    if abs(ref_price) > _BIG or abs(sj_mag) > _BIG:
        raise Unsupported("price outside exact range")
    for v in (kappa, fund_vol, ms_lambda, ms_mean, mean_ns, lsig, lmin, lmax, alpha):
        if not np.isfinite(v):
            raise Unsupported("non-finite float parameter")
    if model == "log_normal" and lsig < 0:
        raise Unsupported("negative log_normal sigma (numpy raises)")
    if model == "pareto" and not alpha > 0:
        raise Unsupported("non-positive pareto alpha (numpy raises)")
    if abs(lmin) > 2**60 or abs(lmax) > 2**60 or abs(mean_ns) > 2**60:
        raise Unsupported("latency bound outside int64-safe range")
    for row_i, row_f in zip(ai, af):
        kind, iv, off, _rp, spread, depth, spl, thr = (int(x) for x in row_i)
        osm, oss, _sn, lookback = (float(x) for x in row_f)
        if iv > 2**60:
            raise Unsupported("wake interval outside int64-safe range")
        if not (np.isfinite(osm) and np.isfinite(oss) and np.isfinite(lookback)):
            raise Unsupported("non-finite agent parameter")
        if abs(osm) > 1e12 or abs(oss) > 1e11 or abs(thr) > _BIG or lookback > 1e9:
            raise Unsupported("agent parameter outside exact range")
        if kind == 1:
            if oss < 0:
                raise Unsupported("negative order_size_std (numpy normal raises)")
            if off < 0:
                raise Unsupported("negative price_offset_ticks (numpy randint raises)")
            if off > 2**31 - 2:
                raise Unsupported("price_offset_ticks beyond the certified randint range")
        if kind == 2 and (spread > _BIG or depth > 10**6 or spl > _BIG):
            raise Unsupported("market-maker parameter outside exact range")


def build_native_config(scenario: dict[str, Any]):
    """Mirror abides_fork.config.build_config, producing the engine's flat arrays."""
    seed = int(scenario["seed"])
    if not (0 <= seed <= 2**32 - 1):
        raise Unsupported("seed outside numpy legacy range")
    exchange_cfg = scenario["exchange_config"]
    proto = bool(exchange_cfg.get("protocol_enforcement", False))
    stp = str(exchange_cfg["stp_policy"]) if proto and exchange_cfg.get("stp_policy") else None
    stp_code = 0 if stp is None else (2 if stp == "cancel_oldest" else 1)
    ack_delay = int(exchange_cfg.get("ack_delay_ns", 0)) if proto else 0
    compute_delay = int(exchange_cfg.get("compute_delay_ns", 0)) if proto else 0

    oracle_params = scenario["oracle_config"].get("params", {})
    reference_price = int(oracle_params.get("initial_price", 100_000))
    horizon_ns = int(scenario["horizon_ns"])
    mkt_open = _DATE_NS + _MKT_OPEN_OFFSET_NS
    mkt_close = mkt_open + horizon_ns
    kappa_per_s = float(oracle_params.get("kappa", 0.0))
    kappa = kappa_per_s / 1e9 if kappa_per_s > 0 else 1.67e-16
    rate_per_s = float(oracle_params.get("jump_intensity", 0.0))
    ms_lambda = rate_per_s / 1e9 if rate_per_s > 0 else 2.77778e-18
    fund_vol = float(oracle_params.get("sigma", 5e-5))
    ms_mean = float(oracle_params.get("jump_sigma", 0.0)) or 1000.0
    sj = oracle_params.get("scheduled_jump")
    sj_time = mkt_open + int(sj["time_ns"]) if sj else 0
    sj_mag = int(sj["magnitude"]) if sj else 0

    latency_cfg = scenario.get("latency_config")
    if not latency_cfg:
        raise Unsupported("no latency_config (ABIDES default latency model not ported)")
    lp = latency_cfg.get("params", {})
    model = str(latency_cfg.get("model", "deterministic"))
    lat_code = {"log_normal": 1, "uniform": 2, "pareto": 3}.get(model, 0)
    mean_ns = float(lp.get("mean_ns", 0.0))
    lat_mu = float(np.log(mean_ns)) if mean_ns > 0 else 0.0

    ai, af = [], []
    for agent_cfg in scenario["agent_configs"]:
        t = str(agent_cfg["agent_type"])
        if t not in _KIND:
            raise Unsupported(f"agent type {t}")
        p = agent_cfg.get("params", {})
        iv = _interval_ns(p)
        row_i = [_KIND[t], iv, 0, 0, 0, 0, 0, 0]
        row_f = [0.0, 0.0, 1000.0, 0.0]
        if t == "NoiseTrader":
            row_f[0] = float(p.get("order_size_mean", 10))
            row_f[1] = float(p.get("order_size_std", 2))
            row_i[2] = int(p.get("price_offset_ticks", 5))
            row_i[3] = int(reference_price)
        elif t == "MarketMaker":
            row_i[4] = int(max(2, p.get("spread_ticks", 2)))
            row_i[5] = int(max(1, p.get("depth_levels", 3)))
            row_i[6] = int(max(1, p.get("size_per_level", 10)))
            row_i[3] = int(reference_price)
        elif t == "ValueTrader":
            row_f[0] = float(p.get("order_size_mean", 25))
            row_i[7] = int(p.get("threshold_ticks", 2))
        else:  # MomentumTrader
            row_f[0] = float(p.get("order_size_mean", 15))
            row_i[7] = int(p.get("threshold_ticks", 2))
            row_f[3] = float(int(max(1, p.get("lookback", 5))))
        for _ in range(int(agent_cfg["count"])):
            ai.append(row_i)
            af.append(row_f)

    ci = np.array(
        [seed, _DATE_NS, mkt_close + _ONE_SECOND_NS, mkt_open, mkt_close, _DEFAULT_COMPUTATION_DELAY,
         ack_delay, compute_delay, stp_code, reference_price, 1 if sj else 0, sj_time, sj_mag, lat_code,
         _DATE_NS + _ORACLE_CLOSE_OFFSET_NS],
        dtype=np.int64,
    )
    cf = np.array(
        [kappa, fund_vol, ms_lambda, ms_mean, 50_000.0, mean_ns, float(lp.get("sigma", 0.0)),
         float(lp.get("min_ns", 0.0)), float(lp.get("max_ns", 1e12)), float(lp.get("alpha", 1.5)), lat_mu],
        dtype=np.float64,
    )
    _check_domain(ci, cf, ai, af, model)
    ai = np.ascontiguousarray(np.array(ai, dtype=np.int64).reshape(-1, 8))
    af = np.ascontiguousarray(np.array(af, dtype=np.float64).reshape(-1, 4))
    return ci, cf, ai, af


def _view(ptr, n, dtype):
    """Zero-copy numpy view of an engine buffer (valid until t3_free)."""
    if not n:
        return np.empty(0, dtype)
    return np.ctypeslib.as_array(ptr, shape=(n,))


def _write_and_hash(write, path, cols) -> str:
    write(path, cols)
    return _sha256(pathlib.Path(path))


class NativeRun:
    """One scenario through the engine, in the reference adapter's phases:

    ``NativeRun(scenario)``  == build_config  (config, RNG seeding chain)        -- untimed
    ``.simulate()``          == abides.run    (event loop)                       -- timed
    ``.finish(paths)``       == extract_trace + parquet writing                  -- untimed
    """

    def __init__(self, scenario: dict[str, Any]):
        ci, cf, ai, af = build_native_config(scenario)
        self.lib = _load()
        as_i = lambda a: a.ctypes.data_as(ctypes.POINTER(ctypes.c_int64))
        as_f = lambda a: a.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        self.handle = self.lib.t3_create(as_i(ci), as_f(cf), ctypes.c_int32(len(ai)), as_i(ai), as_f(af))
        if not self.handle:
            raise Unsupported("native engine rejected the scenario")
        self.t_start = self.t_end = None

    def simulate(self) -> float:
        """Run the event loop; returns its wall-clock seconds (perf_counter = CLOCK_MONOTONIC)."""
        self.t_start = time.perf_counter()
        status = self.lib.t3_simulate(self.handle)
        self.t_end = time.perf_counter()
        if status != 0:
            self.close()
            raise Unsupported("native engine failed during simulation")
        return self.t_end - self.t_start

    def close(self) -> None:
        if self.handle:
            self.lib.t3_destroy(self.handle)
            self.handle = None

    def finish(self, trace_path, msg_path):
        """Assemble and write both parquet files. Returns (n_events, n_messages, (trace_sha, msg_sha))."""
        from t3native import writer

        lib = self.lib
        rp = lib.t3_finish(self.handle)
        self.handle = None  # owned by the result from here on (freed by t3_free)
        if not rp:
            raise Unsupported("native engine failed during output assembly")
        r = rp.contents
        if r.n_trace == 0:
            # No order was ever submitted: the reference's trace.extract_trace raises KeyError('order_id')
            # on such a run, so hand it to the reference path to reproduce that outcome exactly.
            lib.t3_free(rp)
            raise Unsupported("empty trace (reference raises KeyError)")
        try:
            n, m = r.n_trace, r.n_ledger
            pa = writer.pa
            utf8 = lambda off, data, nbytes, count: writer.utf8_from_buffers(off, data, nbytes, count, owner=rp)
            trace_cols = {
                "t_ns": writer.ints(_view(r.t_ns, n, np.int64), pa.int64()),
                "agent_id": writer.ints(_view(r.agent_id, n, np.int32), pa.int32()),
                "msg_type": utf8(r.tr_msg_off, r.tr_msg_data, r.tr_msg_bytes, n),
                "side": utf8(r.tr_side_off, r.tr_side_data, r.tr_side_bytes, n),
                "price": writer.ints(_view(r.price, n, np.int64), pa.int64()),
                "size": writer.ints(_view(r.size, n, np.int64), pa.int64()),
                "order_id": writer.ints(_view(r.order_id, n, np.int64), pa.int64()),
            }
            msg_cols = {
                "seq": writer.ints(_view(r.l_seq, m, np.int64), pa.int64()),
                "t_recv_ns": writer.ints(_view(r.l_t_recv, m, np.int64), pa.int64()),
                "t_send_ns": writer.nullable_int64(_view(r.l_t_send, m, np.int64), _view(r.l_has_send, m, np.int8)),
                "latency_ns": writer.ints(_view(r.l_latency, m, np.int64), pa.int64()),
                "src_id": writer.ints(_view(r.l_src, m, np.int32), pa.int32()),
                "dst_id": writer.ints(_view(r.l_dst, m, np.int32), pa.int32()),
                "message_id": writer.ints(_view(r.l_message_id, m, np.int64), pa.int64()),
                "msg_type": utf8(r.l_msg_off, r.l_msg_data, r.l_msg_bytes, m),
                "order_id": writer.nullable_int64(_view(r.l_order_id, m, np.int64), _view(r.l_has_order, m, np.int8)),
                "causal_parent": writer.nullable_int64(_view(r.l_causal, m, np.int64), _view(r.l_has_causal, m, np.int8)),
            }
            # The two files are independent: write + hash them concurrently (pyarrow/hashlib release the GIL).
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=2) as ex:
                f1 = ex.submit(_write_and_hash, writer.write_trace, trace_path, trace_cols)
                f2 = ex.submit(_write_and_hash, writer.write_message_trace, msg_path, msg_cols)
                hashes = (f1.result(), f2.result())
        finally:
            lib.t3_free(rp)
        return int(n), int(m), hashes


def run_native(scenario: dict[str, Any], trace_path, msg_path):
    """Run the engine, write both parquet files. Returns (n_events, n_messages, wall_clock_sec, shas).

    ``wall_clock_sec`` covers the event loop only -- the same scope as the reference adapter's timing
    of ``abides.run`` -- and excludes config/seeding (build_config) and output assembly/writing.
    """
    run = NativeRun(scenario)
    wall = run.simulate()
    n, m, hashes = run.finish(trace_path, msg_path)
    return n, m, wall, hashes


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_scenario(config_path, seed: Optional[int] = None) -> dict[str, Any]:
    path = pathlib.Path(config_path)
    if not path.is_file():
        # Reuse the reference's diagnostics (names the batch-verb mix-up) -- error path only.
        from abides_fork.scenario_io import read_scenario

        read_scenario(config_path)
    scenario = json.loads(path.read_text())
    if seed is not None:
        scenario = {**scenario, "seed": int(seed)}
    if os.environ.get("T3_FORCE_REFERENCE") == "1":
        raise Unsupported("reference path forced")
    return scenario


def write_events(scenario, out_path, n_events, n_messages, wall_clock_sec, hashes) -> dict[str, Any]:
    """events.json with exactly the reference adapter's fields."""
    out_path = pathlib.Path(out_path)
    events = {
        "scenario_id": str(scenario["scenario_id"]),
        "seed": int(scenario["seed"]),
        "n_events": n_events,
        "wall_clock_sec": float(wall_clock_sec),
        "events_per_sec": float(n_events / wall_clock_sec) if wall_clock_sec > 0 else 0.0,
        "trace_sha256": hashes[0],
        "n_messages": n_messages,
        "message_trace_sha256": hashes[1],
        "peak_memory_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
        "gpu_seconds": 0.0,
    }
    (out_path.parent / "events.json").write_text(json.dumps(events, indent=2) + "\n")
    return events


def simulate(config_path, out_path, seed: Optional[int] = None) -> dict[str, Any]:
    scenario = load_scenario(config_path, seed)
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    msg_out = out_path.parent / "message_trace.parquet"
    n_events, n_messages, wall_clock_sec, hashes = run_native(scenario, out_path, msg_out)
    return write_events(scenario, out_path, n_events, n_messages, wall_clock_sec, hashes)
