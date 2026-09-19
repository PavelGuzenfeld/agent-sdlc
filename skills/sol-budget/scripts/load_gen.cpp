// Offered load on the shared fabric, for §5's contention sweep.
//
// Build:  g++ -O3 -std=c++17 -pthread -o load_gen load_gen.cpp
// Run:    ./load_gen --threads N --seconds S [--bytes MiB] [--quiet]
// Prints: the traffic it actually generated, so the sweep records offered load as a
//         measurement rather than as the number it asked for.
//
// This is not a benchmark. It exists so contention_sweep.py can put a known amount of
// traffic on the fabric while something else is being timed, and so the §5 table can
// say what the load actually was. A generator that reports its request instead of its
// delivery makes every knee on that table a guess: the moment the fabric saturates is
// exactly the moment the generator stops keeping up, so that is the moment its own
// number stops being true.

#ifndef __OPTIMIZE__
#error "load_gen must be built -O3; an unoptimised memcpy loop offers a load nobody \
in production would generate."
#endif

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <string>
#include <thread>
#include <vector>

#include <pthread.h>
#include <sched.h>
#include <unistd.h>

namespace {

constexpr size_t DEFAULT_MIB = 256;

double now_s() {
    timespec t{};
    clock_gettime(CLOCK_MONOTONIC, &t);
    return double(t.tv_sec) + double(t.tv_nsec) * 1e-9;
}

void pin_to(int cpu) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    pthread_setaffinity_np(pthread_self(), sizeof set, &set);
}

}  // namespace

int main(int argc, char** argv) {
    int threads = 1;
    double seconds = 1.0;
    size_t mib = DEFAULT_MIB;
    bool quiet = false;
    // Cores the victim is not using. A generator that lands on the victim's core
    // measures core contention and calls it fabric contention.
    int first_core = 0;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--threads" && i + 1 < argc) threads = std::atoi(argv[++i]);
        else if (a == "--seconds" && i + 1 < argc) seconds = std::atof(argv[++i]);
        else if (a == "--bytes" && i + 1 < argc) mib = size_t(std::atol(argv[++i]));
        else if (a == "--first-core" && i + 1 < argc) first_core = std::atoi(argv[++i]);
        else if (a == "--quiet") quiet = true;
        else {
            std::fprintf(stderr,
                         "usage: %s --threads N --seconds S [--bytes MiB] [--first-core C] [--quiet]\n",
                         argv[0]);
            return 2;
        }
    }
    if (threads < 1 || seconds <= 0) {
        std::fprintf(stderr, "--threads must be >= 1 and --seconds > 0\n");
        return 2;
    }

    const int cores = int(sysconf(_SC_NPROCESSORS_ONLN));
    const size_t lanes = size_t(threads);
    const size_t per = (mib << 20) / lanes;
    std::vector<std::vector<char>> src(lanes), dst(lanes);
    for (size_t t = 0; t < lanes; ++t) {
        src[t].assign(per, char(t + 1));
        dst[t].assign(per, 0);
    }

    std::vector<double> rate(lanes, 0.0);
    std::vector<std::thread> pool;
    const double until = now_s() + seconds;
    for (int t = 0; t < threads; ++t) {
        pool.emplace_back([&, t] {
            // Spread across cores rather than stacking on one: the point is fabric
            // pressure, and one saturated core cannot generate it.
            pin_to(first_core + (t % std::max(1, cores - first_core)));
            double moved = 0.0;
            const double started = now_s();
            while (now_s() < until) {
                std::memcpy(dst[size_t(t)].data(), src[size_t(t)].data(), per);
                moved += double(per);
            }
            rate[size_t(t)] = moved / (now_s() - started);
        });
    }
    for (auto& th : pool) th.join();

    double delivered = 0.0;
    for (double v : rate) delivered += v;
    if (!quiet)
        std::printf("{\"generator\": \"load_gen.cpp\", \"unit\": \"cpu\", "
                    "\"threads\": %d, \"seconds\": %.3f, \"buffer_mib\": %zu, "
                    "\"delivered_bytes_per_s\": %.6g}\n",
                    threads, seconds, mib, delivered);
    return 0;
}
