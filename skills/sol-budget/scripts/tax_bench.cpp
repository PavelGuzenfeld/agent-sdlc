// §8 Tax — fixed cost per crossing, for perf/machine_model.md.
//
// Build:  g++ -O2 -std=c++17 -pthread -o tax_bench tax_bench.cpp
// Run:    ./tax_bench [--warmup-seconds N] [--samples N] [--date YYYY-MM-DD]
// Output: a paste-ready `tax:` yaml fragment. Every row carries method: and date:.
//
// A tax row is a floor, so its value is the median over samples, not the p99: the
// p99 belongs on the measurement side of the comparison, never in the ceiling it is
// compared against. Each method: string carries the p99 anyway, because a crossing
// whose p99 is far from its median is a scheduling finding (§6), not a tax finding.
//
// Batch-then-divide: one clock_gettime pair costs tens of nanoseconds, which is the
// same order as the cheapest rows here. Each sample times a whole batch and divides;
// an empty batch of the same shape is subtracted as loop overhead.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <string>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <linux/futex.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <pthread.h>
#include <sched.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <unistd.h>

namespace {

constexpr int DEFAULT_SAMPLES = 33;
constexpr int DEFAULT_WARMUP_SECONDS = 30;
constexpr long BATCH = 20000;
constexpr size_t PAGE_BYTES = 4096;
constexpr size_t COPY_BYTES = 64u << 20;
// Round trips per timed sample. Fixed, not derived: the echo side has to expect the
// exact count the client sends, and `reps / samples` silently leaves it waiting.
constexpr int RTT_PER_SAMPLE = 400;

int g_samples = DEFAULT_SAMPLES;
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
    const size_t i = size_t(q * double(v.size() - 1) + 0.5);
    return v[i];
}

// Named before it runs, not after: these rows take minutes and one of them blocking
// on a full socket looks exactly like one of them being slow.
void announce(const char* key) {
    std::fprintf(stderr, "  %s ...\n", key);
}

void emit(const char* key, double value, const char* unit, const std::string& method) {
    const bool ok = value > 0.0 && std::isfinite(value);
    std::printf("  %s: {value: %.6g, unit: %s, method: \"%s\", date: \"%s\", measured: %s}\n",
                key, value, unit, method.c_str(), g_date.c_str(), ok ? "true" : "false");
}

// Median seconds per operation over `g_samples` batched samples, loop overhead removed.
// `body(reps)` must run exactly `reps` operations; `empty(reps)` the same loop with none.
template <typename Body, typename Empty>
void row(const char* key, const char* what, long reps, Body body, Empty empty) {
    announce(key);
    std::vector<double> per_op;
    per_op.reserve(size_t(g_samples));
    double overhead = 0.0;
    {
        std::vector<double> o;
        for (int s = 0; s < g_samples; ++s) {
            const int64_t a = now_ns();
            empty(reps);
            o.push_back(double(now_ns() - a) / double(reps));
        }
        overhead = percentile(o, 0.5);
    }
    for (int s = 0; s < g_samples; ++s) {
        const int64_t a = now_ns();
        body(reps);
        const double ns = double(now_ns() - a) / double(reps);
        per_op.push_back(std::max(0.0, ns - overhead));
    }
    char method[512];
    std::snprintf(method, sizeof method,
                  "tax_bench.cpp %s; median of %d batches of %ld, loop overhead %.1fns "
                  "subtracted; p99 %.1fns",
                  what, g_samples, reps, overhead, percentile(per_op, 0.99));
    emit(key, percentile(per_op, 0.5) * 1e-9, "s", method);
}

void pin_to(int cpu) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    pthread_setaffinity_np(pthread_self(), sizeof set, &set);
}

void warmup(int seconds) {
    if (seconds <= 0) return;
    std::fprintf(stderr, "warming up %ds (§7: a number from a cold machine is about a "
                         "cold machine)\n", seconds);
    const double until = now_s() + seconds;
    volatile double sink = 0.0;
    while (now_s() < until)
        for (int i = 0; i < 100000; ++i) sink += double(i) * 0.5;
    (void)sink;
}

