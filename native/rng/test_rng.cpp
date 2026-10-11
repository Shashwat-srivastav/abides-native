// test_rng.cpp -- replay gen_ref.py reference files against nprand::NpRandomState and compare
// bit-for-bit.  Usage:  test_rng <ref.bin>...     |   test_rng bench
#include <chrono>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <vector>

#include "np_random.hpp"

using nprand::NpRandomState;

enum Op {
  OP_SEED, OP_SPAWN, OP_STATE, OP_SAMPLE, OP_RANDINT, OP_RANDINT_U64, OP_NORMAL, OP_STD_NORMAL,
  OP_EXP, OP_STD_EXP, OP_LOGNORMAL, OP_UNIFORM, OP_PARETO, OP_CHOICE
};

static const std::vector<std::vector<double>> kChoiceP = {
    {0.1, 0.2, 0.3, 0.4}, {1.0 / 3, 1.0 / 3, 1.0 / 3}, {0.5, 0.0, 0.25, 0.125, 0.125}};

static uint64_t bits(double d) { uint64_t u; std::memcpy(&u, &d, 8); return u; }

#pragma pack(push, 1)
struct Hdr { int32_t op, target; uint64_t p1, p2, count; };
#pragma pack(pop)

static uint64_t draw(NpRandomState& r, int op, uint64_t p1r, uint64_t p2r) {
  double d1, d2; std::memcpy(&d1, &p1r, 8); std::memcpy(&d2, &p2r, 8);
  int64_t i1 = (int64_t)p1r, i2 = (int64_t)p2r;
  switch (op) {
    case OP_SAMPLE: return bits(r.random_sample());
    case OP_RANDINT: return (uint64_t)r.randint(i1, i2);
    case OP_RANDINT_U64: return r.randint_u64((uint64_t)i1, (uint64_t)i2);
    case OP_NORMAL: return bits(r.normal(d1, d2));
    case OP_STD_NORMAL: return bits(r.standard_normal());
    case OP_EXP: return bits(r.exponential(d1));
    case OP_STD_EXP: return bits(r.standard_exponential());
    case OP_LOGNORMAL: return bits(r.lognormal(d1, d2));
    case OP_UNIFORM: return bits(r.uniform(d1, d2));
    case OP_PARETO: return bits(r.pareto(d1));
    case OP_CHOICE: {
      const auto& p = kChoiceP[i1];
      double scratch[16];
      return (uint64_t)r.choice_p(p.data(), p.size(), scratch);
    }
  }
  std::fprintf(stderr, "bad op %d\n", op);
  std::exit(2);
}

static const char* kOpName[] = {"seed", "spawn", "state", "random_sample", "randint", "randint_u64",
                                "normal", "standard_normal", "exponential", "standard_exponential",
                                "lognormal", "uniform", "pareto", "choice_p"};

