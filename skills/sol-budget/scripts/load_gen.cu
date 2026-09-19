// The GPU lane of the §5 load generator. Same contract as load_gen.cpp: put a known
// amount of traffic on the shared fabric and report what was actually delivered.
//
// Build:  nvcc -O3 -std=c++17 -o load_gen_cuda load_gen.cu
// Run:    ./load_gen_cuda --seconds S [--bytes MiB] [--quiet]
//
// Two generators exist because which unit offers the load changes the answer. On a
// target where the GPU and the CPU share one memory controller — `integrated: true`
// in fabric_bw's §2 readout — GPU traffic and CPU traffic contend for the same
// bandwidth, and a knee measured with only one of them is a knee for a pipeline that
// does not exist. contention_sweep records which generator produced each row.

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <string>
#include <vector>

#include <cuda_runtime.h>

namespace {

constexpr size_t DEFAULT_MIB = 256;

#define CUDA_OR_DIE(call)                                                     \
    do {                                                                      \
        const cudaError_t err = (call);                                       \
        if (err != cudaSuccess) {                                             \
            std::fprintf(stderr, "%s:%d %s: %s\n", __FILE__, __LINE__, #call, \
                         cudaGetErrorString(err));                            \
            std::exit(1);                                                     \
        }                                                                     \
    } while (0)

double now_s() {
    timespec t{};
    clock_gettime(CLOCK_MONOTONIC, &t);
    return double(t.tv_sec) + double(t.tv_nsec) * 1e-9;
}

__global__ void stream_kernel(const float4* __restrict__ src, float4* __restrict__ dst,
                              size_t n) {
    for (size_t i = blockIdx.x * size_t(blockDim.x) + threadIdx.x; i < n;
         i += size_t(gridDim.x) * blockDim.x)
        dst[i] = src[i];
}

}  // namespace

int main(int argc, char** argv) {
    double seconds = 1.0;
    size_t mib = DEFAULT_MIB;
    bool quiet = false;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--seconds" && i + 1 < argc) seconds = std::atof(argv[++i]);
        else if (a == "--bytes" && i + 1 < argc) mib = size_t(std::atol(argv[++i]));
        else if (a == "--quiet") quiet = true;
        else {
            std::fprintf(stderr, "usage: %s --seconds S [--bytes MiB] [--quiet]\n",
                         argv[0]);
            return 2;
        }
    }
    if (seconds <= 0) {
        std::fprintf(stderr, "--seconds must be > 0\n");
        return 2;
    }

    int device = 0;
    cudaDeviceProp prop{};
    CUDA_OR_DIE(cudaGetDevice(&device));
    CUDA_OR_DIE(cudaGetDeviceProperties(&prop, device));
    const size_t bytes = mib << 20;
    const size_t n = bytes / sizeof(float4);
    float4 *src = nullptr, *dst = nullptr;
    CUDA_OR_DIE(cudaMalloc(&src, bytes));
    CUDA_OR_DIE(cudaMalloc(&dst, bytes));
    CUDA_OR_DIE(cudaMemset(src, 1, bytes));

    const int blocks = prop.multiProcessorCount * 32;
    const int threads = 256;
    CUDA_OR_DIE(cudaDeviceSynchronize());
    const double started = now_s();
    const double until = started + seconds;
    long passes = 0;
    while (now_s() < until) {
        stream_kernel<<<blocks, threads>>>(src, dst, n);
        ++passes;
        CUDA_OR_DIE(cudaDeviceSynchronize());
    }
    const double delivered = double(passes) * double(bytes) / (now_s() - started);

    CUDA_OR_DIE(cudaFree(src));
    CUDA_OR_DIE(cudaFree(dst));
    if (!quiet)
        std::printf("{\"generator\": \"load_gen.cu\", \"unit\": \"gpu\", "
                    "\"device\": \"%s\", \"integrated\": %s, \"seconds\": %.3f, "
                    "\"buffer_mib\": %zu, \"delivered_bytes_per_s\": %.6g}\n",
                    prop.name, prop.integrated ? "true" : "false", seconds, mib,
                    delivered);
    return 0;
}
