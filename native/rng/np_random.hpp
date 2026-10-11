// np_random.hpp -- bit-exact C++17 replica of numpy 1.26.4 legacy numpy.random.RandomState
// (MT19937 + the "legacy" distributions in numpy/random/src/legacy/legacy-distributions.c and
// the legacy bounded-integer path in numpy/random/_bounded_integers.pyx / distributions.c).
//
// Header-only. Verified bit-for-bit against numpy 1.26.4 by test_rng.cpp + gen_ref.py.
// Uses std::log / std::exp / std::sqrt, which must resolve to the SAME libm numpy links
// against (glibc libm in the t3-native-dev / runtime image) for log/exp-based methods.
//
// Scalar semantics mirror RandomState methods called WITHOUT size= (and also equal the
// element-wise sequence of the size= forms for these methods).
#pragma once

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>

namespace nprand {

class NpRandomState {
 public:
  static constexpr int kN = 624;
  static constexpr int kM = 397;

  // np.random.RandomState(seed=s) / np.random.seed(s) for a scalar integer 0 <= s <= 2**32-1
  // (numpy's _legacy_seeding -> mt19937_seed, i.e. Matsumoto-Nishimura init_genrand).
  explicit NpRandomState(uint64_t s = 0) { seed(s); }

  void seed(uint64_t s) {
    if (s > 0xFFFFFFFFull) throw std::invalid_argument("Seed must be between 0 and 2**32 - 1");
    uint32_t v = static_cast<uint32_t>(s);
    for (int pos = 0; pos < kN; ++pos) {
      key_[pos] = v;
      v = 1812433253u * (v ^ (v >> 30)) + static_cast<uint32_t>(pos + 1);
    }
    pos_ = kN;
    has_gauss_ = false;
    gauss_ = 0.0;
  }

  // ---- raw bit generator (mt19937.c / mt19937.h) --------------------------------------
  uint32_t next_uint32() {
    if (pos_ == kN) gen();
    uint32_t y = key_[pos_++];
    y ^= (y >> 11);
    y ^= (y << 7) & 0x9d2c5680u;
    y ^= (y << 15) & 0xefc60000u;
    y ^= (y >> 18);
    return y;
  }
  uint64_t next_uint64() {
    uint64_t hi = next_uint32();
    return (hi << 32) | next_uint32();
  }
  // mt19937_next_double: 53-bit resolution in [0, 1)
  double next_double() {
    int32_t a = static_cast<int32_t>(next_uint32() >> 5);
    int32_t b = static_cast<int32_t>(next_uint32() >> 6);
    return (a * 67108864.0 + b) / 9007199254740992.0;
  }

  // ---- RandomState methods ------------------------------------------------------------
  double random_sample() { return next_double(); }  // also rand(), random()
  double rand() { return next_double(); }

  // randint(low, high) with default dtype=int (int64 on Linux); high exclusive.
  // randint(0, 1) consumes NO draw (rng == 0), exactly like numpy.
  int64_t randint(int64_t low, int64_t high) {
    if (low >= high) throw std::invalid_argument("low >= high");
    uint64_t rng = static_cast<uint64_t>(high) - static_cast<uint64_t>(low) - 1u;
    return static_cast<int64_t>(bounded_uint64(static_cast<uint64_t>(low), rng));
  }
  int64_t randint(int64_t high) { return randint(0, high); }

  // randint(low, high, dtype="uint64"); high exclusive, high <= 2**64 not representable here,
  // so callers pass high as uint64 (2**32 -> 4294967296).
  uint64_t randint_u64(uint64_t low, uint64_t high) {
    if (low >= high) throw std::invalid_argument("low >= high");
    return bounded_uint64(low, high - low - 1u);
  }

  // Seeds a child exactly like RandomState(seed=np.random.randint(0, 2**32, dtype="uint64"))
  // (and generate_latency_model's RandomState(seed=np.random.randint(low=0, high=2**32))).
  NpRandomState spawn_child() { return NpRandomState(randint_u64(0, 4294967296ull)); }

  // legacy_gauss: polar Box-Muller with cached second value.
  double standard_normal() {
    if (has_gauss_) {
      const double tmp = gauss_;
      has_gauss_ = false;
      gauss_ = 0.0;
      return tmp;
    }
    double f, x1, x2, r2;
    do {
      x1 = 2.0 * next_double() - 1.0;
      x2 = 2.0 * next_double() - 1.0;
      r2 = x1 * x1 + x2 * x2;
    } while (r2 >= 1.0 || r2 == 0.0);
    f = std::sqrt(-2.0 * std::log(r2) / r2);
    gauss_ = f * x1;
    has_gauss_ = true;
    return f * x2;
  }

  // legacy_normal: loc + scale * gauss   (scale == 0 still consumes a gauss, as numpy does)
  double normal(double loc = 0.0, double scale = 1.0) {
    if (!(scale >= 0.0)) throw std::invalid_argument("scale < 0");
    return loc + scale * standard_normal();
  }

