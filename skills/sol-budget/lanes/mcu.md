# Lane: MCU

A microcontroller. Single core or a small cluster, SRAM measured in kilobytes, often
no MMU, often no operating system worth the name.

**No measured rows here**, and more than on any other lane the benches in this skill
do not simply run: most of them assume threads, a filesystem, sockets and a POSIX
clock. Treat this file as a statement about which parts of the model still apply, and
expect to write a target-specific harness rather than to reuse `tax_bench.cpp`.

## Where the weight falls

**Memory is the design, not a budget line.** With unit-private SRAM and no cache
hierarchy to speak of, whether a buffer fits decides the algorithm. The §2 section
matters more here than anywhere and the §5 knee often matters not at all, because
there is no shared fabric to saturate — one core, one bus, and contention is a
question about DMA, not about threads.

**Determinism replaces throughput.** The interesting quantity is usually the worst
case, not the sustained rate. That inverts this skill's default: a tax row is
normally a median because it is a floor, but on an MCU the number a design lives or
dies by is the p99 or the true maximum. If you adopt this lane, say so explicitly in
the model's `method:` strings — a maximum in a column the rest of the skill reads as
a median is exactly the kind of quiet mismatch the hard rules exist to stop.

**There is no operating system to blame.** No scheduler jitter, no page faults, no
syscalls — and equally no preemption to save you from a long interrupt handler. §6
largely collapses to interrupt latency and handler duration, which is one row and one
of the most important in the model.

## Lane-specific tax list

- **Interrupt latency and handler duration.** The §6 row that replaces every other §6
  row. Measure the worst case, not the median.
- **DMA setup cost against payload size.** Below some size the descriptor costs more
  than the copy, and that crossover is the whole design.
- **Flash wait states and instruction fetch.** Code running from flash rather than
  SRAM can be several times slower, and the difference does not show up in any
  bandwidth row.
- **Peripheral bus crossings** — SPI, I²C, CAN. These are the §8 taxes on this lane,
  and their ceilings are usually a protocol constant, not a measurement.
- **Clock domain crossings**, if the part has more than one.

## What this lane does not tell you

Nothing about power, which on a battery-backed MCU is frequently the real budget and
which this skill does not model at all. If the deadline is an energy budget rather
than a time budget, the shape here still works — a floor, a fraction of it, a gate —
but every unit in the model has to change from seconds to joules, and none of the
supplied benches measure that.
