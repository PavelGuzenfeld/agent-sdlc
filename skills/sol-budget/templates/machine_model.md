# Machine model — <chip> / <os> / <power mode> / <clocks>

One file per target config. The prose sections are for the reader; the `yaml` block is
what `sol.py` reads. Every row carries `method:` and `date:` so somebody else can rerun
it. A row that has not been benched carries `measured: false` and a `method:` naming
where the number came from — `sol.py` will read it and refuse to spend it as a floor.

Regenerate when the config header stops matching the machine in front of you. A model
from a different power mode is not this machine's model.

## §1 Units

Every execution unit reachable from this toolchain, and what it may not do.

| unit | reachable via | restrictions |
|---|---|---|
| cpu | — | |
| gpu | CUDA | |
| dla | TensorRT | no plugin layers, fp16/int8 only |
| vic | NvBufSurfTransform | |

## §2 Memory

Cache levels and who shares them, unit-private SRAM, the fabric path and its
theoretical bandwidth. The theoretical number lives here for orientation only. §5's
knee is what Phase 2 spends.

## §3 Handoff matrix

See `handoff_matrix.md`. Every `copy` or `convert` cell becomes a node in the dataflow.

## §4 Isolated

Sustained over at least 10× the window, never peak. Dispatch and completion latency
with the completion mechanism named — a poll and an interrupt are different rows.

## §5 Contention

Every pair the pipeline overlaps, plus the realistic combination. Mean and p99
degradation. The **saturation knee** — total offered load where latency turns up — is
the row Phase 2 consumes.

## §6 Scheduling

Timer wake jitter, context switch, core-to-core, the effect of pinning, OS placement
and boost policy.

## §7 Power and thermal

Clocks against time to equilibrium. Minutes, not seconds. State whether clocks were
locked or the steady state was modelled.

## §8 Tax

Fixed cost per crossing and throughput ceiling for every mechanism the hot path
touches. Nothing here is free.

```yaml
config:
  chip: <chip>
  os: <os and version>
  power_mode: <mode>
  clocks: locked | modelled-steady-state
  date: <YYYY-MM-DD>

memory:
  # Whether this memory type crosses the shared fabric. Declared, never inferred:
  # it decides every memory floor and whether §5's knee applies to the node.
  nvmm: {shared: true}
  dram: {shared: true}
  sram: {shared: false}

units:
  cpu:
    sustained_ops: {value: 0, unit: op/s, method: "unmeasured", date: "", measured: false}
    sustained_bytes: {value: 0, unit: B/s, method: "unmeasured", date: "", measured: false}
    dispatch_latency: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
    completion_latency: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}

fabric:
  # §5, and the only bandwidth a floor may use.
  knee: {value: 0, unit: B/s, method: "unmeasured", date: "", measured: false}
  # §2, orientation only. sol.py cannot reach this row.
  theoretical: {value: 0, unit: B/s, method: "datasheet", date: "", measured: false}

sched:
  timer_jitter: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
  ctx_switch: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}

tax:
  syscall: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
  clock_gettime_vdso: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
  malloc: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
  page_fault: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
  mutex_uncontended: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
  futex_wake: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
  udp_loopback_rtt: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
  gil_acquire: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
  ffi_crossing: {value: 0, unit: s, method: "unmeasured", date: "", measured: false}
  # Throughput ceiling of a mechanism, keyed `<unit>_ceiling`, spent against
  # a node's crossing_bytes.
  cpu_ceiling: {value: 0, unit: B/s, method: "unmeasured", date: "", measured: false}
```
