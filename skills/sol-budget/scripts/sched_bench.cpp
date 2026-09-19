// §6 Scheduling — what the OS costs a stage, for perf/machine_model.md.
//
// Build:  g++ -O3 -std=c++17 -pthread -o sched_bench sched_bench.cpp
// Run:    ./sched_bench [--window-seconds S] [--warmup-seconds N] [--samples N] [--date D]
// Output: a paste-ready `sched:` yaml fragment.
//
// No perf here, deliberately. The rows the model asks for — timer wake jitter, a
// context switch, core to core, and what pinning buys — are all observable from a
// process watching its own clock, and perf is not installed on every target that has
// to be modelled. What perf would add is attribution: which migration, which run
// queue, which IPC drop. That is a debugging tool for a stage that has already blown
// its budget, not an input to the floor, so it stays out of the model.
//
// Jitter is reported as a p99 and a worst case, not a median, and that is the one
// place in this skill where the p99 belongs in the model rather than in the
// measurement: a deadline is missed by the late wake, never by the typical one.

#ifndef __OPTIMIZE__
#error "sched_bench must be built -O3; an unoptimised spin measures the compiler."
#endif

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
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

constexpr int DEFAULT_WARMUP_SECONDS = 30;
constexpr double DEFAULT_WINDOW_SECONDS = 1.0 / 30.0;
constexpr int WAKE_REPS = 2000;
constexpr int SWITCH_REPS = 20000;
constexpr int PING_REPS = 20000;

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

// A thread inherits its creator's affinity mask. Without this, an "unpinned" run
// started after any pinned bench silently runs every thread on one core and reports
// the core count as the benefit of pinning.
void unpin() {
    const int cores = int(sysconf(_SC_NPROCESSORS_ONLN));
    cpu_set_t set;
    CPU_ZERO(&set);
    for (int i = 0; i < cores; ++i) CPU_SET(i, &set);
    pthread_setaffinity_np(pthread_self(), sizeof set, &set);
}

void announce(const char* key) { std::fprintf(stderr, "  %s ...\n", key); }

void emit(const char* key, double value, const char* unit, const std::string& method) {
    const bool ok = value > 0.0 && std::isfinite(value);
    std::printf("  %s: {value: %.6g, unit: %s, method: \"%s\", date: \"%s\", "
                "measured: %s}\n",
                key, value, unit, method.c_str(), g_date.c_str(), ok ? "true" : "false");
}

// How late a periodic wake actually is. A stage that sleeps to its next deadline
// inherits this, and the tail is what misses the deadline.
void bench_timer_jitter(double period) {
    announce("timer_jitter");
    const timespec req{0, long(period * 1e9)};
    std::vector<double> late;
    double next = now_s() + period;
    for (int i = 0; i < WAKE_REPS; ++i) {
        nanosleep(&req, nullptr);
        const double woke = now_s();
        late.push_back(std::max(0.0, woke - next) * 1e9);
        next = woke + period;
    }
    char method[640];
    std::snprintf(method, sizeof method,
                  "sched_bench.cpp nanosleep(%.4gs) in a loop, lateness against the "
                  "intended wake; p99 over %d wakes, median %.0fns, worst %.0fns. The "
                  "p99 is the value because a deadline is missed by the late wake, not "
                  "the typical one",
                  period, WAKE_REPS, percentile(late, 0.5), percentile(late, 1.0));
    emit("timer_jitter", percentile(late, 0.99) * 1e-9, "s", method);
}

// Two threads forced onto one core, handing off through sched_yield. What the
// scheduler charges to swap one runnable thread for another.
void bench_ctx_switch() {
    announce("ctx_switch");
    alignas(64) static std::atomic<int> turn{0};
    std::atomic<bool> stop{false};
    std::thread peer([&] {
        pin_to(0);
        while (!stop.load(std::memory_order_acquire)) {
            while (turn.load(std::memory_order_acquire) != 1 &&
                   !stop.load(std::memory_order_acquire))
                sched_yield();
            turn.store(0, std::memory_order_release);
        }
    });
    pin_to(0);
    std::vector<double> per;
    const int batch = 100;
    for (int s = 0; s < SWITCH_REPS / batch; ++s) {
        const int64_t a = now_ns();
        for (int i = 0; i < batch; ++i) {
            turn.store(1, std::memory_order_release);
            while (turn.load(std::memory_order_acquire) != 0) sched_yield();
        }
        // Two switches per round trip: over to the peer and back.
        per.push_back(double(now_ns() - a) / (batch * 2.0));
    }
    stop.store(true, std::memory_order_release);
    turn.store(1, std::memory_order_release);
    peer.join();
    char method[640];
    std::snprintf(method, sizeof method,
                  "sched_bench.cpp two threads pinned to cpu0 handing off through "
                  "sched_yield, counted as two switches per round trip; median of %d "
                  "batches of %d, p99 %.0fns",
                  SWITCH_REPS / batch, batch, percentile(per, 0.99));
    emit("ctx_switch", percentile(per, 0.5) * 1e-9, "s", method);
}

