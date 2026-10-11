// Benchmark driver: for each config bin, run create/simulate/finish REPS times in one process.
// Prints the first (cold) and the best (warm) simulate time, so cold-start cost is visible.
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <vector>
#include <chrono>
#include <cstring>
#include <linux/perf_event.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>
static int open_counter(uint64_t config) {
    perf_event_attr a; memset(&a, 0, sizeof a);
    a.type = PERF_TYPE_HARDWARE; a.size = sizeof a; a.config = config;
    a.exclude_kernel = 1; a.exclude_hv = 1;
    return (int)syscall(SYS_perf_event_open, &a, 0, -1, -1, 0);
}
static uint64_t rd(int fd) { uint64_t v = 0; if (fd >= 0 && read(fd, &v, 8) != 8) v = 0; return v; }
extern "C" {
struct T3Result; void* t3_create(const int64_t*, const double*, int32_t, const int64_t*, const double*);
int t3_simulate(void*); T3Result* t3_finish(void*);
void t3_free(T3Result*);
}
int main(int argc, char** argv) {
    int reps = atoi(argv[1]);
    double sum_first = 0, sum_best = 0, sum_cyc = 0, sum_ins = 0; int n = 0;
    int fc = open_counter(PERF_COUNT_HW_CPU_CYCLES), fi = open_counter(PERF_COUNT_HW_INSTRUCTIONS);
    for (int a = 2; a < argc; a++) {
        FILE* f = fopen(argv[a], "rb");
        int64_t nci, ncf, na; std::vector<int64_t> ci; std::vector<double> cf, af; std::vector<int64_t> ai;
        fread(&nci, 8, 1, f); ci.resize(nci); fread(ci.data(), 8, nci, f);
        fread(&ncf, 8, 1, f); cf.resize(ncf); fread(cf.data(), 8, ncf, f);
        fread(&na, 8, 1, f); ai.resize(na * 8); af.resize(na * 4); fread(ai.data(), 8, na * 8, f); fread(af.data(), 8, na * 4, f);
        fclose(f);
        double first = 0, best = 1e9; long long nt = 0; uint64_t bc = ~0ull, bi = ~0ull;
        for (int r = 0; r < reps; r++) {
            void* h = t3_create(ci.data(), cf.data(), (int32_t)na, ai.data(), af.data());
            uint64_t c0 = rd(fc), i0 = rd(fi);
            auto t0 = std::chrono::steady_clock::now();
            t3_simulate(h);
            double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            uint64_t c1 = rd(fc) - c0, i1 = rd(fi) - i0;
            if (c1 < bc) bc = c1;
            if (i1 < bi) bi = i1;
            T3Result* res = t3_finish(h);
            nt = (long long)*(int64_t*)res;
            t3_free(res);
            if (r == 0) first = s;
            if (s < best) best = s;
        }
        const char* nm = strrchr(argv[a], '/'); nm = nm ? nm + 1 : argv[a];
        printf("%-40s n=%8lld first=%9.0f best=%9.0f eps  (%.1f ns/ev)  cyc/ev=%.0f ins/ev=%.0f\n", nm, nt, nt / first, nt / best, best / nt * 1e9, (double)bc / nt, (double)bi / nt);
        sum_cyc += (double)bc / nt; sum_ins += (double)bi / nt;
        sum_first += nt / first; sum_best += nt / best; n++;
    }
    printf("MEAN first=%.0f best=%.0f over %d   cyc/ev=%.1f ins/ev=%.1f\n", sum_first / n, sum_best / n, n, sum_cyc / n, sum_ins / n);
}
