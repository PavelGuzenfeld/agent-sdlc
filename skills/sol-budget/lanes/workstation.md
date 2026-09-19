# Lane: workstation

A desktop, a server, or a CI box. Discrete GPU over PCIe if there is one, DRAM behind
a memory controller the CPU owns, and cooling that mostly keeps its promises.

**No measured rows here.** Nothing in this file came off a benched workstation, and
none of it may be copied into a `machine_model.md`. Run the §4–§8 benches on the
actual box; this is a list of what to expect to dominate, not what it will cost.

## Where the weight falls

**The link is real.** Unlike the SoC lane, a host-to-device copy crosses PCIe and the
bytes genuinely move. `fabric_bw`'s §2 readout prints `integrated: false` here, and
that single flag changes the graph: the transfer is an edge with its own cost, not a
copy node you can delete. Expect the h2d row to be an order of magnitude below the
GPU's own memory bandwidth, and expect pinned-versus-pageable to matter more than on
an SoC, not less.

**Cores are plentiful and the fabric is not.** The §5 sweep matters here for the same
reason as on an SoC, but the knee usually sits at a higher thread count, and NUMA can
put two knees on one machine. If `lscpu` reports more than one NUMA node, the sweep
must be run per node and the model needs a memory type per node — `sol.py` reads the
`memory:` section to decide which nodes share the fabric, and declaring one pool when
there are two is how a budget silently doubles.

**Boost is not steady state.** A workstation will run well above its sustained clock
for tens of seconds and then settle. This is the lane where `thermal_watch.py` most
often comes back with `clocks: ramping`, and where a 30-second warmup is not enough.
Take the equilibrium figure the watch reports, do not assume it.

## Lane-specific tax list

Look at these first; measure all of them:

- **h2d / d2h over PCIe**, pinned and pageable. The gap is the cheapest win on the lane.
- **NUMA locality** — a cross-socket access against a local one. If the spread is
  large, placement is a design decision, not a tuning knob.
- **Kernel launch and completion**, blocking against polling. A discrete GPU's
  completion path goes through an interrupt; the spread against a busy-wait is wider
  than on an integrated part.
- **Timer jitter under a loaded scheduler.** Desktop kernels are not tickless by
  default everywhere, and a 1 ms window is not safe until measured.
- **Page faults and huge pages.** Large working sets on this lane are where
  transparent huge pages either save you or stall you; the §8 `page_fault` row is the
  one to compare against.

## What this lane does not tell you

Nothing about a laptop on battery, which is the phone lane's problem wearing a bigger
case, and nothing about a container with a CPU quota — a cgroup limit makes the
scheduler, not the silicon, the ceiling, and no bench here detects that for you.
