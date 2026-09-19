// §4 Isolated — what one unit sustains, for perf/machine_model.md.
//
// Build:  g++ -O3 -std=c++17 -pthread -o unit_bench unit_bench.cpp
//
// -O3, not -O2, and it is load-bearing: gcc only auto-vectorises at -O3, and on the
// JP6 Orin the same source reads 1.75e10 op/s at -O2 against 4.76e10 at -O3. A floor
// built from the -O2 number is 2.7x too low, which raises every SOL above it and
// makes a stage that has real headroom read as though it were already at the metal.
// -march=native changed nothing there; baseline aarch64 already carries NEON.
// Run:    ./unit_bench [--window-seconds S] [--warmup-seconds N] [--samples N] [--date D]
// Output: a paste-ready `units:` yaml fragment for the `cpu` and `cpu_1core` units.
//
// Sustained, never peak: every throughput row runs for at least ten windows, so a
// burst that fits in a turbo budget or a cache cannot pass for a rate. `--window-seconds`
// is the pipeline's deadline; the floor of 2s below it keeps a 30fps window from
// producing a third-of-a-second "sustained" number.
//
// Two units, because a floor that assumes the wrong width is worse than no floor:
// `cpu` is every core at once, `cpu_1core` is one pinned core. A node that runs
// single-threaded against the all-core rate gets an SOL far below what it can reach,
// and reads as though there were headroom that does not exist.
//
// The GPU is deliberately absent. nvcc lives off PATH on the target and a CUDA row
// needs a .cu translation unit, which is step 5's lane; leaving those rows out keeps
// them `measured: false`, which sol.py refuses to spend.

#include <algorithm>
#include <atomic>
#include <cmath>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <pthread.h>
#include <sched.h>
#include <unistd.h>

#ifndef __OPTIMIZE__
#error "unit_bench measures what the machine sustains, not what an unoptimised build \
does. Build it -O3; see the header for the 2.7x this costs."
#endif

namespace {

constexpr int DEFAULT_SAMPLES = 9;
constexpr int DEFAULT_WARMUP_SECONDS = 30;
constexpr double DEFAULT_WINDOW_SECONDS = 1.0 / 30.0;
constexpr double WINDOWS_PER_SAMPLE = 10.0;
constexpr double MIN_SUSTAINED_SECONDS = 2.0;
// Independent accumulators, so the loop measures throughput rather than the
// latency of one dependency chain.
constexpr int LANES = 8;
// Past this target's 4MiB L3 by a wide margin, so a stream row is DRAM, not cache.
constexpr size_t STREAM_BYTES = 256u << 20;
constexpr int LATENCY_REPS = 2000;

int g_samples = DEFAULT_SAMPLES;
double g_sustained_seconds = MIN_SUSTAINED_SECONDS;
std::string g_date;

double now_s() {
    timespec t{};
    clock_gettime(CLOCK_MONOTONIC, &t);
    return double(t.tv_sec) + double(t.tv_nsec) * 1e-9;
}

int64_t now_ns() {
    timespec t{};
    clock_gettime(CLOCK_MONOTONIC, &t);
    return int64_t(t.tv_sec) * 1000000000LL + t.tv_nsec;
}

double percentile(std::vector<double> v, double q) {
    std::sort(v.begin(), v.end());
    return v[size_t(q * double(v.size() - 1) + 0.5)];
}

void pin_to(int cpu) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    pthread_setaffinity_np(pthread_self(), sizeof set, &set);
}

void announce(const char* key) {
    std::fprintf(stderr, "  %s ...\n", key);
}

void emit(const char* unit, const char* key, double value, const char* u,
          const std::string& method) {
    const bool ok = value > 0.0 && std::isfinite(value);
    std::printf("    %s: {value: %.6g, unit: %s, method: \"%s\", date: \"%s\", "
                "measured: %s}\n",
                key, value, u, method.c_str(), g_date.c_str(), ok ? "true" : "false");
    (void)unit;
}

// --- sustained throughput ------------------------------------------------------

// Multiply-accumulates retired per second by `threads` cores running for the whole
// sustained window. Returns ops/s counting one mul and one add per FMA.
double sustained_ops(int threads, const int* cpus) {
    // Each thread divides its own work by its own elapsed time. Threads are spawned
    // serially against one shared deadline, so a later one runs measurably less;
    // dividing everyone's work by the wall clock under-reports the rate by ~1%.
    std::vector<double> rate(size_t(threads), 0.0);
    std::vector<std::thread> pool;
    const double until = now_s() + g_sustained_seconds;
    for (int t = 0; t < threads; ++t) {
        pool.emplace_back([&, t] {
            if (cpus) pin_to(cpus[t]);
            double acc[LANES];
            for (int i = 0; i < LANES; ++i) acc[i] = double(i) + 1.0;
            const double m = 1.0000001, c = 0.0000001;
            long iterations = 0;
            const double started = now_s();
            while (now_s() < until) {
                for (int rep = 0; rep < 4096; ++rep)
                    for (int i = 0; i < LANES; ++i) acc[i] = acc[i] * m + c;
                iterations += 4096;
            }
            const double mine = now_s() - started;
            double sink = 0.0;
            for (int i = 0; i < LANES; ++i) sink += acc[i];
            // Consume the accumulators so the loop cannot be elided.
            if (std::isnan(sink)) std::fprintf(stderr, "impossible\n");
            rate[size_t(t)] = double(iterations) * LANES * 2.0 / mine;
        });
    }
    for (auto& th : pool) th.join();
    double ops = 0.0;
    for (double v : rate) ops += v;
    return ops;
}

