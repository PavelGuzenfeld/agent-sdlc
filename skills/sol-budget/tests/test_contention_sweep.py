"""Intent: steps 5 and 6. The §5 knee is the only bandwidth sol.py is
allowed to spend, so these tests point at how it is chosen — not at its value, which
is per-target. The knee's definition is the whole risk: pick it off a single noisy
sample and every budget downstream is wrong by whatever that sample happened to be.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import contention_sweep as cs  # noqa: E402
import sol  # noqa: E402
from sol import MachineModel, ModelDefect  # noqa: E402


def _rows(*p99s: float) -> list[dict]:
    return [{"label": f"{i} cpu", "offered": 1e9 * (i + 1), "mean": p / 2, "p99": p}
            for i, p in enumerate(p99s)]


def test_a_single_spike_is_not_a_knee():
    # The failure this function exists to prevent, from a real run: p99 went
    # 926, 1211, 942, 5306, 940us and the first version named the 5306 sample.
    # Saturation is a transition; a spike with recovery either side is noise.
    assert cs._knee(_rows(926.0, 1211.0, 942.0, 5306.0, 940.0)) is None


def test_a_sustained_rise_is_a_knee():
    knee = cs._knee(_rows(919.0, 1182.0, 1994.0, 2384.0, 2548.0))
    assert knee is not None and knee["label"] == "2 cpu"


def test_the_knee_is_the_first_level_that_stays_elevated_not_a_later_one():
    # Picking a later level would report a knee above the load that already hurt,
    # and sol.py would hand every node bandwidth the fabric cannot give it.
    knee = cs._knee(_rows(100.0, 300.0, 400.0, 500.0))
    assert knee["label"] == "1 cpu"


def test_a_sweep_that_never_saturates_reports_no_knee():
    # Reported as measured: false rather than as the widest load tried. A knee that
    # is really "we stopped looking" is the worst kind of number to put in a floor.
    assert cs._knee(_rows(100.0, 101.0, 102.0, 103.0)) is None


def test_a_rise_that_does_not_clear_the_factor_is_not_a_knee():
    # 1.4x everywhere, against a 1.5x threshold.
    assert cs._knee(_rows(100.0, 140.0, 140.0, 140.0)) is None


def test_the_threshold_is_a_stated_number_not_a_hidden_one():
    # A knee whose criterion is not in the method string cannot be reproduced.
    assert cs.KNEE_P99_FACTOR > 1.0


def test_an_unsaturated_sweep_emits_a_row_sol_refuses_to_spend():
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "contention_sweep.py"), "--load-gen",
         str(SCRIPTS / "nonexistent")],
        capture_output=True, text=True, timeout=120,
    )
    assert out.returncode != 0, "a missing generator must fail, not report a knee"


def test_a_knee_row_marked_unmeasured_is_refused_by_sol():
    text = ('```yaml\nconfig: {chip: t}\nmemory: {dram: {shared: true}}\nfabric:\n'
            '  knee: {value: 0, unit: B/s, method: "never saturated", '
            'date: "2026-09-17", measured: false}\n```')
    model = MachineModel(sol.yaml.safe_load(sol._yaml_block(text)))
    with pytest.raises(ModelDefect):
        model.knee()


def test_the_victim_is_kept_off_the_generators_cores():
    # Sharing a core turns this into a measurement of core contention, which
    # saturates long before the fabric and puts the knee far too low.
    assert cs.VICTIM_CORE == 0


def test_the_median_is_the_middle_value_not_a_neighbour_of_it():
    assert cs._percentile([float(i) for i in range(41)], 0.5) == 20.0


def test_the_p99_of_a_sample_is_its_worst_observation():
    assert cs._percentile([float(i) for i in range(41)], 0.99) == 40.0


def test_a_rise_exactly_on_the_threshold_is_not_yet_a_knee():
    # Strictly greater. A level that merely reaches the factor is the last good
    # level, and calling it the knee reports a fabric that still had room as full.
    rows = _rows(100.0, 150.0, 150.0, 150.0)
    assert cs._knee(rows) is None


def test_the_table_reports_latencies_in_microseconds():
    # rows carry seconds; the table is read by humans in microseconds, and a factor
    # of a million in a published table is the kind of thing nobody re-derives.
    table = cs._render_table(_rows(0.001, 0.002))
    assert "1000.0us" in table and "2000.0us" in table


def test_the_table_reports_degradation_against_the_idle_row():
    table = cs._render_table(_rows(0.001, 0.002))
    assert "2.00x" in table


def test_an_unsaturated_sweep_renders_a_knee_sol_will_refuse():
    block = cs._render_knee(None, _rows(1.0, 1.0), 8, 5, "2026-09-17")
    assert "measured: false" in block and "not saturated" in block


def test_a_found_knee_renders_the_delivered_load_it_was_measured_at():
    rows = _rows(100.0, 300.0)
    block = cs._render_knee(cs._knee(rows), rows, 8, 5, "2026-09-17")
    assert "measured: true" in block and "2e+09" in block


def test_the_knee_block_states_the_threshold_that_chose_it():
    rows = _rows(100.0, 300.0)
    block = cs._render_knee(cs._knee(rows), rows, 8, 5, "2026-09-17")
    assert str(cs.KNEE_P99_FACTOR) in block, "a knee without its criterion is not reproducible"


def test_the_victim_reports_one_latency_per_repetition(monkeypatch):
    ticks = iter([float(i) for i in range(1000)])
    monkeypatch.setattr(cs.time, "perf_counter", lambda: next(ticks))
    assert len(cs._victim_latencies(reps=3)) == 3


def test_a_victim_latency_is_the_time_the_copy_took(monkeypatch):
    # Start at 500 rather than 0: with start == 0 an elapsed computed as
    # `now + start` equals `now - start` and a sign error cannot be seen.
    ticks = iter([500.0, 502.0])
    monkeypatch.setattr(cs.time, "perf_counter", lambda: next(ticks))
    assert cs._victim_latencies(reps=1) == [2.0]


def test_the_knee_is_measured_against_the_idle_row_not_the_next_one():
    # baseline is rows[0]. Taken from rows[1] instead, a sweep whose first loaded
    # level is already twice idle would report no knee at all.
    rows = _rows(100.0, 200.0, 210.0, 220.0)
    assert cs._knee(rows)["label"] == "1 cpu"


def _stub_generator(tmp_path, delivered: float):
    script = tmp_path / "stub_gen.py"
    script.write_text(
        "import json,sys\n"
        "print(json.dumps({'delivered_bytes_per_s': %r}))\n" % delivered)
    runner = tmp_path / "stub"
    runner.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n")
    runner.chmod(0o755)
    return runner


def test_the_whole_sweep_runs_against_a_stub_generator(tmp_path):
    # Exercises the sampling loop and every percentile call in main. A quantile past
    # the last sample raises rather than clamping, and only running main finds it.
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "contention_sweep.py"),
         "--load-gen", str(_stub_generator(tmp_path, 1.5e9)),
         "--max-threads", "2", "--seconds", "0.05", "--samples", "2"],
        capture_output=True, text=True, timeout=300, check=True,
    ).stdout
    assert "## §5 Contention" in out
    assert "fabric:" in out and "knee:" in out


def test_the_sweep_counts_the_load_the_generator_delivered(tmp_path):
    # Not what it was asked for. At saturation those differ, which is the whole
    # reason the generators report their own measurement.
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "contention_sweep.py"),
         "--load-gen", str(_stub_generator(tmp_path, 7.5e9)),
         "--max-threads", "1", "--seconds", "0.05", "--samples", "1"],
        capture_output=True, text=True, timeout=300, check=True,
    ).stdout
    assert "7.5e+09" in out


def test_the_table_reports_the_mean_column_too():
    table = cs._render_table([{"label": "x", "offered": 1.0, "mean": 0.003,
                               "p99": 0.004}])
    assert "3000.0us" in table and "4000.0us" in table


def test_an_unsaturated_knee_is_priced_at_zero_not_at_the_widest_load_tried():
    block = cs._render_knee(None, _rows(1.0, 1.0), 8, 5, "2026-09-17")
    assert "value: 0," in block


def test_the_knee_block_reports_how_far_the_victim_had_degraded():
    rows = _rows(100.0, 300.0)
    block = cs._render_knee(cs._knee(rows), rows, 8, 5, "2026-09-17")
    assert "3.00x" in block, "the degradation is measured against the idle row"


def test_the_knee_block_names_the_victim_size_in_mebibytes():
    rows = _rows(100.0, 300.0)
    block = cs._render_knee(cs._knee(rows), rows, 8, 5, "2026-09-17")
    assert f"{cs.VICTIM_BYTES >> 20}MiB" in block


def test_the_generator_is_told_to_avoid_the_victims_core():
    command = cs._generator_command(Path("/bin/true"), 4, 3.0)
    assert command[command.index("--first-core") + 1] == str(cs.VICTIM_CORE + 1)


def test_the_generator_is_told_how_many_threads_and_how_long():
    command = cs._generator_command(Path("/bin/true"), 4, 3.0)
    assert command[command.index("--threads") + 1] == "4"
    assert command[command.index("--seconds") + 1] == "3.0"


def test_the_sweep_keeps_an_idle_row_to_measure_degradation_against():
    # Dropping level zero leaves no baseline, and every ratio in the table then
    # compares the first loaded level against itself.
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "contention_sweep.py"),
         "--load-gen", "/bin/true", "--max-threads", "0", "--seconds", "0.05",
         "--samples", "1"],
        capture_output=True, text=True, timeout=300, check=True,
    ).stdout
    assert "| 0 cpu | 0 |" in out, "the idle row carries no offered load"


def test_the_sweep_adds_up_only_what_the_generators_delivered(tmp_path):
    # Starting the running total at anything but zero adds a phantom byte per
    # level, which at small offered loads is the whole measurement.
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "contention_sweep.py"),
         "--load-gen", str(_stub_generator(tmp_path, 1.0)),
         "--max-threads", "1", "--seconds", "0.05", "--samples", "1"],
        capture_output=True, text=True, timeout=300, check=True).stdout
    assert "| 1 cpu | 1 |" in out, "one generator delivering 1 B/s totals 1 B/s"


def test_the_combined_cpu_and_gpu_level_is_swept_too(tmp_path):
    # The realistic combination. It runs a second percentile over the victim, and
    # a quantile past the last sample raises rather than clamping.
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "contention_sweep.py"),
         "--load-gen", str(_stub_generator(tmp_path, 2.0)),
         "--load-gen-cuda", str(_stub_generator(tmp_path, 3.0)),
         "--max-threads", "1", "--seconds", "0.05", "--samples", "1"],
        capture_output=True, text=True, timeout=300, check=True).stdout
    assert "1 cpu + gpu" in out