// One cache line, two cores. Reported per pair the topology makes distinct, because
// a pipeline that hands off across a cluster boundary pays a different price.
double ping_pong(int cpu_a, int cpu_b) {
    alignas(64) static std::atomic<int> flag{0};
    flag.store(0, std::memory_order_release);
    std::thread peer([&] {
        pin_to(cpu_b);
        for (int i = 0; i < PING_REPS; ++i) {
            while (flag.load(std::memory_order_acquire) != 1) ;
            flag.store(2, std::memory_order_release);
        }
    });
    pin_to(cpu_a);
    // Median of batches, not the mean over all reps: §8's shm_rtt is measured that
    // way and these two rows describe the same hardware handoff, so a mean here —
    // which swallows every scheduling outlier — would put them 4x apart for no
    // physical reason.
    constexpr int BATCH = 400;
    std::vector<double> per;
    for (int done = 0; done < PING_REPS; done += BATCH) {
        const int64_t a = now_ns();
        for (int i = 0; i < BATCH; ++i) {
            flag.store(1, std::memory_order_release);
            while (flag.load(std::memory_order_acquire) != 2) ;
            flag.store(0, std::memory_order_release);
        }
        per.push_back(double(now_ns() - a) / BATCH);
    }
    peer.join();
    return percentile(per, 0.5);
}

void bench_core_to_core(int cores) {
    announce("core_to_core");
    const double near = ping_pong(0, 1);
    const double far = cores > 4 ? ping_pong(0, cores - 1) : near;
    char method[640];
    std::snprintf(method, sizeof method,
                  "sched_bench.cpp one cache line round trip, cpu0<->cpu1, %d reps; the "
                  "widest pair on this machine (cpu0<->cpu%d) measured %.0fns, a %.2fx "
                  "spread — a handoff that crosses it pays the difference",
                  PING_REPS, cores - 1, far, far / near);
    emit("core_to_core", near * 1e-9, "s", method);
}

// What pinning is worth. Same spin, once pinned and once left to the scheduler.
void bench_pinning(double seconds) {
    announce("pin_benefit");
    auto spin = [&](bool pinned) {
        unpin();  // threads inherit this mask; see unpin()
        std::atomic<long> laps{0};
        std::vector<std::thread> pool;
        const double until = now_s() + seconds;
        const int cores = int(sysconf(_SC_NPROCESSORS_ONLN));
        for (int t = 0; t < cores; ++t)
            pool.emplace_back([&, t] {
                if (pinned) pin_to(t);
                long mine = 0;
                volatile double acc = 0.0;
                while (now_s() < until) {
                    for (int i = 0; i < 10000; ++i) acc += double(i) * 0.5;
                    ++mine;
                }
                laps.fetch_add(mine, std::memory_order_relaxed);
            });
        for (auto& th : pool) th.join();
        return double(laps.load());
    };
    const double loose = spin(false);
    const double tight = spin(true);
    char method[640];
    std::snprintf(method, sizeof method,
                  "sched_bench.cpp identical spin on every core for %.1fs, once pinned "
                  "and once left to the scheduler: pinned did %.0f laps against %.0f, "
                  "a %.3fx difference. A ratio near 1.0 means placement is not costing "
                  "this machine anything and pinning buys nothing here",
                  seconds, tight, loose, tight / loose);
    emit("pin_benefit", tight / loose, "ratio", method);
}

}  // namespace

int main(int argc, char** argv) {
    int warm = DEFAULT_WARMUP_SECONDS;
    double window = DEFAULT_WINDOW_SECONDS;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--warmup-seconds" && i + 1 < argc) warm = std::atoi(argv[++i]);
        else if (a == "--window-seconds" && i + 1 < argc) window = std::atof(argv[++i]);
        else if (a == "--date" && i + 1 < argc) g_date = argv[++i];
        else {
            std::fprintf(stderr, "usage: %s [--window-seconds S] [--warmup-seconds N] "
                                 "[--date D]\n", argv[0]);
            return 2;
        }
    }
    if (g_date.empty()) {
        char buf[16];
        const std::time_t t = std::time(nullptr);
        std::strftime(buf, sizeof buf, "%Y-%m-%d", std::localtime(&t));
        g_date = buf;
    }
    setvbuf(stdout, nullptr, _IOLBF, 0);
    if (warm > 0) {
        std::fprintf(stderr, "warming up %ds (§7: a number from a cold machine is about "
                             "a cold machine)\n", warm);
        const double until = now_s() + warm;
        volatile double sink = 0.0;
        while (now_s() < until)
            for (int i = 0; i < 100000; ++i) sink += double(i) * 0.5;
        (void)sink;
    }

    const int cores = int(sysconf(_SC_NPROCESSORS_ONLN));
    std::printf("sched:\n");
    bench_timer_jitter(window);
    bench_ctx_switch();
    bench_core_to_core(cores);
    bench_pinning(2.0);
    std::fprintf(stderr,
                 "\nNo boost-policy row: the governor and its clocks are §7's, and "
                 "thermal_watch.py reports them over the minutes they take to settle.\n");
    return 0;
}
