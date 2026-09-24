---
name: sol-budget
description: "Speed-of-light performance budgeting for a hot path. Use to optimize, profile, or benchmark a stage; when asked if it's fast enough; on a slow frame-rate, latency, or throughput report; or when a diff touches perf/budget.md."
---

# Speed-of-light budgeting

An optimisation with no floor under it is a guess. This skill puts the floor in the
repo first — derived from what the machine was *measured* to do, not what the vendor
says it does — and then refuses the work that the floor says is not there.

Companion to `verify-generated-diff`: that one gates correctness, this one gates
performance.

## Hard rules

- Never use theoretical, isolated, or vendor bandwidth in a floor.
- Never budget against the mean when the window is a deadline.
- Never treat copy, convert, syscall, alloc, lock, or runtime dispatch as free.
- Never profile before the floor exists.
- Never keep an SOL across a graph change.
- Never report a stage faster than SOL as a result.
- Never write a datasheet number in a `measured` column.

## Artefacts

All in `perf/`, in the repo:

| file | written by | holds |
|---|---|---|
| `machine_model.md` | Phase 1, by hand from bench output | §1–§8, one `yaml` block of rows |
| `handoff_matrix.md` | Phase 1 | §3, unit × unit |
| `dataflow.yaml` | Phase 2, by hand | the graph |
| `sol_table.md` | `scripts/sol.py` | floors, regime, critical path |
| `budget.md` | `scripts/sol.py` | allowed p99 per node |
| `measurements.csv` | Phase 2 step 6 | node, mean, p99, SOL, ratio, build, date, graph |
| `budget_revisions.md` | by hand | the only way past a failing gate |

A repo built on two machines carries one machine's `machine_model.md`. The `config:`
header is load-bearing: a model whose header does not match the target in front of you
is a Phase 1 trigger, never a floor source.

`sol.py` needs PyYAML. Nothing else.

## Phase 1 — machine model

Once per target config. Copy `templates/machine_model.md` to `perf/`, fill the `config:`
header, and work through §1–§8 with the bench scripts. Every row gets a `method:` line
and a date. A row you have not benched keeps `measured: false`; `sol.py` reads it and
refuses to spend it, which is the correct outcome — a placeholder in a floor is worse
than a missing floor because it looks like an answer.

Clocks locked, or the steady state modelled and said so. §7's equilibrium is minutes
away; a number taken in the first thirty seconds is a number about a cold machine.

Exit condition: every unit and mechanism the hot path touches has a measured row, the
§5 knee is measured, and somebody else could rerun each row from its `method:`.

## Phase 2 — SOL and budget

1. **Graph.** Write `perf/dataflow.yaml`. Nodes are stages with the unit that runs
   them. Every non-`inplace` cell of the handoff matrix becomes its own copy or convert
   node, and the edge names it with `via:`. Every kernel or runtime crossing — syscall,
   socket op, hot alloc, lock, wake, FFI — is a `crossings:` entry priced from §8.
   Nothing hides inside a library call.
2. **Fundamental work.** Per node, the compulsory ops and compulsory bytes the
   algorithm requires. A miss, a re-read or a conversion is a design decision, so it is
   a node — not part of another node's compulsory work.
3. **Floors.** `sol.py` derives them: compute = ops ÷ §4 sustained rate; memory = bytes
   ÷ the bandwidth available under this graph's overlap; tax = per-crossing §8 cost plus
   bytes ÷ mechanism ceiling. SOL is the largest of the three plus dispatch plus
   completion, and the table records which one won.
4. **Critical path.** Longest path through the DAG plus edge sync costs. `sol.py` sums
   overlapping fabric demand against §5's knee and, if it is over, degrades every
   shared-memory node's bandwidth and re-derives until the graph is self-consistent.
   If the resulting critical path exceeds the window minus margin, it stops: the graph
   is wrong, and no implementation reaches that deadline. Do not start coding.
5. **Budgets.** `budget.md`, per node, as a fraction of SOL — 0.70 memory-bound, 0.50
   tax-dominated, 0.85 tight compute. Margin 25% on a shared fabric, 10% on bare
   metal.
6. **Measure** with the real overlap, production cache state, and enough iterations for
   a p99. Append to `measurements.csv` with the build and the graph digest.

```
python3 scripts/sol.py --perf perf
```

## Phase 3 — decide and gate

Let `ratio = SOL ÷ measured`.

- **ratio ≥ 0.7 — refuse to optimise the implementation.** Say so plainly: this stage
  is within 30% of what the machine was measured to do, so tuning the code cannot buy
  what is being asked for. Only a graph change helps — fewer bytes, fewer ops, an
  in-place handoff, a different unit. Propose one, or stop. Do not profile.
- **ratio ≤ 0.3 — proceed, overhead first.** Test whether the node is overhead-bound
  (dispatch, sync, small work, crossings) before touching the kernel. If tax dominates,
  the only allowed fix is fewer crossings: batch, coalesce, `sendmmsg`, an arena, shared
  memory. Only then static cycle analysis (llvm-mca, OSACA) for CPU nodes or roofline
  placement for GPU nodes. llvm-mca output is analysis, never a floor — it is a model,
  and a model in a measured column is the thing the hard rules forbid.
