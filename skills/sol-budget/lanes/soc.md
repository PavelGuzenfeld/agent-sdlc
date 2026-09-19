# Lane: SoC

An integrated part — CPU, GPU and fixed-function blocks sharing one memory
controller. Jetson, Apple silicon, most automotive and robotics targets.

Measured on a JP6 Orin (L4T R36.4.3, 8× Cortex-A78AE at
1.4976 GHz, 15.3 GiB LPDDR5, 8 SMs) on 2026-09-17. Every number below came off that
machine; another SoC will differ, and the point of the list is which rows to look at
first, not what they will say.

## Where the weight falls

**The fabric, before anything else.** One memory controller serves every unit, so
"which unit does the work" is a question about who gets bandwidth, not about who is
fastest. On the Orin the CPU alone sustains 26.8 GB/s of copy across 8 cores and the
GPU sustains 47.5 GB/s on its own — but the §5 knee, where a victim's p99 turns up,
sits at **14.2 GB/s**. A graph that budgets against either uncontended figure has
already overspent by 2–3×.

**Copies that are not copies.** `cudaGetDeviceProperties` reports `integrated: true`
here, and host-to-device measured 32.7 GB/s — far above any link, because the bytes
never leave DRAM. On this lane a host-to-device copy is a memcpy the graph is paying
for twice, and the first optimisation to look for is deleting it, not speeding it up.
Check `integrated` before modelling any transfer as a crossing.

**Forgetting to pin costs 4×.** Pinned host memory copied at 32.7 GB/s, pageable at
8.18 GB/s, because the driver stages pageable memory through its own pinned buffer.
That is a four-line change in most codebases and it is worth more than most kernel
tuning.

**Language, not just placement.** The same machine sustains 5.96e9 op/s on one native
core and 2.12e7 through CPython — **282×**. Bandwidth is the opposite: a bytearray
copy and a C `memcpy` both land at 9.42 GB/s, because they are the same instruction
underneath. A Python stage that moves bytes is near the metal; a Python stage that
computes is nowhere near it. Price them against different units.

## Lane-specific tax list

Check these before believing any budget on this lane:

| tax | Orin measurement | why it bites here |
|---|---|---|
| `h2d` vs in-place | 32.7 GB/s pinned, 8.18 GB/s pageable | shared DRAM makes the copy avoidable entirely |
| GPU kernel dispatch | 3.42 µs | a per-frame kernel at 30 fps spends 0.01% here; a per-tile kernel at 10 kHz spends 3.4% |
| GPU completion, blocking | 11.9 µs | `cudaDeviceSynchronize` is a driver wait; budget it, or pipeline around it |
| thread handoff, blocking | 3.42 µs dispatch, 3.78 µs completion | condition variable |
| thread handoff, spinning | 160 ns | 23× faster and costs a whole core for the wait |
| core-to-core, near | 224 ns | cpu0↔cpu1 |
| core-to-core, far | 483 ns | cpu0↔cpu7, **2.15×** — cluster boundaries are real on this part |
| timer wake jitter (p99) | 65.8 µs | at a 33 ms window that is 0.2%; at a 1 ms window it is 6.6% |
| context switch | 0.98 µs | two threads, one core |
| syscall | 260 ns | vs 50 ns for `clock_gettime` through the vDSO |
| page fault, first touch | 574 ns | pre-fault or pool; do not discover this in the hot path |
| UDP over loopback | 16.9 µs round trip | vs 11.3 µs for an AF_UNIX datagram and 224 ns for a shared cache line |

## What this lane does not tell you

Clocks held at 1497600 kHz flat under 8-core load, governor `schedutil`, with the
hottest zone settling 60.0 → 66.5 °C and a fixed workload settling by t≈30 s. That
makes `modelled-steady-state` honest **here**. A differently cooled or differently
powered board of the same chip will throttle, and then every row above is an average
over a ramp rather than a steady state. Run `thermal_watch.py` on the actual board
before reusing any of this.

`jetson_clocks` and `nvpmodel` need root, so no locked-clock run exists for this
target. Nothing here is a locked-clock measurement and the model's `clocks:` header
says so.