// Bytes copied per second, counting payload moved by the algorithm, not bus traffic.
double sustained_bytes(int threads, const int* cpus) {
    const size_t lanes = size_t(threads);
    const size_t per = STREAM_BYTES / lanes;
    std::vector<std::vector<char>> src(lanes), dst(lanes);
    for (int t = 0; t < threads; ++t) {
        src[size_t(t)].assign(per, char(t + 1));
        dst[size_t(t)].assign(per, 0);
    }
    std::vector<double> rate(lanes, 0.0);
    std::vector<std::thread> pool;
    const double until = now_s() + g_sustained_seconds;
    for (int t = 0; t < threads; ++t) {
        pool.emplace_back([&, t] {
            if (cpus) pin_to(cpus[t]);
            double bytes = 0.0;
            const double started = now_s();
            while (now_s() < until) {
                std::memcpy(dst[size_t(t)].data(), src[size_t(t)].data(), per);
                bytes += double(per);
            }
            rate[size_t(t)] = bytes / (now_s() - started);
        });
    }
    for (auto& th : pool) th.join();
    double total = 0.0;
    for (double v : rate) total += v;
    return total;
}

// --- dispatch and completion ---------------------------------------------------

// One worker parked on a condition variable, the shape a thread-pool stage has.
// Dispatch is submit to worker-observes-it; completion is worker-done to
// submitter-observes-it, once blocking and once spinning, because the skill treats
// a poll and an interrupt as different rows.
struct Handoff {
    std::mutex m;
    std::condition_variable to_worker, to_submitter;
    bool work = false, done = false;
    int64_t submitted = 0, started = 0, finished = 0, observed = 0;
    std::atomic<bool> quit{false};
    std::atomic<int64_t> spin_finished{0};
    std::atomic<bool> spin_done{false};
};

void latency_rows(bool spin_completion, double* dispatch_out, double* completion_out) {
    Handoff h;
    std::thread worker([&] {
        pin_to(1);
        for (;;) {
            std::unique_lock<std::mutex> lk(h.m);
            h.to_worker.wait(lk, [&] { return h.work || h.quit.load(); });
            if (h.quit.load()) return;
            h.started = now_ns();
            h.work = false;
            if (spin_completion) {
                lk.unlock();
                h.spin_finished.store(now_ns(), std::memory_order_release);
                h.spin_done.store(true, std::memory_order_release);
            } else {
                h.finished = now_ns();
                h.done = true;
                lk.unlock();
                h.to_submitter.notify_one();
            }
        }
    });
    pin_to(0);
    std::vector<double> dispatch, completion;
    for (int i = 0; i < LATENCY_REPS; ++i) {
        h.spin_done.store(false, std::memory_order_release);
        {
            std::lock_guard<std::mutex> lk(h.m);
            h.submitted = now_ns();
            h.work = true;
            h.done = false;
        }
        h.to_worker.notify_one();
        if (spin_completion) {
            while (!h.spin_done.load(std::memory_order_acquire)) ;
            h.observed = now_ns();
            h.finished = h.spin_finished.load(std::memory_order_acquire);
        } else {
            std::unique_lock<std::mutex> lk(h.m);
            h.to_submitter.wait(lk, [&] { return h.done; });
            h.observed = now_ns();
        }
        dispatch.push_back(double(h.started - h.submitted));
        completion.push_back(double(h.observed - h.finished));
    }
    h.quit.store(true);
    h.to_worker.notify_one();
    worker.join();
    *dispatch_out = percentile(dispatch, 0.5);
    *completion_out = percentile(completion, 0.5);
}

// --- one unit ------------------------------------------------------------------

void bench_unit(const char* unit, int threads, const int* cpus, const char* width) {
    std::printf("  %s:\n", unit);
    char method[640];

    announce("sustained_ops");
    std::vector<double> ops;
    for (int s = 0; s < g_samples; ++s) ops.push_back(sustained_ops(threads, cpus));
    std::snprintf(method, sizeof method,
                  "unit_bench.cpp independent double multiply-accumulate, %d lanes, "
                  "%s; one mul plus one add counted as two ops; each sample sustained "
                  "%.1fs; median of %d, worst %.3g op/s; g++ %s — the row needs -O3, "
                  "at -O2 gcc does not vectorise and it reads about 2.7x low",
                  LANES, width, g_sustained_seconds, g_samples, percentile(ops, 0.0),
                  __VERSION__);
    emit(unit, "sustained_ops", percentile(ops, 0.5), "op/s", method);

    announce("sustained_bytes");
    std::vector<double> bytes;
    for (int s = 0; s < g_samples; ++s) bytes.push_back(sustained_bytes(threads, cpus));
    std::snprintf(method, sizeof method,
                  "unit_bench.cpp memcpy stream over %zuMiB split across %s, past this "
                  "target's last-level cache; bytes copied, not bus traffic — halve for "
                  "read+write; each sample sustained %.1fs; median of %d, worst %.3g B/s",
                  STREAM_BYTES >> 20, width, g_sustained_seconds, g_samples,
                  percentile(bytes, 0.0));
    emit(unit, "sustained_bytes", percentile(bytes, 0.5), "B/s", method);
}

}  // namespace

