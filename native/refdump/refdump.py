"""refdump.py -- canonical step-by-step dump of the Python ABIDES reference run.

Usage (inside the agenthon-track3:cand2 image, PYTHONPATH=/opt is preset there):

    python refdump.py <scenario.json> <outdir> [--events trace|all] [--no-dump]

Runs the scenario through the *unmodified* ``abides_fork.simulate.simulate`` entry point
(reset counters, build_config, abides.run, extract_trace, extract_message_trace, parquet
write, events.json), with read-only monkeypatched hooks that append one record per line to
``<outdir>/dump.tsv``.  See DUMP_FORMAT.md for the exact record grammar.

Non-invasiveness rules followed by every hook:
  * hooks only READ simulator state; they never create Message/Order objects (the class-level
    id counters are untouched), never deepcopy, never consume RNG draws;
  * RandomState streams are replaced by a Python subclass (TracedRS) whose methods call the
    base-class implementation and return its result unchanged; the state is copied bit-exact
    via get_state/set_state at the moment the stream is created (before any draw);
  * the kernel queue is replaced (while still empty) by a subclass of the kernel's own
    _HeapQueue whose get() is the same heappop;
  * the only observable difference is wall-clock time.
``--no-dump`` installs every hook but writes to /dev/null (to time the overhead).
"""

from __future__ import annotations

import argparse
import dataclasses
import heapq
import io
import json
import os
import pathlib
import sys
from collections import Counter
from enum import Enum

import numpy as np

import abides_core.abides as abides_mod
import abides_core.kernel as kmod
from abides_core.agent import Agent
from abides_core.kernel import Kernel
from abides_core.message import Message, MessageBatch, WakeupMsg
from abides_markets.oracles.sparse_mean_reverting_oracle import SparseMeanRevertingOracle

import abides_fork.config as cfgmod
import abides_fork.simulate as simmod

DUMP_VERSION = 1

# Agent event types that abides_fork/trace.py consumes (extract_trace).
TRACE_EVENT_TYPES = frozenset(
    {
        "ORDER_SUBMITTED",
        "ORDER_ACCEPTED",
        "ORDER_EXECUTED",
        "ORDER_CANCELLED",
        "ORDER_REPLACED",
        "BEST_BID",
        "BEST_ASK",
    }
)

# ----------------------------------------------------------------------------------------
# output
# ----------------------------------------------------------------------------------------
_OUT: io.TextIOBase | None = None
_COUNTS: Counter = Counter()
_KERNEL: list = [None]  # the live Kernel once constructed
_EVENTS_MODE = "trace"


def _emit(rtype: str, *fields: str) -> None:
    _COUNTS[rtype] += 1
    _OUT.write(rtype + "\t" + "\t".join(fields) + "\n")


def _esc(s: str) -> str:
    return (
        s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    )


def fv(x) -> str:
    """Canonical scalar/value formatting (see DUMP_FORMAT.md section 2)."""
    if x is None:
        return "-"
    if isinstance(x, (bool, np.bool_)):
        return "1" if x else "0"
    if isinstance(x, Enum):
        return _esc(str(x.value))
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)):
        return float(x).hex()
    if isinstance(x, str):
        return _esc(x) if x != "" else "''"
    if isinstance(x, np.ndarray):
        return "[" + ";".join(fv(e) for e in x.ravel().tolist()) + "]"
    if isinstance(x, tuple):
        return "x".join(fv(e) for e in x)
    if isinstance(x, list):
        return "[" + ";".join(fv(e) for e in x) + "]"
    if isinstance(x, dict):
        return "{" + ",".join(f"{fv(k)}:{fv(v)}" for k, v in x.items()) + "}"
    if isinstance(x, Message):
        return f"{type(x).__name__}#{x.message_id}"
    return "<" + type(x).__name__ + ">"


def _t() -> str:
    k = _KERNEL[0]
    return "-" if k is None else fv(k.current_time)


# ----------------------------------------------------------------------------------------
# message field extraction (read-only)
# ----------------------------------------------------------------------------------------
_ORDER_ATTRS = ("order", "old_order", "new_order")


