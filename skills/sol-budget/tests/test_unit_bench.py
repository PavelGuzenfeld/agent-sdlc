"""Intent: step 4. §4 rows are what sol.py divides a node's work by, so
these tests point at that seam — a unit that resolves, a rate that can be a divisor,
a `measured: false` row that is refused — and never at the timings themselves.

UNITS is a verbatim `unit_bench.cpp --samples 9 --warmup-seconds 60` run on the JP6
Orin (R36.4.3, 2026-09-17), built -O3.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sol  # noqa: E402
import unit_bench  # noqa: E402
from sol import MachineModel, ModelDefect  # noqa: E402

UNITS = """
```yaml
config: {chip: orin, clocks: modelled-steady-state, date: "2026-09-17"}
memory:
  dram: {shared: true}
units:
  cpu:
    sustained_ops: {value: 4.76492e+10, unit: op/s, method: "unit_bench.cpp independent double multiply-accumulate, 8 lanes, 8 cores, one thread pinned per core; one mul plus one add counted as two ops; each sample sustained 2.0s; median of 9, worst 4.53e+10 op/s; g++ 11.4.0 — the row needs -O3, at -O2 gcc does not vectorise and it reads about 2.7x low", date: "2026-09-17", measured: true}
    sustained_bytes: {value: 2.68224e+10, unit: B/s, method: "unit_bench.cpp memcpy stream over 256MiB split across 8 cores, one thread pinned per core, past this target's last-level cache; bytes copied, not bus traffic — halve for read+write; each sample sustained 2.0s; median of 9, worst 2.65e+10 B/s", date: "2026-09-17", measured: true}
    dispatch_latency: {value: 3.424e-06, unit: s, method: "unit_bench.cpp submit to worker-observes-it, one worker parked on a condition variable, submitter on cpu0 and worker on cpu1; median of 2000", date: "2026-09-17", measured: true}
    completion_latency: {value: 3.776e-06, unit: s, method: "unit_bench.cpp worker-done to submitter-observes-it via condition variable — the blocking mechanism; the spinning one measured 160ns in the same run and is the completion_latency_poll row; median of 2000", date: "2026-09-17", measured: true}
    completion_latency_poll: {value: 1.6e-07, unit: s, method: "unit_bench.cpp worker-done to submitter-observes-it while spinning on an atomic — a poll and an interrupt are different rows; costs a core for the whole wait; median of 2000", date: "2026-09-17", measured: true}
  cpu_1core:
    sustained_ops: {value: 5.96056e+09, unit: op/s, method: "unit_bench.cpp independent double multiply-accumulate, 8 lanes, 1 core pinned to cpu0; one mul plus one add counted as two ops; each sample sustained 2.0s; median of 9, worst 5.95e+09 op/s; g++ 11.4.0 — the row needs -O3, at -O2 gcc does not vectorise and it reads about 2.7x low", date: "2026-09-17", measured: true}
    sustained_bytes: {value: 9.41983e+09, unit: B/s, method: "unit_bench.cpp memcpy stream over 256MiB split across 1 core pinned to cpu0, past this target's last-level cache; bytes copied, not bus traffic — halve for read+write; each sample sustained 2.0s; median of 9, worst 9.38e+09 B/s", date: "2026-09-17", measured: true}
    dispatch_latency: {value: 3.424e-06, unit: s, method: "unit_bench.cpp same handoff as the cpu unit — the cost belongs to the mechanism, not to how many cores run the work", date: "2026-09-17", measured: true}
    completion_latency: {value: 3.776e-06, unit: s, method: "unit_bench.cpp same handoff as the cpu unit, condition variable", date: "2026-09-17", measured: true}
```
"""


def _model(text=UNITS):
    return MachineModel(sol.yaml.safe_load(sol._yaml_block(text)))


def _run_python_bench(*extra):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "unit_bench.py"), "--warmup-seconds", "0",
         "--samples", "1", "--window-seconds", "0.0001", *extra],
        capture_output=True, text=True, timeout=900, check=True,
    ).stdout


def test_a_node_can_be_priced_against_either_width_of_the_cpu():
    # Both units carry all four rows sol.py reaches for. A dataflow that names
    # cpu_1core must not fall back to the all-core rate by accident.
    model = _model()
    for unit in ("cpu", "cpu_1core"):
        for row in ("sustained_ops", "sustained_bytes"):
            assert model.row(f"units.{unit}.{row}").rate() > 0
        for row in ("dispatch_latency", "completion_latency"):
            assert model.row(f"units.{unit}.{row}").spend() >= 0


def test_one_core_is_priced_below_every_core():
    # The whole reason both units exist. If they ever came out equal the all-core
    # row would be measuring one thread, and every parallel node's floor would be
    # eight times too slow.
    model = _model()
    assert (model.row("units.cpu_1core.sustained_ops").rate()
            < model.row("units.cpu.sustained_ops").rate())


def test_the_poll_and_the_blocking_completion_are_separate_rows():
    # §4 treats them as different mechanisms, and sol.py spends whichever the graph
    # names. Collapsing them would hide the core a spin-wait costs.
    model = _model()
    assert (model.row("units.cpu.completion_latency_poll").spend()
            < model.row("units.cpu.completion_latency").spend())


def test_an_unmeasured_unit_row_is_refused_rather_than_spent():
    line = next(l for l in UNITS.splitlines() if "    sustained_ops:" in l)
    text = UNITS.replace(line, line.replace("measured: true", "measured: false"), 1)
    with pytest.raises(ModelDefect):
        _model(text).row("units.cpu.sustained_ops").rate()


def test_every_unit_row_carries_the_method_and_date_that_make_it_rerunnable():
    model = _model()
    for unit in ("cpu", "cpu_1core"):
        for row in ("sustained_ops", "sustained_bytes", "dispatch_latency",
                    "completion_latency"):
            r = model.row(f"units.{unit}.{row}")
            assert r.method and r.date, f"units.{unit}.{row} could not be rerun"


def test_the_compute_row_names_the_build_that_produced_it():
    # -O2 and -O3 differ by 2.7x on this target, so a compute floor without its
    # compiler is not reproducible and is wrong in the direction that hides headroom.
    assert "g++" in _model().row("units.cpu.sustained_ops").method


def test_a_sustained_sample_covers_at_least_ten_windows():
    assert unit_bench._sustained_seconds(0.5) == 5.0


def test_a_short_window_still_gets_a_sustained_sample_worth_the_name():
    # 10x a 30fps window is a third of a second, which is a burst, not a rate.
    assert unit_bench._sustained_seconds(1.0 / 30.0) == 2.0


def test_the_python_unit_is_reported_separately_from_the_native_one():
    # A Python stage priced against the C++ floor gets an SOL it can never reach.
    out = _run_python_bench()
    assert "cpu_python:" in out
    model = _model("```yaml\nconfig: {chip: t}\nmemory: {dram: {shared: true}}\n"
                   f"units:\n{out.split('  cpu_python:', 1)[0]}  cpu_python:\n"
                   f"{out.split('  cpu_python:', 1)[1]}```")
    assert model.row("units.cpu_python.sustained_ops").rate() > 0


def test_the_python_rows_name_the_interpreter_build():
    method = _model("```yaml\nconfig: {chip: t}\nmemory: {dram: {shared: true}}\n"
                    f"units:\n{_run_python_bench()}```").row(
                        "units.cpu_python.dispatch_latency").method
    assert sys.implementation.name in method


def test_a_nanosecond_latency_is_reported_in_seconds():
    assert unit_bench._seconds(1e9) == 1.0


def test_a_row_with_nothing_measured_is_emitted_unmeasured(capsys):
    unit_bench._emit("sustained_ops", 0.0, "op/s", "nothing ran", "2026-09-17")
    assert "measured: false" in capsys.readouterr().out


def test_an_emitted_row_carries_the_date_it_was_taken(capsys):
    unit_bench._emit("sustained_ops", 1e9, "op/s", "m", "2026-09-17")
    out = capsys.readouterr().out
    assert 'date: "2026-09-17"' in out and "measured: true" in out


def _clock(monkeypatch, ticks):
    supply = iter(ticks)
    monkeypatch.setattr(unit_bench.time, "perf_counter", lambda: next(supply))


# end=102, started=100, one batch runs, the loop exits, elapsed = 102-100 = 2.
# The clock starts at 100 rather than 0 on purpose: with started == 0 an elapsed time
# computed as `now + started` equals `now - started` and a sign error is invisible.
ONE_BATCH_THEN_STOP = [100.0, 100.0, 100.5, 103.0, 102.0]


def test_the_op_rate_is_the_work_done_over_the_time_it_took(monkeypatch):
    _clock(monkeypatch, ONE_BATCH_THEN_STOP)
    assert unit_bench._sustained_ops(2.0) == 10_000.0


def test_the_byte_rate_is_the_payload_moved_over_the_time_it_took(monkeypatch):
    _clock(monkeypatch, ONE_BATCH_THEN_STOP)
    assert unit_bench._sustained_bytes(2.0) == unit_bench.STREAM_BYTES / 2.0


def test_work_started_exactly_on_the_deadline_is_not_counted(monkeypatch):
    # The loop runs while the clock is strictly before the deadline. Landing on it
    # means the window is over, and a batch begun there would be timed against a
    # window that no longer has room for it.
    _clock(monkeypatch, [100.0, 100.0, 102.0, 102.0])
    assert unit_bench._sustained_ops(2.0) == 0.0


def test_the_byte_loop_also_stops_on_the_deadline(monkeypatch):
    _clock(monkeypatch, [100.0, 100.0, 102.0, 102.0])
    assert unit_bench._sustained_bytes(2.0) == 0.0


def test_the_deadline_is_ahead_of_the_start_not_behind_it(monkeypatch):
    # end = now + seconds. Negated, the loop never runs and the rate is zero, which
    # _emit would publish as measured: false rather than as a floor.
    _clock(monkeypatch, [100.0, 100.0, 105.0, 105.0])
    assert unit_bench._sustained_ops(2.0) == 0.0


def test_a_zero_warmup_neither_waits_nor_announces_one(capsys):
    started = unit_bench.time.perf_counter()
    unit_bench._warmup(0)
    assert unit_bench.time.perf_counter() - started < 0.5
    assert capsys.readouterr().err == ""


def test_a_requested_warmup_actually_spends_that_long(capsys):
    started = unit_bench.time.perf_counter()
    unit_bench._warmup(1)
    assert unit_bench.time.perf_counter() - started >= 1.0
    assert "§7" in capsys.readouterr().err, "the wait must cite why it is being spent"


def test_the_latency_rows_are_both_forward_differences(monkeypatch):
    # submitted -> started -> observed. A sum instead of a difference turns either
    # row into the sum of two timestamps, which is a number near the epoch, not a cost.
    monkeypatch.setattr(unit_bench, "LATENCY_REPS", 3)
    dispatch, completion = unit_bench._latency_rows()
    assert 0 <= dispatch < 1e9 and 0 <= completion < 1e9


def test_the_stream_row_names_the_size_it_actually_copied():
    out = _run_python_bench()
    expected = f"{unit_bench.STREAM_BYTES >> 20}MiB"
    assert expected in _model(
        "```yaml\nconfig: {chip: t}\nmemory: {dram: {shared: true}}\n"
        f"units:\n{out}```").row("units.cpu_python.sustained_bytes").method


def test_a_sub_microsecond_latency_is_still_a_measurement(capsys):
    # Latencies here are fractions of a second. A positivity check written against
    # 1 rather than 0 would publish every one of them as measured: false.
    unit_bench._emit("dispatch_latency", 1e-7, "s", "m", "2026-09-17")
    assert "measured: true" in capsys.readouterr().out


def test_the_build_string_is_major_minor_patch():
    # Two dots. "3.10" alone does not identify a build, and a per-target row that
    # cannot name its interpreter is not reproducible.
    method = _model("```yaml\nconfig: {chip: t}\nmemory: {dram: {shared: true}}\n"
                    f"units:\n{_run_python_bench()}```").row(
                        "units.cpu_python.sustained_ops").method
    build = method.split("; ")[-1].split('"')[0].strip()
    assert build.split()[1].count(".") == 2, build
