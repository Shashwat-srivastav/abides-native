"""Generate numpy 1.26.4 legacy RandomState reference streams for test_rng.cpp.

File format (little endian), a sequence of blocks:
    int32 op, int32 target, 8B p1, 8B p2, uint64 count, then count x uint64 payload
p1/p2 are int64 for randint ops / choice, float64 otherwise. Doubles are compared by bit
pattern; ints by value. `target` indexes a table of RandomState objects; target 0 is the
*global* np.random state (np.random.seed / np.random.<method>).

Usage:
    python gen_ref.py bulk <seed> <n> <out>          # every method, n draws each, one seed
    python gen_ref.py mixed <seed> <steps> <out>     # random interleaving of scalar calls
    python gen_ref.py chain <seed> <steps> <out>     # build_config seeding chain + sim draws
"""

import math
import random
import struct
import sys

import numpy as np

assert np.__version__ == "1.26.4", np.__version__

OP_SEED, OP_SPAWN, OP_STATE = 0, 1, 2
OP_SAMPLE, OP_RANDINT, OP_RANDINT_U64 = 3, 4, 5
OP_NORMAL, OP_STD_NORMAL, OP_EXP, OP_STD_EXP = 6, 7, 8, 9
OP_LOGNORMAL, OP_UNIFORM, OP_PARETO, OP_CHOICE = 10, 11, 12, 13
INT_OPS = {OP_RANDINT, OP_RANDINT_U64, OP_CHOICE, OP_SPAWN}

CHOICE_P = [np.array([0.1, 0.2, 0.3, 0.4]), np.array([1 / 3, 1 / 3, 1 / 3]),
            np.array([0.5, 0.0, 0.25, 0.125, 0.125])]


def dbits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


class Writer:
    def __init__(self, path):
        self.f = open(path, "wb")
        self.buf = bytearray()
        self.n_values = 0

    def block(self, op, target, p1, p2, payload_u64):
        fmt = "<iiqqQ" if op in INT_OPS else "<iiddQ"
        self.buf += struct.pack(fmt, op, target, p1, p2, len(payload_u64))
        if isinstance(payload_u64, np.ndarray):
            self.buf += payload_u64.astype("<u8", copy=False).tobytes()
        else:
            self.buf += struct.pack("<%dQ" % len(payload_u64), *payload_u64)
        if op not in (OP_SEED, OP_STATE):
            self.n_values += len(payload_u64)
        if len(self.buf) > (1 << 24):
            self.flush()

    def flush(self):
        self.f.write(self.buf)
        self.buf = bytearray()

    def close(self):
        self.flush()
        self.f.close()


def state_payload(rs):
    _, key, pos, has_gauss, gauss = rs.get_state()
    return [int(k) for k in key] + [int(pos), int(has_gauss), dbits(gauss)]


def scalar_draw(rs, op, p1, p2):
    """One scalar call exactly as the reference code does; returns uint64 payload."""
    if op == OP_SAMPLE:
        return dbits(rs.random_sample())
    if op == OP_RANDINT:
        return int(rs.randint(p1, p2)) & 0xFFFFFFFFFFFFFFFF
    if op == OP_RANDINT_U64:
        return int(rs.randint(p1, p2, dtype="uint64"))
    if op == OP_NORMAL:
        return dbits(rs.normal(p1, p2))
    if op == OP_STD_NORMAL:
        return dbits(rs.standard_normal())
    if op == OP_EXP:
        return dbits(rs.exponential(scale=p1))
    if op == OP_STD_EXP:
        return dbits(rs.standard_exponential())
    if op == OP_LOGNORMAL:
        return dbits(rs.lognormal(mean=p1, sigma=p2))
    if op == OP_UNIFORM:
        return dbits(rs.uniform(p1, p2))
    if op == OP_PARETO:
        return dbits(rs.pareto(p1))
    if op == OP_CHOICE:
        return int(rs.choice(len(CHOICE_P[p1]), p=CHOICE_P[p1]))
    raise ValueError(op)