def _order_cols(o) -> list[str]:
    if o is None:
        return ["-", "-", "-", "-", "-"]
    return [
        fv(getattr(o, "order_id", None)),
        fv(getattr(o, "side", None)),
        fv(getattr(o, "limit_price", None)),
        fv(getattr(o, "quantity", None)),
        fv(getattr(o, "fill_price", None)),
    ]


def _msg_order(msg):
    o = getattr(msg, "order", None)
    if o is None:
        o = getattr(msg, "new_order", None)
    return o


def _payload(msg) -> str:
    if not dataclasses.is_dataclass(msg):
        return "-"
    parts = []
    for f in dataclasses.fields(msg):
        name = f.name
        if name == "message_id" or name in ("order", "new_order"):
            continue
        val = getattr(msg, name, None)
        if name == "old_order":
            parts.append("old=" + fv(getattr(val, "order_id", None)))
            continue
        parts.append(name + "=" + fv(val))
    return ";".join(parts) if parts else "-"


# ----------------------------------------------------------------------------------------
# RNG tracing
# ----------------------------------------------------------------------------------------
_REQ = object()
# method -> [(param, kind, default)]; kind: f=float, i=int, z=size, d=dtype, b=bool, a=any
_SIG = {
    "normal": [("loc", "f", 0.0), ("scale", "f", 1.0), ("size", "z", None)],
    "uniform": [("low", "f", 0.0), ("high", "f", 1.0), ("size", "z", None)],
    "lognormal": [("mean", "f", 0.0), ("sigma", "f", 1.0), ("size", "z", None)],
    "pareto": [("a", "f", _REQ), ("size", "z", None)],
    "exponential": [("scale", "f", 1.0), ("size", "z", None)],
    "standard_normal": [("size", "z", None)],
    "standard_exponential": [("size", "z", None)],
    "random_sample": [("size", "z", None)],
    "random": [("size", "z", None)],
    "poisson": [("lam", "f", 1.0), ("size", "z", None)],
    "binomial": [("n", "i", _REQ), ("p", "f", _REQ), ("size", "z", None)],
    "geometric": [("p", "f", _REQ), ("size", "z", None)],
    "gamma": [("shape", "f", _REQ), ("scale", "f", 1.0), ("size", "z", None)],
    "beta": [("a", "f", _REQ), ("b", "f", _REQ), ("size", "z", None)],
    "randint": [("low", "i", _REQ), ("high", "i", None), ("size", "z", None), ("dtype", "d", int)],
    "random_integers": [("low", "i", _REQ), ("high", "i", None), ("size", "z", None)],
    "choice": [("a", "a", _REQ), ("size", "z", None), ("replace", "b", True), ("p", "a", None)],
    "shuffle": [("x", "a", _REQ)],
    "permutation": [("x", "a", _REQ)],
    "seed": [("seed", "a", None)],
    "bytes": [("length", "i", _REQ)],
}
_VARARGS = {"rand", "randn"}  # rand(d0, d1, ...)


def _fmt_arg(kind: str, v) -> str:
    if v is None:
        return "-"
    if kind == "f":
        if isinstance(v, (int, float, np.integer, np.floating)):
            return float(v).hex()
        return fv(np.asarray(v, dtype=float))
    if kind == "i":
        if isinstance(v, (int, np.integer)):
            return str(int(v))
        return fv(v)
    if kind == "z":
        if isinstance(v, (tuple, list)):
            return "x".join(str(int(e)) for e in v)
        return str(int(v))
    if kind == "d":
        try:
            return np.dtype(v).name
        except TypeError:
            return fv(v)
    if kind == "b":
        return "1" if v else "0"
    if kind == "a" and isinstance(v, (list, tuple)):
        return fv(list(v))
    return fv(v)


