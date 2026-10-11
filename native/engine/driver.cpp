// Standalone driver for profiling: reads the flat config written by dump_cfg.py.
#include <cstdio>
#include <cstdint>
#include <vector>
#include <chrono>
extern "C" {
struct T3Result; void* t3_create(const int64_t*, const double*, int32_t, const int64_t*, const double*);
int t3_simulate(void*); T3Result* t3_finish(void*);
void t3_free(T3Result*);
}
int main(int argc, char** argv) {
    FILE* f = fopen(argv[1], "rb");
    int64_t nci, ncf, na; std::vector<int64_t> ci; std::vector<double> cf, af; std::vector<int64_t> ai;
    fread(&nci, 8, 1, f); ci.resize(nci); fread(ci.data(), 8, nci, f);
    fread(&ncf, 8, 1, f); cf.resize(ncf); fread(cf.data(), 8, ncf, f);
    fread(&na, 8, 1, f); ai.resize(na * 8); af.resize(na * 4); fread(ai.data(), 8, na * 8, f); fread(af.data(), 8, na * 4, f);
    fclose(f);
    void* h = t3_create(ci.data(), cf.data(), (int32_t)na, ai.data(), af.data());
    auto t0 = std::chrono::steady_clock::now();
    t3_simulate(h);
    double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    T3Result* r = t3_finish(h);
    printf("n_trace=%lld sec=%.4f eps=%.0f\n", (long long)*(int64_t*)r, s, *(int64_t*)r / s);
    t3_free(r);
}