def vector_draw(rs, op, p1, p2, n):
    if op == OP_SAMPLE:
        a = rs.random_sample(n)
    elif op == OP_RANDINT:
        return rs.randint(p1, p2, size=n, dtype=np.int64).view(np.uint64)
    elif op == OP_RANDINT_U64:
        return rs.randint(p1, p2, size=n, dtype="uint64")
    elif op == OP_NORMAL:
        a = rs.normal(p1, p2, size=n)
    elif op == OP_STD_NORMAL:
        a = rs.standard_normal(n)
    elif op == OP_EXP:
        a = rs.exponential(scale=p1, size=n)
    elif op == OP_STD_EXP:
        a = rs.standard_exponential(n)
    elif op == OP_LOGNORMAL:
        a = rs.lognormal(mean=p1, sigma=p2, size=n)
    elif op == OP_UNIFORM:
        a = rs.uniform(p1, p2, size=n)
    elif op == OP_PARETO:
        a = rs.pareto(p1, size=n)
    elif op == OP_CHOICE:
        return rs.choice(len(CHOICE_P[p1]), size=n, p=CHOICE_P[p1]).astype(np.int64).view(np.uint64)
    else:
        raise ValueError(op)
    return np.ascontiguousarray(a, dtype=np.float64).view(np.uint64)


BULK_CASES = [
    (OP_SAMPLE, 0, 0),
    (OP_RANDINT, 0, 2), (OP_RANDINT, 0, 6), (OP_RANDINT, 0, 1), (OP_RANDINT, 0, 11),
    (OP_RANDINT, 0, 100), (OP_RANDINT, 20, 50), (OP_RANDINT, 0, 2**32),
    (OP_RANDINT, -5, 1000003), (OP_RANDINT, 0, 2**40), (OP_RANDINT, 0, 2**63 - 1),
    (OP_RANDINT, -(2**63), 2**63 - 1), (OP_RANDINT_U64, 0, 2**32),
    (OP_NORMAL, 10.0, 2.0), (OP_NORMAL, 25.0, 5.0), (OP_NORMAL, 1000.0, math.sqrt(50000)),
    (OP_NORMAL, 100000.0, 0.0), (OP_NORMAL, 99999.7, 12.3), (OP_NORMAL, 100000.0, math.sqrt(1000.0)),
    (OP_STD_NORMAL, 0, 0),
    (OP_EXP, 1.0 / 2.77778e-18, 0), (OP_EXP, 1.0 / (2.0 / 1e9), 0), (OP_EXP, 1.0, 0),
    (OP_STD_EXP, 0, 0),
    (OP_LOGNORMAL, math.log(50000.0), 0.5), (OP_LOGNORMAL, math.log(1e6), 1.0),
    (OP_LOGNORMAL, math.log(250.0), 0.0), (OP_LOGNORMAL, math.log(20000.0), 2.0),
    (OP_LOGNORMAL, float(np.log(1234567.0)), 0.25),
    (OP_UNIFORM, 1000.0, 50000.0), (OP_UNIFORM, 0.0, 3866660.0), (OP_UNIFORM, 5.0, 5.0),
    (OP_UNIFORM, -1.0, 1.0),
    (OP_PARETO, 1.5, 0), (OP_PARETO, 3.0, 0), (OP_PARETO, 0.5, 0),
    (OP_CHOICE, 0, 0), (OP_CHOICE, 1, 0), (OP_CHOICE, 2, 0),
]


def gen_bulk(seed, n, path):
    w = Writer(path)
    rs = np.random.RandomState(seed=seed)
    w.block(OP_SEED, 1, 0, 0, [seed])
    w.block(OP_STATE, 1, 0, 0, state_payload(rs))
    for op, p1, p2 in BULK_CASES:
        # sanity: vectorized == scalar sequence (reference code calls scalars)
        st = rs.get_state()
        k = 3000
        scal = np.array([scalar_draw(rs, op, p1, p2) for _ in range(k)], dtype=np.uint64)
        rs.set_state(st)
        vec = vector_draw(rs, op, p1, p2, n)
        assert np.array_equal(vec[:k], scal), ("vector!=scalar", op, p1, p2)
        w.block(op, 1, p1, p2, vec)
        w.block(OP_STATE, 1, 0, 0, state_payload(rs))
    w.close()
    return w.n_values


