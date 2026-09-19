// §2 fabric path and the GPU half of §4, for perf/machine_model.md.
//
// Build:  nvcc -O3 -std=c++17 -o fabric_bw fabric_bw.cu
// Run:    ./fabric_bw [--window-seconds S] [--warmup-seconds N] [--samples N] [--date D]
// Output: a `units:` block for the `gpu` unit and a `fabric:` block for the paths.
//
// What the fabric is depends on the target and must not be assumed. On a discrete
// card it is PCIe and a host-to-device copy crosses it. On this Orin the GPU and the
// CPU share one LPDDR5 controller, so "host to device" moves bytes that never leave
// DRAM, and a pipeline that copies between them is paying for a copy it could have
// avoided. The rows below therefore report the path *as measured*, and §2's prose is
// where the reader learns which of those two worlds they are in.
//
// None of these rows is the bandwidth Phase 2 spends. `sol.py` reaches exactly one
// bandwidth — `fabric.knee`, the saturation knee from §5 — and these are the
// uncontended ceilings that sit above it, for orientation and for sanity-checking
// the knee. They are named `_uncontended` so nobody mistakes one for the other.

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>

#include <cuda_runtime.h>

namespace {

constexpr int DEFAULT_SAMPLES = 9;
constexpr int DEFAULT_WARMUP_SECONDS = 30;
constexpr double DEFAULT_WINDOW_SECONDS = 1.0 / 30.0;
constexpr double WINDOWS_PER_SAMPLE = 10.0;
constexpr double MIN_SUSTAINED_SECONDS = 2.0;
constexpr size_t COPY_BYTES = 256u << 20;
constexpr int LANES = 8;
constexpr int LATENCY_REPS = 2000;

int g_samples = DEFAULT_SAMPLES;
double g_sustained_seconds = MIN_SUSTAINED_SECONDS;
std::string g_date;
// Read+write traffic of the streaming kernel, kept so §2 can check a derived
// datasheet figure against something the machine actually did.
double g_streaming_traffic = 0.0;

#define CUDA_OR_DIE(call)                                                        \
    do {                                                                         \
        const cudaError_t err = (call);                                          \
        if (err != cudaSuccess) {                                                \
            std::fprintf(stderr, "%s:%d %s: %s\n", __FILE__, __LINE__, #call,    \
                         cudaGetErrorString(err));                               \
            std::exit(1);                                                        \
        }                                                                        \
    } while (0)

double now_s() {
    timespec t{};
    clock_gettime(CLOCK_MONOTONIC, &t);
    return double(t.tv_sec) + double(t.tv_nsec) * 1e-9;
}

double percentile(std::vector<double> v, double q) {
    std::sort(v.begin(), v.end());
    return v[size_t(q * double(v.size() - 1) + 0.5)];
}

void announce(const char* key) { std::fprintf(stderr, "  %s ...\n", key); }

void emit(const char* key, double value, const char* unit, const std::string& method) {
    const bool ok = value > 0.0 && std::isfinite(value);
    std::printf("    %s: {value: %.6g, unit: %s, method: \"%s\", date: \"%s\", "
                "measured: %s}\n",
                key, value, unit, method.c_str(), g_date.c_str(), ok ? "true" : "false");
}

// --- kernels -------------------------------------------------------------------

__global__ void fma_kernel(double* out, long inner) {
    double acc[LANES];
    for (int i = 0; i < LANES; ++i) acc[i] = double(i) + 1.0;
    const double m = 1.0000001, c = 0.0000001;
    for (long it = 0; it < inner; ++it)
        for (int i = 0; i < LANES; ++i) acc[i] = acc[i] * m + c;
    double sink = 0.0;
    for (int i = 0; i < LANES; ++i) sink += acc[i];
    if (sink == 12345.6789) out[blockIdx.x * blockDim.x + threadIdx.x] = sink;
}

__global__ void copy_kernel(const float4* __restrict__ src, float4* __restrict__ dst,
                            size_t n) {
    for (size_t i = blockIdx.x * size_t(blockDim.x) + threadIdx.x; i < n;
         i += size_t(gridDim.x) * blockDim.x)
        dst[i] = src[i];
}

__global__ void noop_kernel() {}

// --- rows ----------------------------------------------------------------------

// Bytes per second across one copy path, timed on the wall clock rather than with
// cuda events: a pipeline pays wall time, and an event pair hides the launch.
double copy_path(void* dst, const void* src, cudaMemcpyKind kind) {
    std::vector<double> rate;
    for (int s = 0; s < g_samples; ++s) {
        CUDA_OR_DIE(cudaDeviceSynchronize());
        const double a = now_s();
        CUDA_OR_DIE(cudaMemcpy(dst, src, COPY_BYTES, kind));
        CUDA_OR_DIE(cudaDeviceSynchronize());
        rate.push_back(double(COPY_BYTES) / (now_s() - a));
    }
    return percentile(rate, 0.5);
}

void bench_copy_paths() {
    void *device_a = nullptr, *device_b = nullptr, *pinned = nullptr;
    CUDA_OR_DIE(cudaMalloc(&device_a, COPY_BYTES));
    CUDA_OR_DIE(cudaMalloc(&device_b, COPY_BYTES));
    CUDA_OR_DIE(cudaMallocHost(&pinned, COPY_BYTES));
    std::vector<char> pageable(COPY_BYTES, 1);
    std::memset(pinned, 1, COPY_BYTES);

    char method[640];
    announce("h2d_uncontended");
    const double h2d = copy_path(device_a, pinned, cudaMemcpyHostToDevice);
    std::snprintf(method, sizeof method,
                  "fabric_bw.cu cudaMemcpy of %zuMiB from pinned host memory, wall "
                  "clock around a synchronised copy; median of %d. Uncontended — "
                  "Phase 2 spends fabric.knee, never this",
                  COPY_BYTES >> 20, g_samples);
    emit("h2d_uncontended", h2d, "B/s", method);

    announce("h2d_pageable_uncontended");
    const double pg = copy_path(device_a, pageable.data(), cudaMemcpyHostToDevice);
    std::snprintf(method, sizeof method,
                  "fabric_bw.cu the same copy from pageable memory — the driver stages "
                  "it through its own pinned buffer, so this is what a stage pays when "
                  "it forgets to pin; median of %d",
                  g_samples);
    emit("h2d_pageable_uncontended", pg, "B/s", method);

    announce("d2h_uncontended");
    const double d2h = copy_path(pinned, device_a, cudaMemcpyDeviceToHost);
    std::snprintf(method, sizeof method,
                  "fabric_bw.cu cudaMemcpy of %zuMiB device to pinned host; median of %d",
                  COPY_BYTES >> 20, g_samples);
    emit("d2h_uncontended", d2h, "B/s", method);

    announce("d2d_uncontended");
    const double d2d = copy_path(device_b, device_a, cudaMemcpyDeviceToDevice);
    std::snprintf(method, sizeof method,
                  "fabric_bw.cu cudaMemcpy of %zuMiB device to device, bytes copied not "
                  "bus traffic — halve for read+write; median of %d",
                  COPY_BYTES >> 20, g_samples);
    emit("d2d_uncontended", d2d, "B/s", method);

    CUDA_OR_DIE(cudaFree(device_a));
    CUDA_OR_DIE(cudaFree(device_b));
    CUDA_OR_DIE(cudaFreeHost(pinned));
}

void bench_gpu_unit() {
    int device = 0;
    cudaDeviceProp prop{};
    CUDA_OR_DIE(cudaGetDevice(&device));
    CUDA_OR_DIE(cudaGetDeviceProperties(&prop, device));
    const int blocks = prop.multiProcessorCount * 32;
    const int threads = 256;

    announce("sustained_ops");
    double* scratch = nullptr;
    CUDA_OR_DIE(cudaMalloc(&scratch, size_t(blocks) * threads * sizeof(double)));
    std::vector<double> ops;
    for (int s = 0; s < g_samples; ++s) {
        // Size the launch to the sustained window rather than a fixed count, so a
        // fast part cannot be reported as a rate the whole window could hold.
        const long inner = 20000;
        CUDA_OR_DIE(cudaDeviceSynchronize());
        const double a = now_s();
        long launches = 0;
        while (now_s() - a < g_sustained_seconds) {
            fma_kernel<<<blocks, threads>>>(scratch, inner);
            ++launches;
            CUDA_OR_DIE(cudaDeviceSynchronize());
        }
        const double elapsed = now_s() - a;
        const double total = double(launches) * blocks * threads * double(inner) * LANES * 2.0;
        ops.push_back(total / elapsed);
    }
    char method[640];
    std::snprintf(method, sizeof method,
                  "fabric_bw.cu independent double multiply-accumulate, %d lanes per "
                  "thread, %d blocks x %d threads on %d SMs; one mul plus one add "
                  "counted as two ops; each sample sustained %.1fs; median of %d, "
                  "worst %.3g op/s",
                  LANES, blocks, threads, prop.multiProcessorCount,
                  g_sustained_seconds, g_samples, percentile(ops, 0.0));
    emit("sustained_ops", percentile(ops, 0.5), "op/s", method);

    announce("sustained_bytes");
    float4 *src = nullptr, *dst = nullptr;
    const size_t n = COPY_BYTES / sizeof(float4);
    CUDA_OR_DIE(cudaMalloc(&src, COPY_BYTES));
    CUDA_OR_DIE(cudaMalloc(&dst, COPY_BYTES));
    CUDA_OR_DIE(cudaMemset(src, 1, COPY_BYTES));
    std::vector<double> bytes;
    for (int s = 0; s < g_samples; ++s) {
        CUDA_OR_DIE(cudaDeviceSynchronize());
        const double a = now_s();
        long passes = 0;
        while (now_s() - a < g_sustained_seconds) {
            copy_kernel<<<blocks, threads>>>(src, dst, n);
            ++passes;
            CUDA_OR_DIE(cudaDeviceSynchronize());
        }
        bytes.push_back(double(passes) * double(COPY_BYTES) / (now_s() - a));
    }
    std::snprintf(method, sizeof method,
                  "fabric_bw.cu float4 streaming copy kernel over %zuMiB, bytes copied "
                  "not bus traffic — halve for read+write; each sample sustained %.1fs; "
                  "median of %d, worst %.3g B/s",
                  COPY_BYTES >> 20, g_sustained_seconds, g_samples, percentile(bytes, 0.0));
    g_streaming_traffic = percentile(bytes, 0.5) * 2.0;
    emit("sustained_bytes", percentile(bytes, 0.5), "B/s", method);

    announce("dispatch_latency / completion_latency");
    std::vector<double> dispatch, completion;
    for (int i = 0; i < LATENCY_REPS; ++i) {
        CUDA_OR_DIE(cudaDeviceSynchronize());
        const double a = now_s();
        noop_kernel<<<1, 1>>>();
        const double launched = now_s();
        CUDA_OR_DIE(cudaDeviceSynchronize());
        const double done = now_s();
        dispatch.push_back(launched - a);
        completion.push_back(done - launched);
    }
    std::snprintf(method, sizeof method,
                  "fabric_bw.cu time for an empty <<<1,1>>> launch to return to the "
                  "host — the queueing cost a stage pays per kernel, not the kernel; "
                  "median of %d", LATENCY_REPS);
    emit("dispatch_latency", percentile(dispatch, 0.5), "s", method);
    std::snprintf(method, sizeof method,
                  "fabric_bw.cu cudaDeviceSynchronize after that launch — the blocking "
                  "mechanism, which is a driver wait and not a spin; median of %d",
                  LATENCY_REPS);
    emit("completion_latency", percentile(completion, 0.5), "s", method);

    CUDA_OR_DIE(cudaFree(src));
    CUDA_OR_DIE(cudaFree(dst));
    CUDA_OR_DIE(cudaFree(scratch));
}

void describe_memory() {
    int device = 0;
    cudaDeviceProp prop{};
    CUDA_OR_DIE(cudaGetDevice(&device));
    CUDA_OR_DIE(cudaGetDeviceProperties(&prop, device));
    // Whether the GPU shares DRAM with the CPU decides whether a host-to-device copy
    // is a fabric crossing at all, and the `memory:` section of the model declares it.
    std::fprintf(stderr,
                 "\n§2 for the model's `memory:` section, read from the device:\n"
                 "  device            %s, %d SMs, compute %d.%d\n"
                 "  integrated        %s  <- true means GPU and CPU share DRAM, so a\n"
                 "                        host-to-device copy never leaves memory and\n"
                 "                        belongs in the graph as a copy node, not a link\n"
                 "  unified addressing %s\n"
                 "  can map host mem   %s\n"
                 "  L2 cache          %d KiB\n"
                 "  global memory     %.1f GiB\n"
                 "  memory bus        %d-bit at %d kHz\n"
                 "\n"
                 "  No bandwidth is derived from that bus width and clock, deliberately.\n"
                 "  Doing it the textbook way (width/8 x clock x 2 for DDR) gives %.3g B/s\n"
                 "  here, and the streaming kernel above already moved %.3g B/s of traffic\n"
                 "  — measuring above your own ceiling means the arithmetic is wrong, not\n"
                 "  that the machine is magic. LPDDR5 does not clock the way that formula\n"
                 "  assumes. Look the figure up for this exact part and put it in\n"
                 "  fabric.theoretical with method: datasheet and measured: false, which\n"
                 "  is the one row sol.py can never reach anyway.\n",
                 prop.name, prop.multiProcessorCount, prop.major, prop.minor,
                 prop.integrated ? "true" : "false",
                 prop.unifiedAddressing ? "true" : "false",
                 prop.canMapHostMemory ? "true" : "false",
                 prop.l2CacheSize / 1024, double(prop.totalGlobalMem) / (1 << 30),
                 prop.memoryBusWidth, prop.memoryClockRate,
                 double(prop.memoryBusWidth) / 8.0 * double(prop.memoryClockRate) * 2000.0,
                 g_streaming_traffic);
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

    if (warm > 0) {
        std::fprintf(stderr, "warming up %ds (§7: a number from a cold machine is about "
                             "a cold machine)\n", warm);
        double* scratch = nullptr;
        CUDA_OR_DIE(cudaMalloc(&scratch, 1024 * sizeof(double)));
        const double until = now_s() + warm;
        while (now_s() < until) {
            fma_kernel<<<64, 256>>>(scratch, 20000);
            CUDA_OR_DIE(cudaDeviceSynchronize());
        }
        CUDA_OR_DIE(cudaFree(scratch));
    }

    std::printf("units:\n  gpu:\n");
    bench_gpu_unit();
    std::printf("fabric:\n");
    bench_copy_paths();
    describe_memory();
    return 0;
}