// --- individual crossings ------------------------------------------------------

void bench_syscall() {
    row("syscall", "getpid() through syscall(2), no vDSO shortcut", BATCH,
        [](long n) { for (long i = 0; i < n; ++i) syscall(SYS_getpid); },
        [](long n) { for (long i = 0; i < n; ++i) asm volatile(""); });
}

void bench_clock() {
    row("clock_gettime_vdso", "clock_gettime(CLOCK_MONOTONIC) via the vDSO", BATCH,
        [](long n) { timespec t{}; for (long i = 0; i < n; ++i) clock_gettime(CLOCK_MONOTONIC, &t); },
        [](long n) { for (long i = 0; i < n; ++i) asm volatile(""); });
    row("clock_gettime_syscall", "the same clock forced through syscall(2)", BATCH / 4,
        [](long n) { timespec t{}; for (long i = 0; i < n; ++i) syscall(SYS_clock_gettime, CLOCK_MONOTONIC, &t); },
        [](long n) { for (long i = 0; i < n; ++i) asm volatile(""); });
}

void bench_sleep_granularity() {
    announce("sleep_granularity");
    // What a 1ns sleep actually costs: the floor under every poll loop that sleeps.
    std::vector<double> v;
    for (int s = 0; s < g_samples; ++s) {
        const timespec req{0, 1};
        const int64_t a = now_ns();
        nanosleep(&req, nullptr);
        v.push_back(double(now_ns() - a));
    }
    char method[512];
    std::snprintf(method, sizeof method,
                  "tax_bench.cpp nanosleep(1ns) wall cost; median of %d, p99 %.0fns",
                  g_samples, percentile(v, 0.99));
    emit("sleep_granularity", percentile(v, 0.5) * 1e-9, "s", method);
}

void bench_malloc(size_t bytes, const char* key) {
    const long reps = 2000;
    char what[192];
    std::snprintf(what, sizeof what,
                  "malloc+free of %zuB, same size repeatedly so the allocator stays warm "
                  "— bookkeeping only, one byte touched; the page cost is the page_fault row",
                  bytes);
    row(key, what, reps,
        [bytes](long n) {
            for (long i = 0; i < n; ++i) { void* p = std::malloc(bytes); if (p) { *(char*)p = 1; std::free(p); } }
        },
        [](long n) { for (long i = 0; i < n; ++i) asm volatile(""); });
}