def _fmt_args(method: str, a: tuple, k: dict) -> str:
    if method in _VARARGS:
        return ",".join(str(int(e)) for e in a) if a else "-"
    sig = _SIG.get(method)
    if sig is None:
        parts = [fv(e) for e in a] + [f"{kk}={fv(vv)}" for kk, vv in sorted(k.items())]
        return ",".join(parts) if parts else "-"
    out = []
    for idx, (name, kind, default) in enumerate(sig):
        if idx < len(a):
            v = a[idx]
        elif name in k:
            v = k[name]
        else:
            v = default
        if v is _REQ:
            v = None
        out.append(_fmt_arg(kind, v))
    return ",".join(out)


_DEPTH = [0]


def _emit_R(owner: str, method: str, a, k, result) -> None:
    _emit("R", _t(), owner, method, _fmt_args(method, a, k), fv(result))


class TracedRS(np.random.RandomState):
    """RandomState subclass that logs outermost draws. Results are the base-class results."""

    _owner = "?"


_RS_METHODS = sorted(set(_SIG) | _VARARGS | {"tomaxint", "multinomial", "dirichlet"})


def _make_rs_method(name):
    base = getattr(np.random.RandomState, name)

    def m(self, *a, **k):
        if _DEPTH[0]:
            return base(self, *a, **k)
        _DEPTH[0] += 1
        try:
            r = base(self, *a, **k)
        finally:
            _DEPTH[0] -= 1
        _emit_R(self._owner, name, a, k, r)
        return r

    m.__name__ = name
    return m


for _name in _RS_METHODS:
    if hasattr(np.random.RandomState, _name):
        setattr(TracedRS, _name, _make_rs_method(_name))


def traced_copy(rs: np.random.RandomState, owner: str) -> TracedRS:
    """Bit-exact copy of ``rs`` (MT19937 key/pos + cached gaussian) as a TracedRS."""
    t = TracedRS(0)  # fixed seed: no entropy / global-stream use; overwritten next line
    t.set_state(rs.get_state())
    t._owner = owner
    return t


def _install_global_wrappers() -> None:
    for name in _RS_METHODS:
        orig = getattr(np.random, name, None)
        if orig is None or not callable(orig):
            continue

        def make(orig=orig, name=name):
            def g(*a, **k):
                if _DEPTH[0]:
                    return orig(*a, **k)
                _DEPTH[0] += 1
                try:
                    r = orig(*a, **k)
                finally:
                    _DEPTH[0] -= 1
                _emit_R("global", name, a, k, r)
                return r

            g.__name__ = name
            return g

        setattr(np.random, name, make())


# ----------------------------------------------------------------------------------------
# hooks
# ----------------------------------------------------------------------------------------
class TracedQueue(kmod._HeapQueue):
    """Same heap as the kernel's _HeapQueue; get() additionally emits the D record(s)."""

    __slots__ = ("_k",)

    def __init__(self, k):
        super().__init__()
        self._k = k

    def get(self):
        item = heapq.heappop(self.queue)
        _emit_D(self._k, item)
        return item


def _emit_D(k, item) -> None:
    t, (sender, recipient, msg) = item
    kind = "WAKEUP" if isinstance(msg, WakeupMsg) else "MSG"
    agent_t = k.agent_current_times[recipient]
    ts = fv(t)
    if agent_t > t:
        # the kernel will push the item back with priority agent_t
        o = _msg_order(msg)
        _emit(
            "D", ts, kind, "REQUEUE", fv(sender), fv(recipient), type(msg).__name__,
            fv(msg.message_id), fv(agent_t), "-", *_order_cols(o), _payload(msg),
        )
        return
    if isinstance(msg, MessageBatch):
        for sub in msg.messages:
            _emit(
                "D", ts, kind, "DELIVER", fv(sender), fv(recipient), type(sub).__name__,
                fv(sub.message_id), "-", fv(msg.message_id), *_order_cols(_msg_order(sub)),
                _payload(sub),
            )
        return
    _emit(
        "D", ts, kind, "DELIVER", fv(sender), fv(recipient), type(msg).__name__,
        fv(msg.message_id), "-", "-", *_order_cols(_msg_order(msg)), _payload(msg),
    )


_NOLAT = object()
_LAST_LAT = [_NOLAT]