  // legacy_standard_exponential: -log(1 - U)
  double standard_exponential() { return -std::log(1.0 - next_double()); }

  // legacy_exponential: scale * standard_exponential
  double exponential(double scale = 1.0) {
    if (!(scale >= 0.0)) throw std::invalid_argument("scale < 0");
    return scale * standard_exponential();
  }

  // legacy_lognormal: exp(legacy_normal(mean, sigma))
  double lognormal(double mean = 0.0, double sigma = 1.0) {
    if (!(sigma >= 0.0)) throw std::invalid_argument("sigma < 0");
    return std::exp(mean + sigma * standard_normal());
  }

  // RandomState.uniform: range = high - low computed once, then random_uniform: low + range*U
  double uniform(double low = 0.0, double high = 1.0) {
    const double range = high - low;
    if (!std::isfinite(range)) throw std::overflow_error("Range exceeds valid bounds");
    return low + range * next_double();
  }

  // legacy_pareto: exp(standard_exponential / a) - 1
  double pareto(double a) {
    if (!(a > 0.0)) throw std::invalid_argument("a <= 0");
    return std::exp(standard_exponential() / a) - 1.0;
  }

  // RandomState.choice(n, p=p) for a single sample (replace=True): cdf = cumsum(p);
  // cdf /= cdf[-1]; idx = searchsorted(cdf, random_sample(), side='right').
  // numpy's p validation (sum ~ 1, non-negative) is NOT replicated.  `cdf_scratch` must hold n.
  int64_t choice_p(const double* p, std::size_t n, double* cdf_scratch) {
    double acc = 0.0;
    for (std::size_t i = 0; i < n; ++i) { acc += p[i]; cdf_scratch[i] = acc; }
    const double last = cdf_scratch[n - 1];
    for (std::size_t i = 0; i < n; ++i) cdf_scratch[i] /= last;
    const double u = next_double();
    std::size_t lo = 0, hi = n;  // first index with cdf[i] > u
    while (lo < hi) {
      std::size_t mid = lo + (hi - lo) / 2;
      if (cdf_scratch[mid] <= u) lo = mid + 1; else hi = mid;
    }
    return static_cast<int64_t>(lo);
  }

  // ---- state access (matches RandomState.get_state()) ---------------------------------
  const uint32_t* key() const { return key_; }
  int pos() const { return pos_; }
  bool has_gauss() const { return has_gauss_; }
  double cached_gauss() const { return gauss_; }

 private:
  static uint64_t gen_mask(uint64_t max) {
    uint64_t mask = max;
    mask |= mask >> 1;
    mask |= mask >> 2;
    mask |= mask >> 4;
    mask |= mask >> 8;
    mask |= mask >> 16;
    mask |= mask >> 32;
    return mask;
  }

  // random_bounded_uint64_fill(state, off, rng, 1, use_masked=true, ...) -- legacy path.
  uint64_t bounded_uint64(uint64_t off, uint64_t rng) {
    if (rng == 0) return off;
    if (rng <= 0xFFFFFFFFull) {
      if (rng == 0xFFFFFFFFull) return off + next_uint32();
      const uint32_t r32 = static_cast<uint32_t>(rng);
      const uint32_t mask = static_cast<uint32_t>(gen_mask(rng));
      uint32_t val;
      while ((val = (next_uint32() & mask)) > r32) {}
      return off + val;
    }
    if (rng == 0xFFFFFFFFFFFFFFFFull) return off + next_uint64();
    const uint64_t mask = gen_mask(rng);
    uint64_t val;
    while ((val = (next_uint64() & mask)) > rng) {}
    return off + val;
  }

  void gen() {
    constexpr uint32_t kMatrixA = 0x9908b0dfu, kUpper = 0x80000000u, kLower = 0x7fffffffu;
    uint32_t y;
    int i;
    for (i = 0; i < kN - kM; ++i) {
      y = (key_[i] & kUpper) | (key_[i + 1] & kLower);
      key_[i] = key_[i + kM] ^ (y >> 1) ^ (-(y & 1u) & kMatrixA);
    }
    for (; i < kN - 1; ++i) {
      y = (key_[i] & kUpper) | (key_[i + 1] & kLower);
      key_[i] = key_[i + (kM - kN)] ^ (y >> 1) ^ (-(y & 1u) & kMatrixA);
    }
    y = (key_[kN - 1] & kUpper) | (key_[0] & kLower);
    key_[kN - 1] = key_[kM - 1] ^ (y >> 1) ^ (-(y & 1u) & kMatrixA);
    pos_ = 0;
  }

  uint32_t key_[kN];
  int pos_ = kN;
  bool has_gauss_ = false;
  double gauss_ = 0.0;
};

}  // namespace nprand
