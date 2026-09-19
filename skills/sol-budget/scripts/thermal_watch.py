#!/usr/bin/env python3
"""§7 Power and thermal — how long until a number means anything.

Run:    python3 thermal_watch.py [--seconds N] [--threads N] [--date D]
Output: the §7 table, then the `clocks:` verdict for the model's config header.

Every other bench in this skill takes a warmup on faith. This one measures it: it
loads every core, samples the clocks and the hottest zone until they stop moving, and
says how long that took. The answer decides the `clocks:` line in `machine_model.md`,
and that line is load-bearing — `sol.py` refuses a model whose header does not match
the machine in front of you.

Two honest outcomes. If the clocks never move under sustained load, the steady state
is the only state and `modelled-steady-state` is true after the warmup this reports.
If they do move, nothing here can lock them — that needs root — and the model either
carries a locked-clock run or says plainly that its rows are averages over a ramp.
"""

from __future__ import annotations

import argparse
import datetime
import glob
import os
import statistics
import subprocess
import sys
import time

# A fixed unit of work, re-timed as the machine heats. Its cost is the thing that
# actually matters: clocks are a proxy, throughput is the observable.
PROBE_ITERATIONS = 2_000_000
# The probe owns this core; the load is kept off it.
PROBE_CORE = 0
# Sampled on a log-ish schedule because the interesting part is the first minute and
# the confirmation is the last one.
SAMPLE_AT = (5, 15, 30, 60, 120, 180, 240, 300, 360)
# Fraction of the settled probe cost within which a sample counts as equilibrium.
SETTLED_WITHIN = 0.03
# A rise smaller than this over the whole sweep means the machine was already hot.
WARM_START_MILLI_C = 2000


STEADY = "modelled-steady-state"
RAMPING = "ramping — see the table; not lockable without root"


def _settled_cost(rows: list[dict]) -> float:
    """The plateau the probe ends on, as the median of the last third.

    Not the final sample: one noisy reading there would redefine settled and make
    every earlier point look far from it, which is how an early version of this
    reported equilibrium at the last sample it happened to take.
    """
    tail = rows[-max(3, len(rows) // 3):]
    return statistics.median(r["probe_ns"] for r in tail)


def _equilibrium(rows: list[dict]) -> int | None:
    """First sample time from which the probe never leaves the plateau again.

    None means the machine was still moving when the sweep ended. That is a finding
    — every row measured on it is an average over a ramp — and reporting the last
    sample instead would hide exactly that.
    """
    settled = _settled_cost(rows)
    for index, row in enumerate(rows):
        if all(abs(r["probe_ns"] - settled) / settled <= SETTLED_WITHIN
               for r in rows[index:]):
            return int(row["t"])
    return None


def _started_warm(rows: list[dict]) -> bool:
    """Whether the machine was already hot when the sweep began.

    A warm start makes the probe flat from the first sample and the reported warmup
    comes out near zero — true for that machine in that state, and badly wrong for
    anyone who runs the pipeline from cold. Measured on the JP6 Orin: a cold start
    settled over about 30s, a start at 64.8C settled in 5.
    """
    temps = [r["milli_c"] for r in rows if r["milli_c"] is not None]
    if len(temps) < 2:
        return False
    return (max(temps) - temps[0]) <= WARM_START_MILLI_C


def _warm_start_note() -> str:
    """What to tell a reader whose warmup figure came off an already-hot machine."""
    return (f"**The machine was already warm.** The hottest zone rose by less than "
            f"{WARM_START_MILLI_C / 1000:.1f}C across the whole sweep, so this is the "
            f"time to settle from wherever it already was, not from cold. A pipeline "
            f"that starts on a cold board will take longer. Let it idle and run this "
            f"again before trusting the figure.")


def _clock_verdict(khz: list[int]) -> str:
    """What the `clocks:` header may claim. Anything that moved is a ramp."""
    return STEADY if len(set(khz)) <= 1 else RAMPING


def _marks(seconds: int) -> list[int]:
    """Sample times inside the requested sweep. A sweep shorter than the first mark
    still gets one sample at its own end rather than none."""
    return [t for t in SAMPLE_AT if t <= seconds] or [seconds]


def _load_command(seconds: float, cores: int) -> list[str]:
    """One spinner, kept off the probe's core. Getting this range wrong is how the
    probe ends up sharing a core with the load and measuring the scheduler."""
    return ["timeout", str(seconds), "taskset", "-c",
            f"{PROBE_CORE + 1}-{cores - 1}", "bash", "-c", "while :; do :; done"]


def _render_table(rows: list[dict], settled: float) -> str:
    """The §7 table. Temperatures in C from milli-C, probe cost in ms from ns."""
    lines = ["| t | cpu0 kHz | hottest zone | fixed-work probe | vs settled |",
             "|---|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['t']}s | {row['khz']} | "
                     f"{(row['milli_c'] or 0) / 1000:.1f}C | "
                     f"{row['probe_ns'] / 1e6:.1f}ms | "
                     f"{row['probe_ns'] / settled:.3f}x |")
    return "\n".join(lines)


def _read_first(pattern: str) -> int | None:
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path) as handle:
                return int(handle.read().strip())
        except (OSError, ValueError):
            continue
    return None


def _max_of(pattern: str) -> int | None:
    values = []
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path) as handle:
                values.append(int(handle.read().strip()))
        except (OSError, ValueError):
            continue
    return max(values) if values else None