def _wrap_latency_model(lm) -> None:
    orig = lm.get_latency  # bound method

    def get_latency(sender_id, recipient_id):
        v = orig(sender_id=sender_id, recipient_id=recipient_id)
        _LAST_LAT[0] = v
        return v

    lm.get_latency = get_latency  # instance attribute shadows the class method


_orig_kernel_init = Kernel.__init__


def _kernel_init(self, *a, **kw):
    rs = kw.get("random_state")
    if rs is not None:
        kw["random_state"] = traced_copy(rs, "kernel")
    _orig_kernel_init(self, *a, **kw)
    if rs is None:
        # kernel drew its own state from the global stream (logged); wrap a copy of it
        self.random_state = traced_copy(self.random_state, "kernel")
    assert self.messages.empty()
    self.messages = TracedQueue(self)
    if self.agent_latency_model is not None:
        _wrap_latency_model(self.agent_latency_model)
    _KERNEL[0] = self
    _emit(
        "K", fv(self.start_time), fv(self.stop_time), fv(len(self.agents)),
        fv(self.agent_computation_delays[0] if self.agents else None),
    )


_orig_send = Kernel.send_message


def _send_message(self, sender_id, recipient_id, message, delay=0):
    comp = self.agent_computation_delays[sender_id]
    add = self.current_agent_additional_delay
    n_ledger = len(self._msg_ledger)
    _LAST_LAT[0] = _NOLAT
    _orig_send(self, sender_id, recipient_id, message, delay)
    sent = self.current_time + comp + add + delay
    if len(self._msg_ledger) > n_ledger:
        deliver_at = self._msg_ledger[-1]["t_recv_ns"]
    else:  # empty MessageBatch
        deliver_at = None
    raw = _LAST_LAT[0]
    _emit(
        "S", fv(self.current_time), fv(sender_id), fv(recipient_id), type(message).__name__,
        fv(message.message_id), fv(comp), fv(add), fv(delay), fv(sent),
        "-" if raw is _NOLAT else fv(raw),
        "-" if deliver_at is None else fv(deliver_at - sent),
        fv(deliver_at), *_order_cols(_msg_order(message)), _payload(message),
    )


_orig_set_wakeup = Kernel.set_wakeup


def _set_wakeup(self, sender_id, requested_time=None):
    req = self.current_time + 1 if requested_time is None else requested_time
    _orig_set_wakeup(self, sender_id, requested_time)
    mid = getattr(Message, "_Message__message_id_counter") - 1
    _emit("W", fv(self.current_time), fv(sender_id), fv(req), fv(mid))


_orig_log_event = Agent.logEvent


def _log_event(self, event_type, event="", append_summary_log=False, deepcopy_event=True):
    if self.log_events and (_EVENTS_MODE == "all" or event_type in TRACE_EVENT_TYPES):
        if isinstance(event, dict) and "order_id" in event:
            cols = [
                fv(event.get("order_id")), fv(event.get("side")), fv(event.get("limit_price")),
                fv(event.get("quantity")), fv(event.get("fill_price")),
            ]
            payload = "-"
        else:
            cols = ["-"] * 5
            payload = fv(event)
        _emit("E", fv(self.current_time), fv(self.id), _esc(str(event_type)), *cols, payload)
    return _orig_log_event(self, event_type, event, append_summary_log, deepcopy_event)


_orig_cfat = SparseMeanRevertingOracle.compute_fundamental_at_timestamp


def _cfat(self, ts, v_adj, symbol, pt, pv):
    v = _orig_cfat(self, ts, v_adj, symbol, pt, pv)
    _emit("F", _t(), fv(ts), fv(v_adj), fv(pt), fv(pv), fv(v))
    return v


# --- stream-owner labelling for the RandomStates built by build_config ---------------------
_orig_draw_rs = cfgmod._draw_random_state
_RS_LABELS: list[str] = []
_RS_CREATED: list[TracedRS] = []