void bench_page_fault() {
    announce("page_fault");
    // Cost of the first touch of an anonymous page: mmap is lazy, so this is the
    // fault, not the mapping. MAP_POPULATE would measure something else entirely.
    const long pages = 4096;
    std::vector<double> v;
    for (int s = 0; s < g_samples; ++s) {
        char* p = (char*)mmap(nullptr, size_t(pages) * PAGE_BYTES, PROT_READ | PROT_WRITE,
                              MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (p == MAP_FAILED) { std::perror("mmap"); return; }
        const int64_t a = now_ns();
        for (long i = 0; i < pages; ++i) p[size_t(i) * PAGE_BYTES] = 1;
        v.push_back(double(now_ns() - a) / double(pages));
        munmap(p, size_t(pages) * PAGE_BYTES);
    }
    char method[512];
    std::snprintf(method, sizeof method,
                  "tax_bench.cpp first touch of %ld anonymous 4KiB pages, median of %d, "
                  "p99 %.0fns",
                  pages, g_samples, percentile(v, 0.99));
    emit("page_fault", percentile(v, 0.5) * 1e-9, "s", method);
}

void bench_mutex() {
    static pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;
    row("mutex_uncontended", "pthread_mutex lock+unlock, no other thread", BATCH,
        [](long n) { for (long i = 0; i < n; ++i) { pthread_mutex_lock(&m); pthread_mutex_unlock(&m); } },
        [](long n) { for (long i = 0; i < n; ++i) asm volatile(""); });
}

void bench_futex_wake() {
    announce("futex_wake");
    // Wake latency, not round trip: one waiter parked in FUTEX_WAIT, timed from the
    // waker's FUTEX_WAKE to the waiter observing it.
    alignas(64) static int word = 0;
    std::vector<double> v;
    for (int s = 0; s < g_samples; ++s) {
        word = 0;
        int64_t woke = 0;
        std::thread waiter([&] {
            while (__atomic_load_n(&word, __ATOMIC_ACQUIRE) == 0)
                syscall(SYS_futex, &word, FUTEX_WAIT, 0, nullptr, nullptr, 0);
            woke = now_ns();
        });
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        const int64_t a = now_ns();
        __atomic_store_n(&word, 1, __ATOMIC_RELEASE);
        syscall(SYS_futex, &word, FUTEX_WAKE, 1, nullptr, nullptr, 0);
        waiter.join();
        v.push_back(double(woke - a));
    }
    char method[512];
    std::snprintf(method, sizeof method,
                  "tax_bench.cpp FUTEX_WAKE to waiter observing it, one parked waiter; "
                  "median of %d, p99 %.0fns",
                  g_samples, percentile(v, 0.99));
    emit("futex_wake", percentile(v, 0.5) * 1e-9, "s", method);
}

void bench_file_io() {
    char path[] = "/tmp/tax_bench_ioXXXXXX";
    const int fd = mkstemp(path);
    if (fd < 0) { std::perror("mkstemp"); return; }
    unlink(path);
    static char buf[PAGE_BYTES];
    const long reps = 20000;
    // pwrite/pread, not lseek+write: an offset argument keeps the row one syscall.
    ssize_t seed = pwrite(fd, buf, sizeof buf, 0);
    (void)seed;
    row("file_write", "pwrite(2) of 4KiB to a tmpfile, page cache warm, no fsync", reps,
        [fd](long n) { for (long i = 0; i < n; ++i) { ssize_t r = pwrite(fd, buf, sizeof buf, 0); (void)r; } },
        [](long n) { for (long i = 0; i < n; ++i) asm volatile(""); });
    row("file_read", "pread(2) of 4KiB from the page cache", reps,
        [fd](long n) { for (long i = 0; i < n; ++i) { ssize_t r = pread(fd, buf, sizeof buf, 0); (void)r; } },
        [](long n) { for (long i = 0; i < n; ++i) asm volatile(""); });
    close(fd);
}

// Round trip over an already-connected pair, one 64B message each way.
// UDP can drop on loopback under load, and a blocking recv on a lost datagram is a
// deadlock, not a slow row. Both ends carry a receive timeout; a drop abandons the
// row as `measured: false`, which sol.py refuses to spend — the correct outcome.
void pair_rtt(const char* key, const char* what, int a, int b) {
    announce(key);
    const timeval one_second{1, 0};
    setsockopt(a, SOL_SOCKET, SO_RCVTIMEO, &one_second, sizeof one_second);
    setsockopt(b, SOL_SOCKET, SO_RCVTIMEO, &one_second, sizeof one_second);
    std::atomic<bool> lost{false};
    std::thread echo([b, &lost] {
        char in[64];
        for (long i = 0; i < long(g_samples) * RTT_PER_SAMPLE; ++i) {
            if (recv(b, in, sizeof in, 0) <= 0 || send(b, in, sizeof in, 0) <= 0) {
                lost = true;
                return;
            }
        }
    });
    std::vector<double> v;
    for (int s = 0; s < g_samples && !lost; ++s) {
        char msg[64] = {};
        const int64_t t0 = now_ns();
        for (long i = 0; i < RTT_PER_SAMPLE; ++i) {
            if (send(a, msg, sizeof msg, 0) <= 0 || recv(a, msg, sizeof msg, 0) <= 0) {
                lost = true;
                break;
            }
        }
        v.push_back(double(now_ns() - t0) / double(RTT_PER_SAMPLE));
    }
    echo.join();
    if (lost) {
        emit(key, 0.0, "s", std::string("tax_bench.cpp ") + what
                            + " — a message was lost or timed out; row abandoned");
        return;
    }
    char method[512];
    std::snprintf(method, sizeof method,
                  "tax_bench.cpp %s, 64B each way; median of %d batches of %d, p99 %.0fns",
                  what, g_samples, RTT_PER_SAMPLE, percentile(v, 0.99));
    emit(key, percentile(v, 0.5) * 1e-9, "s", method);
}

void bench_socketpair_rtts() {
    int fds[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, fds) == 0) {
        pair_rtt("unix_rtt", "AF_UNIX SOCK_STREAM socketpair round trip", fds[0], fds[1]);
        close(fds[0]); close(fds[1]);
    }
    if (socketpair(AF_UNIX, SOCK_DGRAM, 0, fds) == 0) {
        pair_rtt("unix_dgram_rtt", "AF_UNIX SOCK_DGRAM socketpair round trip", fds[0], fds[1]);
        close(fds[0]); close(fds[1]);
    }
}

