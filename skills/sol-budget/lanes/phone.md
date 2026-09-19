# Lane: phone

A handset or tablet SoC. Architecturally the SoC lane, so start from `soc.md` — the
shared-fabric reasoning, the integrated-memory check and the pinning tax all carry
over unchanged. What follows is only what is different, and **none of it is measured**.

## Where the weight falls

**The clocks will not hold still, and you cannot lock them.** This is the defining
difference from a bench SoC. A phone boosts hard, throttles on skin temperature
rather than junction temperature, and has a power manager actively working against a
sustained benchmark. `thermal_watch.py` on this lane should be expected to report
`clocks: ramping`, and a model that claims `modelled-steady-state` on a handset is
almost certainly wrong.

The consequence is not "measure longer". It is that a single floor may not exist. A
stage's SOL under boost and its SOL at thermal equilibrium can differ by a factor
that matters, and the honest model carries the equilibrium number — a budget met only
while the device is cold is a budget the user never sees met.

**Heterogeneous cores are not interchangeable.** big.LITTLE means `sustained_ops`
depends on which cluster ran the work, and the scheduler moves it. The SoC lane's
`cpu` and `cpu_1core` split is not enough here: measure a big core and a little core
as separate units, and expect the spread to be larger than the core-to-core spread.
A stage that is not pinned has no single floor, which is a finding about the stage.

**The foreground is not yours.** Another app, the compositor, and the modem all share
the fabric. The §5 knee measured on an idle handset is optimistic in a way the
workstation lane's is not.

## Lane-specific tax list

- **Big versus little `sustained_ops`**, as separate units, plus what the scheduler
  does with an unpinned thread.
- **Time to throttle** under a realistic screen-on load, from `thermal_watch.py`.
- **Wake-up and idle-exit latency**, which dominates anything event-driven and is
  worse than on a mains-powered part.
- **GPU/NPU dispatch**, where the vendor runtime often adds a queueing layer the
  desktop drivers do not have.

## What this lane does not tell you

Nothing about what the OS will do to a background process, and nothing about energy.
As on the MCU lane, if the real budget is battery rather than milliseconds, this
skill's structure survives but its units do not.