static int run_file(const char* path, uint64_t& compared, uint64_t& state_checks) {
  FILE* f = std::fopen(path, "rb");
  if (!f) { std::perror(path); return 1; }
  std::map<int, NpRandomState> rs;
  std::vector<uint64_t> payload;
  uint64_t mism = 0, blocks = 0, per_op[14] = {0};
  Hdr h;
  while (std::fread(&h, sizeof h, 1, f) == 1) {
    ++blocks;
    payload.resize(h.count);
    if (std::fread(payload.data(), 8, h.count, f) != h.count) { std::fprintf(stderr, "short read\n"); return 1; }
    NpRandomState& r = rs[h.target];
    if (h.op == OP_SEED) { r.seed(payload[0]); continue; }
    if (h.op == OP_SPAWN) {
      NpRandomState& g = rs[0];
      uint64_t cs = h.p1 ? (uint64_t)g.randint(0, 4294967296LL) : g.randint_u64(0, 4294967296ull);
      ++compared; ++per_op[OP_SPAWN];
      if (cs != payload[0]) {
        if (mism++ < 10) std::printf("  MISMATCH spawn block %" PRIu64 ": %" PRIu64 " vs %" PRIu64 "\n", blocks, cs, payload[0]);
      }
      rs[h.target] = NpRandomState(payload[0]);
      continue;
    }
    if (h.op == OP_STATE) {
      ++state_checks;
      bool ok = true;
      for (int i = 0; i < 624; ++i) ok &= (r.key()[i] == (uint32_t)payload[i]);
      ok &= (uint64_t)r.pos() == payload[624];
      ok &= (uint64_t)r.has_gauss() == payload[625];
      ok &= bits(r.cached_gauss()) == payload[626];
      if (!ok && mism++ < 10) std::printf("  STATE MISMATCH block %" PRIu64 " target %d\n", blocks, h.target);
      continue;
    }
    for (uint64_t i = 0; i < h.count; ++i) {
      uint64_t v = draw(r, h.op, h.p1, h.p2);
      if (v != payload[i] && mism++ < 10) {
        double a, b; std::memcpy(&a, &v, 8); std::memcpy(&b, &payload[i], 8);
        std::printf("  MISMATCH %s block %" PRIu64 " idx %" PRIu64 ": got %016" PRIx64 " (%.17g) want %016" PRIx64 " (%.17g)\n",
                    kOpName[h.op], blocks, i, v, a, payload[i], b);
      }
    }
    compared += h.count;
    per_op[h.op] += h.count;
  }
  std::fclose(f);
  std::printf("%s: blocks=%" PRIu64 " mismatches=%" PRIu64 " |", path, blocks, mism);
  for (int o = 1; o < 14; ++o) if (per_op[o]) std::printf(" %s=%" PRIu64, kOpName[o], per_op[o]);
  std::printf("\n");
  return mism ? 1 : 0;
}

template <class F>
static void bench(const char* name, F f) {
  const int n = 20000000;
  volatile double sink = 0;
  double acc = 0;
  auto t0 = std::chrono::steady_clock::now();
  for (int i = 0; i < n; ++i) acc += (double)f();
  auto t1 = std::chrono::steady_clock::now();
  sink = acc; (void)sink;
  double s = std::chrono::duration<double>(t1 - t0).count();
  std::printf("  %-34s %8.1f M draws/s  (%.2f ns/draw)\n", name, n / s / 1e6, s / n * 1e9);
}

int main(int argc, char** argv) {
  if (argc >= 2 && std::strcmp(argv[1], "bench") == 0) {
    NpRandomState r(12345);
    std::printf("benchmark (20M scalar draws each):\n");
    bench("next_uint32", [&] { return r.next_uint32(); });
    bench("random_sample", [&] { return r.random_sample(); });
    bench("randint(0,2)", [&] { return r.randint(0, 2); });
    bench("randint(0,6)", [&] { return r.randint(0, 6); });
    bench("randint_u64(0,2**32)", [&] { return r.randint_u64(0, 4294967296ull); });
    bench("normal(10,2)", [&] { return r.normal(10.0, 2.0); });
    bench("exponential(3.6e17)", [&] { return r.exponential(3.6e17); });
    bench("lognormal(ln 5e4, 0.5)", [&] { return r.lognormal(10.819778284410283, 0.5); });
    bench("uniform(1000,50000)", [&] { return r.uniform(1000.0, 50000.0); });
    bench("pareto(1.5)", [&] { return r.pareto(1.5); });
    bench("spawn_child (seed 624 words)", [&] { return r.spawn_child().pos(); });
    return 0;
  }
  uint64_t compared = 0, states = 0;
  int bad = 0;
  for (int i = 1; i < argc; ++i) bad |= run_file(argv[i], compared, states);
  std::printf("TOTAL values compared=%" PRIu64 " state checks=%" PRIu64 " -> %s\n", compared, states,
              bad ? "FAIL" : "ALL BIT-IDENTICAL");
  return bad;
}
