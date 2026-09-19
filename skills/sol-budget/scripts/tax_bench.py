#!/usr/bin/env python3
"""§8 Tax — the two crossings only a Python process can show, for perf/machine_model.md.

Run:    python3 tax_bench.py [--warmup-seconds N] [--samples N] [--date YYYY-MM-DD]
Output: `tax:` rows to paste under the block tax_bench.cpp printed. Nothing here
        overlaps that file; every other crossing is measured in C++ where the
        interpreter is not in the way.

Method for both rows rests on one fact: ctypes.CDLL drops the GIL around a foreign
call and ctypes.PyDLL does not. PyDLL alone is therefore the bare crossing, and the
difference between the two is one GIL release plus one reacquire.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import datetime
import statistics
import sys
import time

BATCH = 200_000
DEFAULT_SAMPLES = 33
DEFAULT_WARMUP_SECONDS = 30


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[round(q * (len(ordered) - 1))]


def _seconds(nanos: float) -> float:
    return nanos * 1e-9


def _emit(key: str, value: float, unit: str, method: str, date: str) -> None:
    ok = "true" if value > 0 else "false"
    print(f"  {key}: {{value: {value:.6g}, unit: {unit}, "
          f'method: "{method}", date: "{date}", measured: {ok}}}')


def _per_call_ns(fn, arg, reps: int, samples: int) -> list[float]:
    """Seconds per call over `samples` batches, empty-loop overhead removed."""
    overhead = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        for _ in range(reps):
            pass
        overhead.append((time.perf_counter_ns() - start) / reps)
    floor = statistics.median(overhead)
    out = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        for _ in range(reps):
            fn(arg)
        out.append(max(0.0, (time.perf_counter_ns() - start) / reps - floor))
    return out


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
    parser.add_argument("--warmup-seconds", type=int, default=DEFAULT_WARMUP_SECONDS)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    args = parser.parse_args()

    libc_path = ctypes.util.find_library("c")
    if not libc_path:
        sys.exit("no libc found; both rows here are foreign calls into it")
    holding = ctypes.PyDLL(libc_path).abs      # keeps the GIL
    dropping = ctypes.CDLL(libc_path).abs      # drops and reacquires it
    for fn in (holding, dropping):
        fn.restype = ctypes.c_int
        fn.argtypes = [ctypes.c_int]

    _warmup(args.warmup_seconds)
    held = _per_call_ns(holding, -1, BATCH, args.samples)
    dropped = _per_call_ns(dropping, -1, BATCH, args.samples)

    build = f"{sys.implementation.name} {'.'.join(map(str, sys.version_info[:3]))}"
    gil_disabled = not getattr(sys, "_is_gil_enabled", lambda: True)()
    crossing = statistics.median(held)
    gil = max(0.0, statistics.median(dropped) - crossing)

    _emit("ffi_crossing", _seconds(crossing), "s",
          f"tax_bench.py ctypes.PyDLL abs() — GIL held throughout, so this is the "
          f"crossing alone; median of {args.samples} batches of {BATCH}, empty-loop "
          f"overhead subtracted; p99 {_percentile(held, 0.99):.0f}ns; {build}",
          args.date)
    _emit("gil_acquire", _seconds(gil), "s",
          f"tax_bench.py ctypes.CDLL minus ctypes.PyDLL abs() — one release plus one "
          f"reacquire, single-threaded so no waiting; median of {args.samples} batches "
          f"of {BATCH}; {build}, GIL "
          f"{'disabled — this row is not a contention cost' if gil_disabled else 'enabled'}",
          args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