void bench_udp_loopback_rtt() {
    // Real UDP through 127.0.0.1, not an AF_UNIX datagram stand-in: the loopback
    // device and the IP stack are most of what this row costs.
    int a = socket(AF_INET, SOCK_DGRAM, 0), b = socket(AF_INET, SOCK_DGRAM, 0);
    sockaddr_in la{}, lb{};
    la.sin_family = lb.sin_family = AF_INET;
    la.sin_addr.s_addr = lb.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (a < 0 || b < 0 || bind(a, (sockaddr*)&la, sizeof la) != 0
        || bind(b, (sockaddr*)&lb, sizeof lb) != 0) {
        std::perror("udp bind"); return;
    }
    socklen_t len = sizeof la;
    getsockname(a, (sockaddr*)&la, &len);
    getsockname(b, (sockaddr*)&lb, &len);
    if (connect(a, (sockaddr*)&lb, sizeof lb) != 0 || connect(b, (sockaddr*)&la, sizeof la) != 0) {
        std::perror("udp connect"); return;
    }
    pair_rtt("udp_loopback_rtt", "UDP over 127.0.0.1, both sockets connected", a, b);
    close(a); close(b);
}

void bench_tcp_loopback_rtt() {
    const int srv = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (srv < 0 || bind(srv, (sockaddr*)&addr, sizeof addr) != 0 || listen(srv, 1) != 0) {
        std::perror("tcp setup"); if (srv >= 0) close(srv); return;
    }
    socklen_t len = sizeof addr;
    getsockname(srv, (sockaddr*)&addr, &len);
    const int a = socket(AF_INET, SOCK_STREAM, 0);
    if (connect(a, (sockaddr*)&addr, sizeof addr) != 0) { std::perror("connect"); return; }
    const int b = accept(srv, nullptr, nullptr);
    const int one = 1;
    setsockopt(a, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    setsockopt(b, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    pair_rtt("tcp_loopback_rtt", "TCP over 127.0.0.1 with TCP_NODELAY", a, b);
    close(a); close(b); close(srv);
}

// Send-only cost per datagram. The receive is deliberately outside the timed region:
// with a recv per send the two rows differ by a few percent and the whole point of
// the pair — what batching buys per datagram — disappears into the receive.
void bench_sendmsg_vs_sendmmsg() {
    constexpr int BATCH_MSGS = 32;
    int fds[2];
    if (socketpair(AF_UNIX, SOCK_DGRAM, 0, fds) != 0) { std::perror("socketpair"); return; }
    const int room = 8 << 20;
    setsockopt(fds[0], SOL_SOCKET, SO_SNDBUF, &room, sizeof room);
    setsockopt(fds[1], SOL_SOCKET, SO_RCVBUF, &room, sizeof room);
    static char payload[64] = {};
    char sink[64];

    auto drain = [&] {
        while (recv(fds[1], sink, sizeof sink, MSG_DONTWAIT) > 0) ;
    };
    // How many datagrams actually fit before the socket blocks. Probed, not assumed:
    // SO_SNDBUF is a byte budget the kernel spends on per-skb overhead, not payload,
    // and a blocking send past it deadlocks against a drain that runs afterwards.
    long capacity = 0;
    while (send(fds[0], payload, sizeof payload, MSG_DONTWAIT) > 0) ++capacity;
    drain();
    const long SEND_REPS = (capacity / 2 / BATCH_MSGS) * BATCH_MSGS;
    if (SEND_REPS < BATCH_MSGS) {
        std::fprintf(stderr, "socket holds only %ld datagrams; skipping the send rows\n", capacity);
        close(fds[0]); close(fds[1]);
        return;
    }
    auto sample = [&](const char* key, const char* what, auto send_all) {
        std::vector<double> v;
        for (int s = 0; s < g_samples; ++s) {
            drain();
            const int64_t t0 = now_ns();
            send_all();
            v.push_back(double(now_ns() - t0) / double(SEND_REPS));
        }
        drain();
        char method[512];
        std::snprintf(method, sizeof method,
                      "tax_bench.cpp %s; send only, receive drained outside the timed "
                      "region; median of %d batches of %ld, p99 %.0fns",
                      what, g_samples, SEND_REPS, percentile(v, 0.99));
        emit(key, percentile(v, 0.5) * 1e-9, "s", method);
    };

    sample("sendmsg", "sendmsg(2), one 64B datagram per call", [&] {
        iovec io{payload, sizeof payload};
        msghdr h{}; h.msg_iov = &io; h.msg_iovlen = 1;
        for (long i = 0; i < SEND_REPS; ++i) sendmsg(fds[0], &h, 0);
    });
    sample("sendmmsg", "sendmmsg(2), 32 of the same 64B datagrams per call", [&] {
        iovec io[BATCH_MSGS];
        mmsghdr h[BATCH_MSGS];
        for (int i = 0; i < BATCH_MSGS; ++i) {
            io[i] = iovec{payload, sizeof payload};
            h[i] = mmsghdr{};
            h[i].msg_hdr.msg_iov = &io[i];
            h[i].msg_hdr.msg_iovlen = 1;
        }
        for (long i = 0; i < SEND_REPS; i += BATCH_MSGS) sendmmsg(fds[0], h, BATCH_MSGS, 0);
    });
    close(fds[0]); close(fds[1]);
}

void bench_pipe_rtt() {
    int up[2], down[2];
    if (pipe(up) != 0 || pipe(down) != 0) { std::perror("pipe"); return; }
    const long reps = long(g_samples) * RTT_PER_SAMPLE;
    char msg[64] = {};
    std::thread echo([&] {
        char in[64];
        for (long i = 0; i < reps; ++i) {
            if (read(up[0], in, sizeof in) <= 0) return;
            if (write(down[1], in, sizeof in) <= 0) return;
        }
    });
    std::vector<double> v;
    for (int s = 0; s < g_samples; ++s) {
        const int64_t t0 = now_ns();
        for (long i = 0; i < RTT_PER_SAMPLE; ++i) { ssize_t w = write(up[1], msg, sizeof msg); (void)w; ssize_t r = read(down[0], msg, sizeof msg); (void)r; }
        v.push_back(double(now_ns() - t0) / double(RTT_PER_SAMPLE));
    }
    echo.join();
    char method[512];
    std::snprintf(method, sizeof method,
                  "tax_bench.cpp pipe(2) pair round trip, 64B each way; median of %d "
                  "batches of %d, p99 %.0fns", g_samples, RTT_PER_SAMPLE,
                  percentile(v, 0.99));
    emit("pipe_rtt", percentile(v, 0.5) * 1e-9, "s", method);
    close(up[0]); close(up[1]); close(down[0]); close(down[1]);
}

void bench_shm_rtt() {
    announce("shm_rtt");
    // Two threads, one cache line, no kernel. The floor every IPC row above is
    // measured against: anything slower is paying for the mechanism, not the handoff.
    alignas(64) static volatile int flag = 0;
    const long reps = long(g_samples) * RTT_PER_SAMPLE;
    pin_to(0);
    std::thread peer([&] {
        pin_to(1);
        for (long i = 0; i < reps; ++i) {
            while (__atomic_load_n(&flag, __ATOMIC_ACQUIRE) != 1) ;
            __atomic_store_n(&flag, 2, __ATOMIC_RELEASE);
        }
    });
    std::vector<double> v;
    for (int s = 0; s < g_samples; ++s) {
        const int64_t t0 = now_ns();
        for (long i = 0; i < RTT_PER_SAMPLE; ++i) {
            __atomic_store_n(&flag, 1, __ATOMIC_RELEASE);
            while (__atomic_load_n(&flag, __ATOMIC_ACQUIRE) != 2) ;
            __atomic_store_n(&flag, 0, __ATOMIC_RELEASE);
        }
        v.push_back(double(now_ns() - t0) / double(RTT_PER_SAMPLE));
    }
    peer.join();
    char method[512];
    std::snprintf(method, sizeof method,
                  "tax_bench.cpp shared cache line, spinning threads pinned to cpu0 and "
                  "cpu1; a pair spanning clusters costs more, so §6 owns that spread; "
                  "median of %d batches of %d, p99 %.0fns", g_samples, RTT_PER_SAMPLE,
                  percentile(v, 0.99));
    emit("shm_rtt", percentile(v, 0.5) * 1e-9, "s", method);
}

void bench_cpu_ceiling() {
    // sol.py spends this against a node's crossing_bytes, so it is the copy
    // throughput a crossing can sustain, not a peak read or write bandwidth.
    announce("cpu_ceiling");
    std::vector<char> src(COPY_BYTES, 1), dst(COPY_BYTES);
    std::vector<double> v;
    for (int s = 0; s < g_samples; ++s) {
        const int64_t a = now_ns();
        std::memcpy(dst.data(), src.data(), COPY_BYTES);
        v.push_back(double(COPY_BYTES) / (double(now_ns() - a) * 1e-9));
    }
    char method[512];
    std::snprintf(method, sizeof method,
                  "tax_bench.cpp memcpy of %zuMiB, bytes copied not bus traffic — halve "
                  "it for read+write; buffers sized past any last-level cache on this "
                  "target, median of %d, p1 %.3g B/s (the sustained end)",
                  COPY_BYTES >> 20, g_samples, percentile(v, 0.01));
    emit("cpu_ceiling", percentile(v, 0.5), "B/s", method);
}

}  // namespace

int main(int argc, char** argv) {
    int warm = DEFAULT_WARMUP_SECONDS;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--warmup-seconds" && i + 1 < argc) warm = std::atoi(argv[++i]);
        else if (a == "--samples" && i + 1 < argc) g_samples = std::atoi(argv[++i]);
        else if (a == "--date" && i + 1 < argc) g_date = argv[++i];
        else { std::fprintf(stderr, "usage: %s [--warmup-seconds N] [--samples N] [--date D]\n", argv[0]); return 2; }
    }
    if (g_date.empty()) {
        char buf[16];
        const std::time_t t = std::time(nullptr);
        std::strftime(buf, sizeof buf, "%Y-%m-%d", std::localtime(&t));
        g_date = buf;
    }
    // Line-buffered: redirected to a file, a block-buffered run that hangs loses
    // every row it already finished, which is exactly when you need them.
    setvbuf(stdout, nullptr, _IOLBF, 0);
    warmup(warm);
    std::printf("tax:\n");
    bench_syscall();
    bench_clock();
    bench_sleep_granularity();
    bench_malloc(64, "malloc");
    bench_malloc(4096, "malloc_4k");
    bench_malloc(1u << 20, "malloc_1m");
    bench_page_fault();
    bench_mutex();
    bench_futex_wake();
    bench_file_io();
    bench_socketpair_rtts();
    bench_udp_loopback_rtt();
    bench_tcp_loopback_rtt();
    bench_sendmsg_vs_sendmmsg();
    bench_pipe_rtt();
    bench_shm_rtt();
    bench_cpu_ceiling();
    std::fprintf(stderr, "\nNo NIC row: a real-NIC crossing needs a peer host and is not "
                         "self-measurable. Leave it `measured: false` until it is benched.\n");
    return 0;
}