def random_call(r):
    """A random (op, p1, p2) with scenario-like and edge-case parameters."""
    op = r.choice([OP_SAMPLE, OP_RANDINT, OP_RANDINT, OP_RANDINT_U64, OP_NORMAL, OP_NORMAL,
                   OP_STD_NORMAL, OP_EXP, OP_STD_EXP, OP_LOGNORMAL, OP_LOGNORMAL, OP_UNIFORM,
                   OP_PARETO, OP_CHOICE])
    if op == OP_RANDINT:
        hi = r.choice([1, 2, 2, 3, 6, 11, 21, 100, 2**31 + 7, 2**32, 2**33 + 1, 2**62])
        lo = r.choice([0, 0, 0, -3, 20])
        return op, lo, lo + hi
    if op == OP_RANDINT_U64:
        return op, 0, r.choice([2**32, 2**32, 2, 1000])
    if op == OP_NORMAL:
        return op, r.choice([10.0, 25.0, 1000.0, 1e5 + r.random(), r.uniform(-1e6, 1e6)]), \
            r.choice([2.0, 0.0, math.sqrt(50000), math.sqrt(1000.0), r.uniform(0, 100)])
    if op == OP_EXP:
        return op, r.choice([1.0 / 2.77778e-18, 5e8, 1.0, r.uniform(0, 10)]), 0.0
    if op == OP_LOGNORMAL:
        return op, math.log(r.choice([100.0, 5e4, 1e6, r.uniform(1, 1e7)])), \
            r.choice([0.0, 0.5, 1.0, 2.0, r.uniform(0, 3)])
    if op == OP_UNIFORM:
        lo = r.choice([0.0, 1000.0, r.uniform(-1e3, 1e6)])
        return op, lo, lo + r.choice([0.0, 1.0, 49000.0, r.uniform(0, 1e9)])
    if op == OP_PARETO:
        return op, r.choice([1.5, 1.5, 3.0, 0.5, r.uniform(0.1, 5)]), 0.0
    if op == OP_CHOICE:
        return op, r.randrange(len(CHOICE_P)), 0
    return op, 0.0, 0.0


def gen_mixed(seed, steps, path):
    r = random.Random(seed * 7919 + 1)
    w = Writer(path)
    rs = np.random.RandomState(seed=seed)
    w.block(OP_SEED, 1, 0, 0, [seed])
    for i in range(steps):
        if r.random() < 1e-4:  # reseed mid-stream (resets gauss cache)
            s = r.randrange(2**32)
            rs.seed(s)
            w.block(OP_SEED, 1, 0, 0, [s])
        op, p1, p2 = random_call(r)
        w.block(op, 1, p1, p2, [scalar_draw(rs, op, p1, p2)])
        if i % 2000 == 0:
            w.block(OP_STATE, 1, 0, 0, state_payload(rs))
    w.block(OP_STATE, 1, 0, 0, state_payload(rs))
    w.close()
    return w.n_values


def gen_chain(seed, steps, path):
    """Mirror cand2 build_config: np.random.seed; oracle RS; global megashock exponential;
    oracle normal+randint(2); exchange; agents; latency; kernel; then simulation draws on
    random targets including global np.random.exponential (oracle megashock times)."""
    r = random.Random(seed * 104729 + 3)
    w = Writer(path)
    np.random.seed(seed)
    w.block(OP_SEED, 0, 0, 0, [seed])
    g = np.random  # module-level functions use the global RandomState
    rss = {}
    nxt = [1]

    def spawn(default_dtype=False):
        t = nxt[0]
        nxt[0] += 1
        if default_dtype:  # generate_latency_model: randint(low=0, high=2**32) (int64)
            cs = g.randint(low=0, high=2**32)
        else:
            cs = g.randint(low=0, high=2**32, dtype="uint64")
        rss[t] = np.random.RandomState(seed=cs)
        w.block(OP_SPAWN, t, 1 if default_dtype else 0, 0, [int(cs)])
        return t

    lam = 1.0 / r.choice([2.77778e-18, 2.0 / 1e9, 0.5 / 1e9])
    orc = spawn()
    w.block(OP_EXP, 0, lam, 0.0, [dbits(g.exponential(scale=lam))])
    msm = r.choice([1000.0, 250.0])
    for op, p1, p2 in [(OP_NORMAL, msm, math.sqrt(50000)), (OP_RANDINT, 0, 2)]:
        w.block(op, orc, p1, p2, [scalar_draw(rss[orc], op, p1, p2)])
    spawn()  # exchange
    for _ in range(r.randint(1, 120)):
        spawn()  # agents
    spawn(default_dtype=r.random() < 0.5)  # latency model (either branch)
    spawn()  # random_state_kernel
    w.block(OP_STATE, 0, 0, 0, state_payload(np.random.mtrand._rand))
    targets = list(rss)
    for i in range(steps):
        if r.random() < 0.02:
            w.block(OP_EXP, 0, lam, 0.0, [dbits(g.exponential(scale=lam))])
            continue
        t = r.choice(targets)
        op, p1, p2 = random_call(r)
        w.block(op, t, p1, p2, [scalar_draw(rss[t], op, p1, p2)])
    for t in targets:
        w.block(OP_STATE, t, 0, 0, state_payload(rss[t]))
    w.close()
    return w.n_values


if __name__ == "__main__":
    mode, seed, n, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    fn = {"bulk": gen_bulk, "mixed": gen_mixed, "chain": gen_chain}[mode]
    print(f"{mode} seed={seed} values={fn(seed, n, out)}")