def _governor() -> str:
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") as handle:
            return handle.read().strip()
    except OSError:
        return "unknown"


def _probe_ns() -> float:
    """Wall time for a fixed amount of work. Falls as clocks rise, rises as they fall.

    Pinned to a core the load generators are kept off. Sharing a core with them makes
    this a measurement of the scheduler, and its noise then swamps the thermal signal
    it exists to show.
    """
    os.sched_setaffinity(0, {PROBE_CORE})
    start = time.perf_counter_ns()
    acc = 0.0
    for i in range(PROBE_ITERATIONS):
        acc += i * 0.5
    end = time.perf_counter_ns()
    if acc < 0:
        print("impossible", file=sys.stderr)
    return float(end - start)


def _load(threads: int, seconds: float) -> list[subprocess.Popen]:
    """Busy every core. Plain shell spinners, so this needs nothing built first."""
    command = _load_command(seconds, os.cpu_count() or 2)
    return [
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(threads)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=max(SAMPLE_AT))
    parser.add_argument("--threads", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args()

    marks = _marks(args.seconds)
    print(f"loading {args.threads} threads for {args.seconds}s, sampling at "
          f"{marks}", file=sys.stderr)

    procs = _load(args.threads, args.seconds + 5)
    started = time.perf_counter()
    rows = []
    try:
        for mark in marks:
            while time.perf_counter() - started < mark:
                time.sleep(0.5)
            rows.append({
                "t": mark,
                "khz": _read_first("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"),
                "milli_c": _max_of("/sys/class/thermal/thermal_zone*/temp"),
                "probe_ns": _probe_ns(),
            })
            last = rows[-1]
            print(f"  t={last['t']:>4}s  freq={last['khz']}kHz  "
                  f"temp={(last['milli_c'] or 0) / 1000:.1f}C  "
                  f"probe={last['probe_ns'] / 1e6:.1f}ms", file=sys.stderr)
    finally:
        for p in procs:
            p.terminate()

    settled = _settled_cost(rows)
    equilibrium = _equilibrium(rows)
    clocks = {r["khz"] for r in rows if r["khz"] is not None}
    verdict = _clock_verdict([r["khz"] for r in rows if r["khz"] is not None])
    moved = verdict == RAMPING

    print("\n## §7 Power and thermal\n")
    print(_render_table(rows, settled))

    print()
    if moved:
        print(f"Clocks MOVED under load ({sorted(clocks)} kHz). The steady state is not "
              f"the only state, and nothing here can lock them — that needs root. A "
              f"model built from this machine must either carry a locked-clock run or "
              f"say in `clocks:` that its rows are averages over a ramp.")

    else:
        only = next(iter(clocks)) if clocks else "unknown"
        print(f"Clocks HELD at {only} kHz for the whole run under {args.threads} "
              f"threads, governor `{_governor()}`. The steady state is the only state, "
              f"so `modelled-steady-state` is honest once the warmup below has passed.")


    if equilibrium is None:
        print("\nThe probe never settled within "
              f"{SETTLED_WITHIN:.0%} of its final value — sweep longer before trusting "
              "any warmup figure.")
    else:
        print(f"\nEquilibrium at **t={equilibrium}s**: the fixed-work probe is within "
              f"{SETTLED_WITHIN:.0%} of its settled cost from there on. Use that as the "
              f"`--warmup-seconds` for every other bench on this target.")
        if _started_warm(rows):
            print("\n" + _warm_start_note())

    print("\n```yaml")
    print("config:")
    print(f'  clocks: "{verdict}"')
    print(f'  warmup_seconds: {equilibrium if equilibrium is not None else "unknown"}')
    print(f'  date: "{args.date}"')
    print("```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
