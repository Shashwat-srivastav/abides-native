// SHA-256 (FIPS 180-4): portable compression function plus an SHA-NI one picked at run time.
// Self-contained so the launcher can be a static binary with no libcrypto to load.
#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <immintrin.h>

namespace sha256 {

static const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

static inline uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

static void blocks_portable(uint32_t* st, const uint8_t* p, size_t nblocks) {
    while (nblocks--) {
        uint32_t w[64];
        for (int i = 0; i < 16; i++)
            w[i] = ((uint32_t)p[4 * i] << 24) | ((uint32_t)p[4 * i + 1] << 16) | ((uint32_t)p[4 * i + 2] << 8) | p[4 * i + 3];
        for (int i = 16; i < 64; i++) {
            uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
            uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        uint32_t a = st[0], b = st[1], c = st[2], d = st[3], e = st[4], f = st[5], g = st[6], h = st[7];
        for (int i = 0; i < 64; i++) {
            uint32_t t1 = h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
            uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
            h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
        }
        st[0] += a; st[1] += b; st[2] += c; st[3] += d; st[4] += e; st[5] += f; st[6] += g; st[7] += h;
        p += 64;
    }
}

__attribute__((target("sha,sse4.1,ssse3")))
static void blocks_shani(uint32_t* st, const uint8_t* p, size_t nblocks) {
    const __m128i MASK = _mm_set_epi64x(0x0c0d0e0f08090a0bULL, 0x0405060700010203ULL);
    __m128i TMP = _mm_loadu_si128((const __m128i*)&st[0]);
    __m128i S1 = _mm_loadu_si128((const __m128i*)&st[4]);
    TMP = _mm_shuffle_epi32(TMP, 0xB1);         // CDAB
    S1 = _mm_shuffle_epi32(S1, 0x1B);           // EFGH
    __m128i S0 = _mm_alignr_epi8(TMP, S1, 8);   // ABEF
    S1 = _mm_blend_epi16(S1, TMP, 0xF0);        // CDGH
    while (nblocks--) {
        const __m128i save0 = S0, save1 = S1;
        __m128i M[4];
        for (int g = 0; g < 16; g++) {
            const int cur = g & 3, nxt = (g + 1) & 3, prv = (g + 3) & 3;
            if (g < 4) M[g] = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i*)(p + 16 * g)), MASK);
            __m128i MSG = _mm_add_epi32(M[cur], _mm_loadu_si128((const __m128i*)&K[4 * g]));
            S1 = _mm_sha256rnds2_epu32(S1, S0, MSG);
            if (g >= 3 && g <= 14) {
                TMP = _mm_alignr_epi8(M[cur], M[prv], 4);
                M[nxt] = _mm_add_epi32(M[nxt], TMP);
                M[nxt] = _mm_sha256msg2_epu32(M[nxt], M[cur]);
            }
            MSG = _mm_shuffle_epi32(MSG, 0x0E);
            S0 = _mm_sha256rnds2_epu32(S0, S1, MSG);
            if (g >= 1 && g <= 12) M[prv] = _mm_sha256msg1_epu32(M[prv], M[cur]);
        }
        S0 = _mm_add_epi32(S0, save0);
        S1 = _mm_add_epi32(S1, save1);
        p += 64;
    }
    TMP = _mm_shuffle_epi32(S0, 0x1B);          // FEBA
    S1 = _mm_shuffle_epi32(S1, 0xB1);           // DCHG
    S0 = _mm_blend_epi16(TMP, S1, 0xF0);        // DCBA
    S1 = _mm_alignr_epi8(S1, TMP, 8);           // HGFE
    _mm_storeu_si128((__m128i*)&st[0], S0);
    _mm_storeu_si128((__m128i*)&st[4], S1);
}

struct Ctx {
    uint32_t st[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    uint8_t buf[64];
    size_t fill = 0;
    uint64_t total = 0;
    void (*fn)(uint32_t*, const uint8_t*, size_t);
    Ctx() {
        __builtin_cpu_init();
        const bool ni = __builtin_cpu_supports("sha") && __builtin_cpu_supports("sse4.1") && !getenv("T3_SHA_PORTABLE");
        fn = ni ? blocks_shani : blocks_portable;
    }
    void update(const uint8_t* p, size_t n) {
        total += n;
        if (fill) {
            size_t take = 64 - fill < n ? 64 - fill : n;
            memcpy(buf + fill, p, take);
            fill += take; p += take; n -= take;
            if (fill < 64) return;
            fn(st, buf, 1);
            fill = 0;
        }
        if (n >= 64) { fn(st, p, n / 64); p += n & ~(size_t)63; n &= 63; }
        if (n) { memcpy(buf, p, n); fill = n; }
    }
    void final(unsigned char* md) {
        const uint64_t bits = total * 8;
        uint8_t pad[72] = {0x80};
        const size_t padlen = (fill < 56 ? 56 : 120) - fill;
        uint8_t len[8];
        for (int i = 0; i < 8; i++) len[i] = (uint8_t)(bits >> (56 - 8 * i));
        update(pad, padlen);
        update(len, 8);
        for (int i = 0; i < 8; i++) {
            md[4 * i] = (unsigned char)(st[i] >> 24); md[4 * i + 1] = (unsigned char)(st[i] >> 16);
            md[4 * i + 2] = (unsigned char)(st[i] >> 8); md[4 * i + 3] = (unsigned char)st[i];
        }
    }
};

}  // namespace sha256
