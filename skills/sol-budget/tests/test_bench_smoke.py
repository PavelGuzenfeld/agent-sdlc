"""Intent: step 3. A Phase 1 bench is only useful if sol.py can spend
what it prints, so these tests point at the seam between the two — the row format —
never at the timings, which are per-target and assertable nowhere.

SAMPLE is a verbatim `tax_bench.cpp --samples 33` run on the JP6 Orin (R36.4.3,
2026-09-17). It is both the record that the bench executed on
real hardware and the fixture that catches format drift against sol.py. There is
deliberately no test that compiles the C++: the gate's container has no compiler, so
such a test would skip on every run and read as coverage it never provided.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sol  # noqa: E402
import tax_bench  # noqa: E402
from sol import MachineModel, ModelDefect  # noqa: E402

SAMPLE = """
```yaml
config: {chip: orin, clocks: modelled-steady-state, date: "2026-09-17"}
memory:
  dram: {shared: true}
tax:
  syscall: {value: 2.59833e-07, unit: s, method: "tax_bench.cpp getpid() through syscall(2), no vDSO shortcut; median of 33 batches of 20000, loop overhead 0.7ns subtracted; p99 261.4ns", date: "2026-09-17", measured: true}
  clock_gettime_vdso: {value: 5.01937e-08, unit: s, method: "tax_bench.cpp clock_gettime(CLOCK_MONOTONIC) via the vDSO; median of 33 batches of 20000, loop overhead 0.7ns subtracted; p99 50.5ns", date: "2026-09-17", measured: true}
  clock_gettime_syscall: {value: 3.36159e-07, unit: s, method: "tax_bench.cpp the same clock forced through syscall(2); median of 33 batches of 5000, loop overhead 0.7ns subtracted; p99 338.0ns", date: "2026-09-17", measured: true}
  sleep_granularity: {value: 5.2706e-05, unit: s, method: "tax_bench.cpp nanosleep(1ns) wall cost; median of 33, p99 58466ns", date: "2026-09-17", measured: true}
  malloc: {value: 2.0865e-08, unit: s, method: "tax_bench.cpp malloc+free of 64B, same size repeatedly so the allocator stays warm — bookkeeping only, one byte touched; the page cost is the page_fault row; median of 33 batches of 2000, loop overhead 0.7ns subtracted; p99 20.9ns", date: "2026-09-17", measured: true}
  malloc_4k: {value: 3.8481e-08, unit: s, method: "tax_bench.cpp malloc+free of 4096B, same size repeatedly so the allocator stays warm — bookkeeping only, one byte touched; the page cost is the page_fault row; median of 33 batches of 2000, loop overhead 0.7ns subtracted; p99 45.8ns", date: "2026-09-17", measured: true}
  malloc_1m: {value: 4.11375e-08, unit: s, method: "tax_bench.cpp malloc+free of 1048576B, same size repeatedly so the allocator stays warm — bookkeeping only, one byte touched; the page cost is the page_fault row; median of 33 batches of 2000, loop overhead 0.7ns subtracted; p99 65.3ns", date: "2026-09-17", measured: true}
  page_fault: {value: 5.73856e-07, unit: s, method: "tax_bench.cpp first touch of 4096 anonymous 4KiB pages, median of 33, p99 605ns", date: "2026-09-17", measured: true}
  mutex_uncontended: {value: 1.06852e-08, unit: s, method: "tax_bench.cpp pthread_mutex lock+unlock, no other thread; median of 33 batches of 20000, loop overhead 0.7ns subtracted; p99 11.0ns", date: "2026-09-17", measured: true}
  futex_wake: {value: 6.785e-06, unit: s, method: "tax_bench.cpp FUTEX_WAKE to waiter observing it, one parked waiter; median of 33, p99 17953ns", date: "2026-09-17", measured: true}
  file_write: {value: 1.10669e-06, unit: s, method: "tax_bench.cpp pwrite(2) of 4KiB to a tmpfile, page cache warm, no fsync; median of 33 batches of 20000, loop overhead 0.7ns subtracted; p99 1121.8ns", date: "2026-09-17", measured: true}
  file_read: {value: 7.72232e-07, unit: s, method: "tax_bench.cpp pread(2) of 4KiB from the page cache; median of 33 batches of 20000, loop overhead 0.7ns subtracted; p99 779.3ns", date: "2026-09-17", measured: true}
  unix_rtt: {value: 1.30405e-05, unit: s, method: "tax_bench.cpp AF_UNIX SOCK_STREAM socketpair round trip, 64B each way; median of 33 batches of 400, p99 13333ns", date: "2026-09-17", measured: true}
  unix_dgram_rtt: {value: 1.12579e-05, unit: s, method: "tax_bench.cpp AF_UNIX SOCK_DGRAM socketpair round trip, 64B each way; median of 33 batches of 400, p99 11908ns", date: "2026-09-17", measured: true}
  udp_loopback_rtt: {value: 1.69224e-05, unit: s, method: "tax_bench.cpp UDP over 127.0.0.1, both sockets connected, 64B each way; median of 33 batches of 400, p99 17500ns", date: "2026-09-17", measured: true}
  tcp_loopback_rtt: {value: 2.32108e-05, unit: s, method: "tax_bench.cpp TCP over 127.0.0.1 with TCP_NODELAY, 64B each way; median of 33 batches of 400, p99 23709ns", date: "2026-09-17", measured: true}
  sendmsg: {value: 1.37067e-06, unit: s, method: "tax_bench.cpp sendmsg(2), one 64B datagram per call; send only, receive drained outside the timed region; median of 33 batches of 256, p99 1459ns", date: "2026-09-17", measured: true}
  sendmmsg: {value: 1.04866e-06, unit: s, method: "tax_bench.cpp sendmmsg(2), 32 of the same 64B datagrams per call; send only, receive drained outside the timed region; median of 33 batches of 256, p99 1104ns", date: "2026-09-17", measured: true}
  pipe_rtt: {value: 7.67659e-06, unit: s, method: "tax_bench.cpp pipe(2) pair round trip, 64B each way; median of 33 batches of 400, p99 7878ns", date: "2026-09-17", measured: true}
  shm_rtt: {value: 2.23768e-07, unit: s, method: "tax_bench.cpp shared cache line, spinning threads pinned to cpu0 and cpu1; a pair spanning clusters costs more, so §6 owns that spread; median of 33 batches of 400, p99 38866ns", date: "2026-09-17", measured: true}
  cpu_ceiling: {value: 9.42059e+09, unit: B/s, method: "tax_bench.cpp memcpy of 64MiB, bytes copied not bus traffic — halve it for read+write; buffers sized past any last-level cache on this target, median of 33, p1 9.27e+09 B/s (the sustained end)", date: "2026-09-17", measured: true}
```
"""

KEYS = [line.split(":", 1)[0].strip()
        for line in SAMPLE.split("tax:\n", 1)[1].splitlines() if line.startswith("  ")]


def _model(text=SAMPLE):
    return MachineModel(sol.yaml.safe_load(sol._yaml_block(text)))


def _run_python_bench():
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "tax_bench.py"), "--warmup-seconds", "0",
         "--samples", "1"],
        capture_output=True, text=True, timeout=600, check=True,
    ).stdout


def test_every_crossing_the_bench_prints_can_be_spent_as_a_floor():
    model = _model()
    for key in KEYS:
        assert model.row(f"tax.{key}").spend() > 0, f"tax.{key} is not spendable"


def test_a_row_the_bench_abandoned_is_refused_rather_than_priced_at_zero():
    # pair_rtt emits measured: false when a message is lost. A crossing sol.py prices
    # at zero is a budget nothing can exceed, so the refusal is the whole point.
    abandoned = next(line for line in SAMPLE.splitlines() if "  udp_loopback_rtt:" in line)
    text = SAMPLE.replace(abandoned, abandoned.replace("measured: true", "measured: false"))
    with pytest.raises(ModelDefect):
        _model(text).row("tax.udp_loopback_rtt").spend()


def test_cpu_ceiling_is_a_rate_sol_can_divide_crossing_bytes_by():
    assert _model().row("tax.cpu_ceiling").rate() > 0


def test_every_row_carries_the_method_and_date_that_make_it_rerunnable():
    model = _model()
    for key in KEYS:
        row = model.row(f"tax.{key}")
        assert row.method and row.date, f"tax.{key} could not be rerun by anyone else"


def test_the_python_bench_covers_exactly_the_two_rows_c_cannot_reach():
    rows = {line.split(":", 1)[0].strip() for line in _run_python_bench().splitlines()}
    assert rows == {"ffi_crossing", "gil_acquire"}


def test_the_python_rows_load_and_name_how_the_gil_was_held():
    out = _run_python_bench()
    model = _model("```yaml\nconfig: {chip: t}\nmemory: {dram: {shared: true}}\n"
                   f"tax:\n{out}```")
    assert model.row("tax.ffi_crossing").spend() > 0
    assert "PyDLL" in model.row("tax.ffi_crossing").method
    assert "CDLL" in model.row("tax.gil_acquire").method


def test_the_median_is_the_middle_value_not_a_neighbour_of_it():
    # 33 samples is the default, and an off-by-one index here shifts every row in
    # the model by one sample without changing anything else about the output.
    assert tax_bench._percentile([float(i) for i in range(33)], 0.5) == 16.0


def test_the_p99_of_33_samples_is_the_worst_one():
    assert tax_bench._percentile([float(i) for i in range(33)], 0.99) == 32.0


def test_the_percentile_of_an_even_length_sample_picks_a_real_observation():
    # Never an interpolated value: a crossing cost that was never observed is not a
    # measurement, and `method:` claims every number came off this machine.
    assert tax_bench._percentile([1.0, 2.0, 3.0, 4.0], 0.5) in (2.0, 3.0)


def test_a_row_is_emitted_unmeasured_when_the_bench_got_nothing(capsys):
    tax_bench._emit("ffi_crossing", 0.0, "s", "nothing was measured", "2026-09-17")
    assert "measured: false" in capsys.readouterr().out


def test_an_emitted_row_carries_the_date_it_was_taken(capsys):
    tax_bench._emit("ffi_crossing", 1e-7, "s", "m", "2026-09-17")
    out = capsys.readouterr().out
    assert 'date: "2026-09-17"' in out and "measured: true" in out


def test_a_nanosecond_cost_is_reported_in_seconds():
    # The template's tax rows are `unit: s`. An unconverted nanosecond in that column
    # is a floor a billion times too high, and every ratio under it reads as a win.
    # 1e9 ns is one second exactly in IEEE754; 1000 ns is not, and an == on it would
    # fail on the last bit for a reason that has nothing to do with the conversion.
    assert tax_bench._seconds(1e9) == 1.0


def test_per_call_cost_is_the_batch_divided_by_its_reps(monkeypatch):
    # 100 reps taking 5000ns, against an empty loop of the same shape at 1000ns:
    # 50ns of work per call, 10ns of it loop overhead, so 40ns is the call.
    # The clock starts well away from zero on purpose: with start == 0, an elapsed
    # time computed as `end + start` equals `end - start` and a sign error is invisible.
    clock = iter([7000, 8000, 7000, 12000])
    monkeypatch.setattr(tax_bench.time, "perf_counter_ns", lambda: next(clock))
    assert tax_bench._per_call_ns(lambda _: None, None, 100, 1) == [40.0]


def test_a_call_cheaper_than_the_empty_loop_is_clamped_to_zero(monkeypatch):
    # Noise, not a negative cost. Reporting it would make _emit write measured: false,
    # which is the honest outcome; a negative number in a floor is not.
    clock = iter([7000, 12000, 7000, 8000])
    monkeypatch.setattr(tax_bench.time, "perf_counter_ns", lambda: next(clock))
    assert tax_bench._per_call_ns(lambda _: None, None, 100, 1) == [0.0]


def test_a_zero_warmup_neither_waits_nor_announces_one(capsys):
    started = tax_bench.time.perf_counter()
    tax_bench._warmup(0)
    assert tax_bench.time.perf_counter() - started < 0.5
    assert capsys.readouterr().err == ""


def test_a_requested_warmup_actually_spends_that_long(capsys):
    started = tax_bench.time.perf_counter()
    tax_bench._warmup(1)
    assert tax_bench.time.perf_counter() - started >= 1.0
    assert "§7" in capsys.readouterr().err, "the wait must cite why it is being spent"


def _rows_of(stdout):
    return {line.split(":", 1)[0].strip(): line for line in stdout.splitlines()}


def test_the_gil_pair_costs_less_than_the_crossing_it_is_measured_against():
    # CDLL does everything PyDLL does plus the release and reacquire, so the
    # difference is positive and smaller than the call itself. A sign error or a
    # sum instead of a difference breaks one of those two bounds.
    model = _model("```yaml\nconfig: {chip: t}\nmemory: {dram: {shared: true}}\n"
                   f"tax:\n{_run_python_bench()}```")
    gil = model.row("tax.gil_acquire").spend()
    crossing = model.row("tax.ffi_crossing").spend()
    assert 0 < gil < crossing


def test_the_method_names_the_interpreter_build_that_produced_the_row():
    # A tax row is per-target, and the interpreter is part of the target. Two dots
    # is major.minor.patch — "3.12" alone would not identify a build.
    method = _rows_of(_run_python_bench())["ffi_crossing"]
    build = method.split("; ")[-1].split('"')[0].strip()
    assert build.startswith(sys.implementation.name)
    assert build.split()[1].count(".") == 2, build


def test_a_gil_enabled_interpreter_is_not_reported_as_free_threaded():
    method = _rows_of(_run_python_bench())["gil_acquire"]
    enabled = getattr(sys, "_is_gil_enabled", lambda: True)()
    assert ("GIL enabled" in method) is enabled


def test_a_percentile_past_the_last_sample_is_not_silently_clamped():
    # The method strings quote a p99. With one sample every index collapses to 0 and
    # a wrong quantile is invisible, so this run takes five.
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "tax_bench.py"), "--warmup-seconds", "0",
         "--samples", "5"],
        capture_output=True, text=True, timeout=600, check=True,
    ).stdout
    assert set(_rows_of(out)) == {"ffi_crossing", "gil_acquire"}
