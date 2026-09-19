#!/usr/bin/env python3
"""§5 Contention — the saturation knee, the one bandwidth Phase 2 is allowed to spend.

Run:    python3 contention_sweep.py --load-gen ./load_gen [--load-gen-cuda ./load_gen_cuda]
                                    [--max-threads N] [--seconds S] [--samples N]
Output: the §5 markdown table, then a `fabric:` block carrying `knee`.

§2's uncontended bandwidth is what one unit gets with the machine to itself, and no
pipeline ever runs that way. This sweep puts a growing, *measured* load on the fabric
and watches a victim copy until its latency turns up. The load at that point is the
knee, and `sol.py` reaches exactly one bandwidth row — this one.

The knee is defined on latency, not on throughput. Total delivered bandwidth flattens
gently and picking a point on a flat curve is taste; the victim's p99 turning up is an
event. KNEE_P99_FACTOR names how far up counts, and it is in the method string because
a knee whose threshold is not stated is not reproducible.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

# How much worse the victim's p99 has to get before the fabric counts as saturated.
# 1.5x is a judgement call, stated rather than hidden, and printed with every knee.
KNEE_P99_FACTOR = 1.5
# The victim owns this core and the generators are kept off it.
VICTIM_CORE = 0
VICTIM_BYTES = 8 << 20
VICTIM_REPS = 40
DEFAULT_SECONDS = 3.0
DEFAULT_SAMPLES = 5


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[round(q * (len(ordered) - 1))]


def _render_table(rows: list[dict]) -> str:
    """The §5 table. Latencies in microseconds, degradation against the idle row."""
    idle = rows[0]["p99"]
    lines = ["| offered load | delivered B/s | victim mean | victim p99 | p99 vs idle |",
             "|---|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['label']} | {row['offered']:.3g} | "
                     f"{row['mean'] * 1e6:.1f}us | {row['p99'] * 1e6:.1f}us | "
                     f"{row['p99'] / idle:.2f}x |")
    return "\n".join(lines)


def _render_knee(knee: dict | None, rows: list[dict], max_threads: int,
                 samples: int, date: str) -> str:
    """The `fabric:` block. This is the row sol.py spends, so an unsaturated sweep
    has to come out `measured: false` rather than as the widest load that was tried."""
    if knee is None:
        return ("fabric:\n"
                f'  knee: {{value: 0, unit: B/s, method: "contention_sweep.py swept to '
                f'{max_threads} threads and the victim p99 never rose past '
                f'{KNEE_P99_FACTOR}x idle — the fabric was not saturated, so this sweep '
                f'found no knee and a wider one is needed", date: "{date}", '
                "measured: false}")
    idle = rows[0]["p99"]
    return ("fabric:\n"
            f'  knee: {{value: {knee["offered"]:.6g}, unit: B/s, method: '
            f'"contention_sweep.py delivered load at the first level where the victim '
            f'p99 exceeded {KNEE_P99_FACTOR}x its idle value ({knee["label"]}, '
            f'{knee["p99"] / idle:.2f}x); victim is a {VICTIM_BYTES >> 20}MiB bytearray '
            f'copy, {VICTIM_REPS} reps, median of {samples} samples; load measured as '
            f'delivered by the generator, not as requested", '
            f'date: "{date}", measured: true}}')


def _generator_command(load_gen: Path, threads: int, seconds: float) -> list[str]:
    """`--first-core` keeps the generators off the victim's core. Without it the sweep
    measures threads fighting for a core, which saturates long before the fabric does
    and puts the knee far below where it belongs."""
    return [str(load_gen), "--threads", str(threads), "--seconds", str(seconds),
            "--first-core", str(VICTIM_CORE + 1)]


def _victim_latencies(reps: int = VICTIM_REPS) -> list[float]:
    """Seconds to copy a fixed buffer, repeatedly. This is the stage being hurt."""
    os.sched_setaffinity(0, {VICTIM_CORE})
    src = bytearray(VICTIM_BYTES)
    dst = bytearray(VICTIM_BYTES)
    out = []
    for _ in range(reps):
        start = time.perf_counter()
        dst[:] = src
        out.append(time.perf_counter() - start)
    return out


def _sweep_point(load_gen: Path, threads: int, seconds: float,
                 cuda: Path | None) -> tuple[float, list[float]]:
    """Offered load and victim latencies, measured at the same time."""
    if threads == 0 and cuda is None:
        return 0.0, _victim_latencies()

    cmds = []
    if threads > 0:
        cmds.append(_generator_command(load_gen, threads, seconds))
    if cuda is not None:
        cmds.append([str(cuda), "--seconds", str(seconds)])
    procs = [subprocess.Popen(c, stdout=subprocess.PIPE, text=True) for c in cmds]
    time.sleep(seconds * 0.2)  # let the generators reach steady state
    latencies = _victim_latencies()
    delivered = 0.0
    for p in procs:
        out, _ = p.communicate(timeout=600)
        delivered += float(json.loads(out)["delivered_bytes_per_s"])
    return delivered, latencies


def _knee(rows: list[dict]) -> dict | None:
    """First row past which the victim's p99 stays elevated.

    Saturation is a transition, not a spike. Requiring every later level to stay
    above the factor throws away the single scheduling outlier that would otherwise
    be reported as the knee — which is exactly what an early version of this sweep
    did, naming 3 threads on the strength of one 5.7x sample with 1.02x either side.
    """
    baseline = rows[0]["p99"]
    for index, row in enumerate(rows[1:], start=1):
        later = rows[index:]
        if all(r["p99"] > baseline * KNEE_P99_FACTOR for r in later):
            return row
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load-gen", type=Path, required=True)
    parser.add_argument("--load-gen-cuda", type=Path, default=None)
    parser.add_argument("--max-threads", type=int, default=8)
    parser.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args()

    levels = list(range(0, args.max_threads + 1))
    rows = []
    for threads in levels:
        delivered, mean_l, p99_l = [], [], []
        for _ in range(args.samples):
            d, lat = _sweep_point(args.load_gen, threads, args.seconds, None)
            delivered.append(d)
            mean_l.append(statistics.mean(lat))
            p99_l.append(_percentile(lat, 0.99))
        rows.append({
            "label": f"{threads} cpu",
            "offered": statistics.median(delivered),
            "mean": statistics.median(mean_l),
            "p99": statistics.median(p99_l),
        })
        print(f"  {rows[-1]['label']}: offered {rows[-1]['offered']:.3g} B/s, "
              f"victim p99 {rows[-1]['p99'] * 1e6:.1f}us", file=sys.stderr)

    if args.load_gen_cuda is not None:
        # The realistic combination the skill asks for: both units at once. On an
        # integrated part they share one controller, so this is the only row that
        # describes a pipeline using both.
        delivered, mean_l, p99_l = [], [], []
        for _ in range(args.samples):
            d, lat = _sweep_point(args.load_gen, args.max_threads, args.seconds,
                                  args.load_gen_cuda)
            delivered.append(d)
            mean_l.append(statistics.mean(lat))
            p99_l.append(_percentile(lat, 0.99))
        rows.append({
            "label": f"{args.max_threads} cpu + gpu",
            "offered": statistics.median(delivered),
            "mean": statistics.median(mean_l),
            "p99": statistics.median(p99_l),
        })

    print("\n## §5 Contention\n")
    print(_render_table(rows))
    print("\n```yaml")
    print(_render_knee(_knee(rows), rows, args.max_threads, args.samples, args.date))
    print("```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