def _draw_random_state():
    rs = _orig_draw_rs()  # same global randint draw, same seed -> same state
    i = len(_RS_CREATED)
    label = _RS_LABELS[i] if i < len(_RS_LABELS) else f"rs{i}"
    t = traced_copy(rs, label)
    _RS_CREATED.append(t)
    return t


_orig_gen_latency = cfgmod.generate_latency_model


def _generate_latency_model(n_agents, *a, **k):
    # Only used when the scenario has no latency_config (none of the public scenarios).
    # Temporarily route the RandomState constructor to TracedRS so the pairwise-distance
    # draws made during construction are logged under owner 'latency'.
    saved = np.random.RandomState

    def ctor(*ca, **ck):
        t = TracedRS(*ca, **ck)
        t._owner = "latency"
        return t

    np.random.RandomState = ctor
    try:
        return _orig_gen_latency(n_agents, *a, **k)
    finally:
        np.random.RandomState = saved


_orig_run = abides_mod.run


def _run(config, *a, **k):
    # Verify the positional labels match object identity before the simulation starts.
    agents = config["agents"]
    for ag in agents:
        assert getattr(ag.random_state, "_owner", None) == str(ag.id), (
            "RNG label mismatch for agent", ag.id, getattr(ag.random_state, "_owner", None))
    orc = config["custom_properties"]["oracle"]
    for sym, s in orc.symbols.items():
        assert getattr(s["random_state"], "_owner", None) == "oracle"
    lm = config["agent_latency_model"]
    assert getattr(lm.random_state, "_owner", None) == "latency"
    return _orig_run(config, *a, **k)


def install(scenario: dict) -> None:
    n_agents = sum(int(a["count"]) for a in scenario["agent_configs"])
    labels = ["oracle"] + [str(i) for i in range(n_agents + 1)]
    if scenario.get("latency_config"):
        labels.append("latency")
    labels.append("cfgkernel")  # config['random_state_kernel']: drawn, never passed to Kernel
    _RS_LABELS[:] = labels

    _install_global_wrappers()
    cfgmod._draw_random_state = _draw_random_state
    cfgmod.generate_latency_model = _generate_latency_model
    abides_mod.run = _run
    Kernel.__init__ = _kernel_init
    Kernel.send_message = _send_message
    Kernel.set_wakeup = _set_wakeup
    Agent.logEvent = _log_event
    SparseMeanRevertingOracle.compute_fundamental_at_timestamp = _cfat


def main(argv=None) -> int:
    global _OUT, _EVENTS_MODE
    ap = argparse.ArgumentParser(prog="refdump")
    ap.add_argument("scenario")
    ap.add_argument("outdir")
    ap.add_argument("--events", choices=["trace", "all"], default="trace",
                    help="E records: only trace.py-consumed event types (default) or all")
    ap.add_argument("--no-dump", action="store_true", help="hooks on, output to devnull")
    args = ap.parse_args(argv)
    _EVENTS_MODE = args.events

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    scenario = json.loads(pathlib.Path(args.scenario).read_text())

    dump_path = os.devnull if args.no_dump else str(outdir / "dump.tsv")
    _OUT = open(dump_path, "w", encoding="utf-8", newline="\n", buffering=1 << 20)
    _OUT.write(f"#REFDUMP\tv{DUMP_VERSION}\tscenario_id={scenario.get('scenario_id')}"
               f"\tseed={scenario.get('seed')}\tevents={args.events}\n")
    install(scenario)
    events = simmod.simulate(args.scenario, outdir / "trace.parquet")
    for rt in sorted(_COUNTS):
        _OUT.write(f"#COUNT\t{rt}\t{_COUNTS[rt]}\n")
    _OUT.close()

    summary = {
        "trace_sha256": events["trace_sha256"],
        "message_trace_sha256": events["message_trace_sha256"],
        "n_events": events["n_events"],
        "n_messages": events["n_messages"],
        "wall_clock_sec": events["wall_clock_sec"],
        "record_counts": dict(sorted(_COUNTS.items())),
        "dump_bytes": 0 if args.no_dump else os.path.getsize(dump_path),
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