- **0.3 < ratio < 0.7** — report both options with the remaining margin, and ask.
- **ratio > 1.0 — `MODEL_DEFECT`.** A stage cannot beat its own floor. `sol.py` names
  the machine-model row that produced the winning floor; re-measure it. Do not report
  a win.

**Any structural change re-derives the SOL before anything is compared.** The graph
digest in `budget.md` and `measurements.csv` enforces it: a row measured against a
different graph is refused, not compared.

```
python3 scripts/budget_check.py --perf perf   # PERF_GATE: pass|fail
```

Gate: a node p99 over budget, or the sum of node p99s (the serial upper bound) over the window minus margin, fails
— unless `budget_revisions.md` carries a dated entry naming that node and saying why
the derived budget was wrong. "It is slow" is not a reason; that is the finding, not
the revision.

§8 has a bench. Both halves print a paste-ready `tax:` fragment with `method:` and
`date:` already filled, and the C++ one warms up first because §7 says a cold number
is about a cold machine:

```
g++ -O2 -std=c++17 -pthread -o tax_bench scripts/tax_bench.cpp && ./tax_bench
python3 scripts/tax_bench.py     # ffi_crossing and gil_acquire only
```

A real-NIC crossing needs a peer host, so no row here can measure it. It stays
`measured: false` until somebody benches it against the peer the hot path uses.

§4 has one too. It prints a `units:` block for `cpu` (every core) and `cpu_1core`
(one pinned core), plus `cpu_python` for a stage the interpreter runs:

```
g++ -O3 -DBENCH_OPTIMIZATION_LEVEL=3 -std=c++17 -pthread -o unit_bench scripts/unit_bench.cpp && ./unit_bench
python3 scripts/unit_bench.py    # the cpu_python unit
```

**-O3 is load-bearing.** gcc only auto-vectorises there, and on the JP6 Orin the same
source reads 1.75e10 op/s at -O2 against 4.76e10 at -O3. A compute floor built from
the -O2 number is 2.7× too low, which raises every SOL above it and makes a stage
that has real headroom read as though it were already at the metal. gcc and clang
define `__OPTIMIZE__` the same way at -O2 and -O3, so the bench cannot see the level
from inside; it refuses to compile without `-DBENCH_OPTIMIZATION_LEVEL=3` named on
the command line instead. That still trusts the build line — a line that passes
`-O2` alongside the define compiles anyway — so check it.

Pick the unit a node actually runs on. Measured on that same target, a Python stage
sustains 2.1e7 op/s against the native single core's 5.96e9 — 282× — while its
*bandwidth* row is identical, because a bytearray copy is the machine's memcpy. One
unit cannot carry both.

§2, §5, §6 and §7 have benches too. Build what the target can take — the CUDA lane
needs `nvcc`, everything else needs a compiler and Python:

```
nvcc -O3 -std=c++17 -o fabric_bw scripts/fabric_bw.cu && ./fabric_bw   # §2 + the gpu unit
g++ -O3 -DBENCH_OPTIMIZATION_LEVEL=3 -std=c++17 -pthread -o load_gen scripts/load_gen.cpp
nvcc -O3 -std=c++17 -o load_gen_cuda scripts/load_gen.cu
python3 scripts/contention_sweep.py --load-gen ./load_gen \
        --load-gen-cuda ./load_gen_cuda                               # §5, the knee
g++ -O3 -DBENCH_OPTIMIZATION_LEVEL=3 -std=c++17 -pthread -o sched_bench scripts/sched_bench.cpp && ./sched_bench  # §6
python3 scripts/thermal_watch.py                                      # §7, run this first
```

**Run §7 first.** It reports the equilibrium the other benches that take
`--warmup-seconds` should use, and whether `clocks:` may say `modelled-steady-state` at all.

`fabric_bw` prints the `integrated` flag, and it changes the graph: on an integrated
part a host-to-device copy never leaves DRAM, so it is a copy node the graph can
often delete rather than a link it must pay for. It also refuses to derive a
bandwidth from the bus width and clock — doing that on the Orin gave a figure *below*
what the streaming kernel measured, and a ceiling you can exceed is arithmetic, not a
datasheet.

No `perf` is needed anywhere. §6's rows — timer jitter, context switch, core to core,
what pinning buys — are all observable from a process watching its own clock. What
`perf` adds is attribution, which is a debugging tool for a stage that has already
blown its budget, not an input to a floor.

`lanes/` holds what dominates on each kind of target: `soc.md` is measured on a JP6
Orin, and `workstation.md`, `mcu.md` and `phone.md` carry no measured rows at all and
say so. None of their numbers may be copied into a `machine_model.md`.

## Not here yet

No DLA or other fixed-function row is measured anywhere, and the real-NIC crossing
still needs a peer host. Those rows of `machine_model.md` stay filled by hand from
whatever harness the repo already has, and every row still needs its `method:` and
its date — that requirement does not relax because the bench is missing. A row you
cannot yet measure stays `measured: false` and `sol.py` refuses to build a floor on
it, which is the whole point: an unbuilt bench blocks a stage, it does not silently
price it.

Phases 2 and 3 are complete and enforced by `sol.py` and `budget_check.py`.
