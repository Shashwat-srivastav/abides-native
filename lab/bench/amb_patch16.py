"""sub16 + deterministic hand-over flag: a rounding-sensitive latency draw counts only if the run used it.
usage: python amb_patch16.py <engine_sub16.cpp> <output.cpp>"""
import io, sys
s = io.open(sys.argv[1], encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in s else "\n"
s = s.replace("\r\n", "\n")


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:80])
    s = s.replace(a, b)


rep("    static i64 latency_from(const Config& c, nprand::NpRandomState& rs) {",
    "    // `sensitive` is set when the draw would round differently if lat_mu were a few ulps off.\n"
    "    static i64 latency_from(const Config& c, nprand::NpRandomState& rs, bool& sensitive) {")
rep("                g_lat_ambiguous.store(true, std::memory_order_relaxed);", "                sensitive = true;")
rep("""                for (uint32_t i = 0; i < CHUNK; i++) buf[(t + i) & MASK] = latency_from(c, rs);
""", """                for (uint32_t i = 0; i < CHUNK; i++) {
                    bool sensitive = false;
                    buf[(t + i) & MASK] = latency_from(c, rs, sensitive);
                    // The helper runs ahead of the event loop, so a sensitive draw only matters if
                    // the loop gets as far as using it: remember the index of the first one. (Set
                    // before `tail` moves past it, so the loop sees it by the time it can read the value.)
                    if (__builtin_expect(sensitive, 0) && first_sensitive.load(std::memory_order_relaxed) == UINT32_MAX)
                        first_sensitive.store(t + i, std::memory_order_release);
                }
""")
rep("""        alignas(64) std::atomic<int> go{0};         // 0 parked, 1 produce, 2 stop
""", """        alignas(64) std::atomic<int> go{0};         // 0 parked, 1 produce, 2 stop
        std::atomic<uint32_t> first_sensitive{UINT32_MAX};  // index of the first rounding-sensitive draw
""")
rep("""        i64 v = latency_from(c, latency_rs);
""", """        bool sensitive = false;
        i64 v = latency_from(c, latency_rs, sensitive);
        if (__builtin_expect(sensitive, 0)) g_lat_ambiguous.store(true, std::memory_order_relaxed);
""")
rep("""        if (feed) feed->stop();
        finish_trace_rows();
""", """        if (feed) {
            // Ring values the loop used are the indices below f_head (inline draws of the start-up
            // phase are counted in f_head too and were checked as they were drawn). If the loop
            // never used the ring, every draw was inline and the helper's flags do not apply.
            if (feed_mode == 2 && feed->first_sensitive.load(std::memory_order_acquire) < f_head)
                g_lat_ambiguous.store(true, std::memory_order_relaxed);
            feed->stop();
        }
        finish_trace_rows();
""")
io.open(sys.argv[2], "w", encoding="utf-8", newline="").write(s.replace("\n", nl))
print("written", sys.argv[2])