int main(int argc, char** argv) {
    int warm = DEFAULT_WARMUP_SECONDS;
    double window = DEFAULT_WINDOW_SECONDS;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--samples" && i + 1 < argc) g_samples = std::atoi(argv[++i]);
        else if (a == "--warmup-seconds" && i + 1 < argc) warm = std::atoi(argv[++i]);
        else if (a == "--window-seconds" && i + 1 < argc) window = std::atof(argv[++i]);
        else if (a == "--date" && i + 1 < argc) g_date = argv[++i];
        else {
            std::fprintf(stderr, "usage: %s [--window-seconds S] [--warmup-seconds N] "
                                 "[--samples N] [--date D]\n", argv[0]);
            return 2;
        }
    }
    if (g_date.empty()) {
        char buf[16];
        const std::time_t t = std::time(nullptr);
        std::strftime(buf, sizeof buf, "%Y-%m-%d", std::localtime(&t));
        g_date = buf;
    }
    g_sustained_seconds = std::max(MIN_SUSTAINED_SECONDS, WINDOWS_PER_SAMPLE * window);
    setvbuf(stdout, nullptr, _IOLBF, 0);

    const int cores = int(sysconf(_SC_NPROCESSORS_ONLN));
    const size_t ncores = size_t(cores);
    std::vector<int> all(ncores);
    for (int i = 0; i < cores; ++i) all[size_t(i)] = i;
    const int one[1] = {0};

    if (warm > 0) {
        std::fprintf(stderr, "warming up %ds (§7: a number from a cold machine is about "
                             "a cold machine)\n", warm);
        const double until = now_s() + warm;
        volatile double sink = 0.0;
        while (now_s() < until)
            for (int i = 0; i < 100000; ++i) sink += double(i) * 0.5;
        (void)sink;
    }
    std::fprintf(stderr, "window %.4gs, each sustained sample %.1fs (>= %gx the window)\n",
                 window, g_sustained_seconds, WINDOWS_PER_SAMPLE);

    std::printf("units:\n");
    char width[64];
    std::snprintf(width, sizeof width, "%d cores, one thread pinned per core", cores);
    bench_unit("cpu", cores, all.data(), width);

    // Dispatch and completion belong to the handoff, not to the width, so they are
    // measured once between two pinned cores and reported on both units.
    announce("dispatch_latency / completion_latency");
    double dispatch = 0.0, blocking = 0.0, spin_dispatch = 0.0, spinning = 0.0;
    latency_rows(false, &dispatch, &blocking);
    latency_rows(true, &spin_dispatch, &spinning);
    char method[640];
    std::snprintf(method, sizeof method,
                  "unit_bench.cpp submit to worker-observes-it, one worker parked on a "
                  "condition variable, submitter on cpu0 and worker on cpu1; median of %d",
                  LATENCY_REPS);
    emit("cpu", "dispatch_latency", dispatch * 1e-9, "s", method);
    std::snprintf(method, sizeof method,
                  "unit_bench.cpp worker-done to submitter-observes-it via condition "
                  "variable — the blocking mechanism; the spinning one measured %.0fns "
                  "in the same run and is the completion_latency_poll row; median of %d",
                  spinning, LATENCY_REPS);
    emit("cpu", "completion_latency", blocking * 1e-9, "s", method);
    std::snprintf(method, sizeof method,
                  "unit_bench.cpp worker-done to submitter-observes-it while spinning on "
                  "an atomic — a poll and an interrupt are different rows; costs a core "
                  "for the whole wait; median of %d",
                  LATENCY_REPS);
    emit("cpu", "completion_latency_poll", spinning * 1e-9, "s", method);

    bench_unit("cpu_1core", 1, one, "1 core pinned to cpu0");
    emit("cpu_1core", "dispatch_latency", dispatch * 1e-9, "s",
         "unit_bench.cpp same handoff as the cpu unit — the cost belongs to the "
         "mechanism, not to how many cores run the work");
    emit("cpu_1core", "completion_latency", blocking * 1e-9, "s",
         "unit_bench.cpp same handoff as the cpu unit, condition variable");

    std::fprintf(stderr, "\nNo gpu/dla rows: a CUDA unit needs a .cu translation unit "
                         "(step 5). They stay `measured: false` and sol.py refuses them.\n");
    return 0;
}
