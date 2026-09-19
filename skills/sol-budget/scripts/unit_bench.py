#!/usr/bin/env python3
"""§4 Isolated — what a CPython node sustains, for perf/machine_model.md.

Run:    python3 unit_bench.py [--window-seconds S] [--warmup-seconds N] [--samples N]
Output: a `cpu_python` unit to paste under the `units:` block unit_bench.cpp printed.

A stage written in Python does not get the `cpu` unit's floor, and giving it one is
the dangerous direction: the SOL comes out far below what the interpreter can reach,
the ratio reads low, and the skill says optimise where no optimisation exists. This
unit is the same four rows measured through CPython, so a Python node has a floor
that is about the machine it will actually run on.

Stdlib only, deliberately. A numpy row would measure numpy's C kernels, which is the
`cpu` unit again wearing a Python name.
"""

from __future__ import annotations

import argparse
import datetime
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

WINDOWS_PER_SAMPLE = 10.0
MIN_SUSTAINED_SECONDS = 2.0
DEFAULT_SAMPLES = 9
DEFAULT_WARMUP_SECONDS = 30
DEFAULT_WINDOW_SECONDS = 1.0 / 30.0
LATENCY_REPS = 2000
# Past any last-level cache, so the stream row is DRAM rather than a cache resident.
STREAM_BYTES = 64 << 20


def _sustained_seconds(window: float) -> float:
    """How long one sustained sample runs. Never below the floor: ten windows of a
    30fps deadline is a third of a second, which measures a burst, not a rate."""
    return max(MIN_SUSTAINED_SECONDS, WINDOWS_PER_SAMPLE * window)


def _seconds(nanos: float) -> float:
    return nanos * 1e-9


def _emit(unit_key: str, value: float, unit: str, method: str, date: str) -> None:
    ok = "true" if value > 0 else "false"
    print(f"    {unit_key}: {{value: {value:.6g}, unit: {unit}, "
          f'method: "{method}", date: "{date}", measured: {ok}}}')


def _sustained_ops(seconds: float) -> float:
    """Multiply-accumulates per second, counting one mul and one add as two ops."""
    acc = 1.0
    ops = 0
    end = time.perf_counter() + seconds
    started = time.perf_counter()
    while time.perf_counter() < end:
        for _ in range(10_000):
            acc = acc * 1.0000001 + 0.0000001
        ops += 20_000
    return ops / (time.perf_counter() - started)


def _sustained_bytes(seconds: float) -> float:
    """Bytes copied per second by slicing a bytearray — payload moved, not bus traffic."""
    src = bytearray(STREAM_BYTES)
    dst = bytearray(STREAM_BYTES)
    moved = 0
    end = time.perf_counter() + seconds
    started = time.perf_counter()
    while time.perf_counter() < end:
        dst[:] = src
        moved += STREAM_BYTES
    return moved / (time.perf_counter() - started)


def _latency_rows() -> tuple[float, float]:
    """Submit-to-running and done-to-observed, through ThreadPoolExecutor.

    The pool is the mechanism a Python stage actually hands work to, and the GIL is
    part of its cost, so this is not the C++ condition-variable row in Python clothing.
    """
    dispatch, completion = [], []
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lambda: None).result()  # absorb worker-thread creation
        for _ in range(LATENCY_REPS):
            submitted = time.perf_counter_ns()
            future = pool.submit(time.perf_counter_ns)
            started = future.result()
            observed = time.perf_counter_ns()
            dispatch.append(float(started - submitted))
            completion.append(float(observed - started))
    return statistics.median(dispatch), statistics.median(completion)


def _warmup(seconds: int) -> None:
    if seconds <= 0:
        return
    print(f"warming up {seconds}s (§7: a number from a cold machine is about a "
          "cold machine)", file=sys.stderr)
    end = time.perf_counter() + seconds
    sink = 0.0
    while time.perf_counter() < end:
        for i in range(100_000):
            sink += i * 0.5
    del sink


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-seconds", type=float, default=DEFAULT_WINDOW_SECONDS)
    parser.add_argument("--warmup-seconds", type=int, default=DEFAULT_WARMUP_SECONDS)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args()

    sustained = _sustained_seconds(args.window_seconds)
    _warmup(args.warmup_seconds)
    print(f"window {args.window_seconds:.4g}s, each sustained sample {sustained:.1f}s "
          f"(>= {WINDOWS_PER_SAMPLE:g}x the window)", file=sys.stderr)

    build = f"{sys.implementation.name} {'.'.join(map(str, sys.version_info[:3]))}"
    ops = [_sustained_ops(sustained) for _ in range(args.samples)]
    moved = [_sustained_bytes(sustained) for _ in range(args.samples)]
    dispatch, completion = _latency_rows()

    print("  cpu_python:")
    _emit("sustained_ops", statistics.median(ops), "op/s",
          f"unit_bench.py interpreted multiply-accumulate on one thread; one mul plus "
          f"one add counted as two ops; each sample sustained {sustained:.1f}s; median "
          f"of {args.samples}, worst {min(ops):.3g} op/s; {build}", args.date)
    _emit("sustained_bytes", statistics.median(moved), "B/s",
          f"unit_bench.py bytearray slice copy of {STREAM_BYTES >> 20}MiB, past any "
          f"last-level cache; bytes copied, not bus traffic; each sample sustained "
          f"{sustained:.1f}s; median of {args.samples}, worst {min(moved):.3g} B/s; "
          f"{build}", args.date)
    _emit("dispatch_latency", _seconds(dispatch), "s",
          f"unit_bench.py submit to the task running, ThreadPoolExecutor with one "
          f"worker, GIL included because a Python stage pays it; median of "
          f"{LATENCY_REPS}; {build}", args.date)
    _emit("completion_latency", _seconds(completion), "s",
          f"unit_bench.py task done to Future.result() returning — the blocking "
          f"mechanism; median of {LATENCY_REPS}; {build}", args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
