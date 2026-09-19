"""Intent: step 7. §7 decides the `clocks:` header and the warmup every
other bench takes on faith, so these tests point at how equilibrium is decided — not
at when it happens, which is per-target.
"""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import thermal_watch as tw  # noqa: E402


def _rows(*probes: float) -> list[dict]:
    return [{"t": (i + 1) * 10, "khz": 1000, "milli_c": 60000, "probe_ns": p}
            for i, p in enumerate(probes)]


def _settled(rows: list[dict]) -> float:
    return tw._settled_cost(rows)


def test_the_plateau_is_the_median_of_the_tail_not_the_last_sample():
    # A real run ended 270, 377ms after sitting near 300. Taking the last sample as
    # settled made every earlier point look 25% off it, and equilibrium was then
    # reported at the final sample — which is no measurement at all.
    rows = _rows(300.0, 300.0, 300.0, 270.0, 377.0)
    assert _settled(rows) == 300.0


def test_equilibrium_is_where_the_probe_stays_settled():
    rows = _rows(400.0, 350.0, 300.0, 301.0, 299.0, 300.0)
    assert tw._equilibrium(rows) == 30


def test_a_probe_that_settles_immediately_reports_the_first_sample():
    assert tw._equilibrium(_rows(300.0, 300.0, 300.0, 300.0)) == 10


def test_a_probe_that_never_settles_reports_nothing_rather_than_a_guess():
    # Drifting throughout. Returning the last sample would let a ramping machine
    # pass as settled, and every row measured after it would be an average.
    assert tw._equilibrium(_rows(100.0, 200.0, 300.0, 400.0, 500.0)) is None


def test_a_late_excursion_pushes_equilibrium_out():
    # Settled, then disturbed. Equilibrium must not be claimed before the
    # disturbance, because a warmup that short would end mid-excursion.
    rows = _rows(300.0, 300.0, 500.0, 300.0, 300.0)
    assert tw._equilibrium(rows) == 40


def test_clocks_that_moved_are_reported_as_ramping():
    assert tw._clock_verdict([1000, 1000, 2000]) == tw.RAMPING


def test_clocks_that_held_permit_the_modelled_steady_state_claim():
    assert tw._clock_verdict([1000, 1000, 1000]) == tw.STEADY


def test_the_plateau_ignores_more_than_just_the_last_sample():
    # Nine samples, last third is three. A tail of one would let a single noisy
    # final reading define settled, which is the bug this replaced.
    rows = _rows(900.0, 900.0, 900.0, 900.0, 900.0, 900.0, 300.0, 300.0, 900.0)
    assert _settled(rows) == 300.0


def test_a_sample_exactly_on_the_tolerance_counts_as_settled():
    # 3% out, against a 3% tolerance. Excluding the boundary would push every
    # equilibrium one sample later and overstate the warmup every bench needs.
    rows = _rows(103.0, 100.0, 100.0, 100.0)
    assert tw._equilibrium(rows) == 10


def test_the_sweep_samples_inside_the_window_it_was_given():
    assert tw._marks(30) == [5, 15, 30]


def test_a_sweep_shorter_than_the_first_mark_still_takes_one_sample():
    # Otherwise a short run reports nothing at all and reads as a failure.
    assert tw._marks(2) == [2]


def test_the_load_is_kept_off_the_probes_core():
    command = tw._load_command(10, 8)
    assert f"{tw.PROBE_CORE + 1}-7" in command


def test_the_table_reports_celsius_from_millicelsius():
    table = tw._render_table(_rows(1e6), 1e6)
    assert "60.0C" in table


def test_the_table_reports_the_probe_in_milliseconds():
    table = tw._render_table(_rows(1e6), 1e6)
    assert "1.0ms" in table


def test_the_table_reports_each_sample_against_the_plateau():
    table = tw._render_table([{"t": 10, "khz": 1, "milli_c": 0, "probe_ns": 2e6}], 1e6)
    assert "2.000x" in table


def test_the_plateau_is_taken_from_the_end_of_the_run_not_the_start():
    # Hot at the start, settled at the end. Reading the head would call the ramp
    # the plateau and report equilibrium before the machine had settled at all.
    rows = _rows(900.0, 900.0, 900.0, 300.0, 300.0, 300.0)
    assert _settled(rows) == 300.0


def test_the_plateau_never_collapses_to_a_single_sample():
    # max(3, n//3): with six samples n//3 is two, and the floor of three is what
    # stops one noisy reading from carrying the whole verdict.
    rows = _rows(100.0, 100.0, 100.0, 300.0, 300.0, 900.0)
    assert _settled(rows) == 300.0


def test_a_clock_set_that_is_empty_does_not_claim_a_ramp():
    # No readable sysfs is "unknown", not "moved". Reporting a ramp there would
    # make every model on such a target refuse a steady-state claim it may deserve.
    assert tw._clock_verdict([]) == tw.STEADY


def test_equilibrium_is_measured_as_distance_from_the_plateau(monkeypatch):
    # The comparison is |probe - settled| / settled. Multiplying instead of
    # dividing makes the tolerance scale with the machine's speed, so a slow
    # target would accept anything and a fast one would never settle.
    rows = _rows(200.0, 100.0, 100.0, 100.0)
    assert tw._equilibrium(rows) == 20


def test_the_load_spans_every_core_except_the_probes():
    assert tw._load_command(10, 8)[4] == "1-7"


def test_the_load_stops_itself_after_the_sweep():
    # A spinner that outlives the run leaves the machine hot for whatever measures
    # next, and this one is started detached.
    assert tw._load_command(10, 8)[0] == "timeout"


import subprocess  # noqa: E402


def test_a_missing_temperature_reads_as_zero_not_as_one():
    table = tw._render_table([{"t": 5, "khz": 1, "milli_c": None, "probe_ns": 1e6}], 1e6)
    assert "0.0C" in table


def test_the_probe_is_the_time_the_work_took(monkeypatch):
    # Start well away from zero: with start == 0, `end + start` equals `end - start`.
    ticks = iter([5_000_000_000, 5_200_000_000])
    monkeypatch.setattr(tw.time, "perf_counter_ns", lambda: next(ticks))
    monkeypatch.setattr(tw.os, "sched_setaffinity", lambda *_: None)
    monkeypatch.setattr(tw, "PROBE_ITERATIONS", 1)
    assert tw._probe_ns() == 200_000_000.0


def test_a_machine_that_will_not_say_how_many_cores_it_has_still_runs(monkeypatch):
    # `or 2`, not `and 2`: a None core count must fall back, not collapse to None
    # and crash the range the load is pinned to.
    monkeypatch.setattr(tw.os, "cpu_count", lambda: None)
    assert tw._load_command(1, tw.os.cpu_count() or 2)[4] == "1-1"


def test_the_first_readable_sysfs_file_wins(tmp_path):
    (tmp_path / "a").write_text("not a number\n")
    (tmp_path / "b").write_text("1234\n")
    assert tw._read_first(str(tmp_path / "*")) == 1234


def test_the_hottest_zone_is_the_maximum_not_the_first(tmp_path):
    (tmp_path / "a").write_text("60000\n")
    (tmp_path / "b").write_text("71000\n")
    (tmp_path / "c").write_text("65000\n")
    assert tw._max_of(str(tmp_path / "*")) == 71000


def test_an_unreadable_zone_does_not_hide_the_ones_after_it(tmp_path):
    # `continue`, not `break`. One unparseable file must not stop the scan, or the
    # hottest zone goes unreported on any machine that exposes an odd one first.
    (tmp_path / "a").write_text("garbage\n")
    (tmp_path / "b").write_text("70000\n")
    assert tw._max_of(str(tmp_path / "*")) == 70000
    assert tw._read_first(str(tmp_path / "*")) == 70000


def test_the_whole_watch_runs_and_emits_a_config_block():
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "thermal_watch.py"), "--seconds", "1",
         "--threads", "1"],
        capture_output=True, text=True, timeout=300, check=True,
    ).stdout
    assert "## §7 Power and thermal" in out
    assert "config:" in out and "clocks:" in out and "warmup_seconds:" in out


def test_the_watch_reports_the_verdict_matching_what_the_clocks_did():
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "thermal_watch.py"), "--seconds", "1",
         "--threads", "1"],
        capture_output=True, text=True, timeout=300, check=True,
    ).stdout
    held = "Clocks HELD" in out
    assert held == (tw.STEADY in out.split("```yaml")[1]), \
        "the prose and the config block must not disagree about the same run"


def _hot(*milli_c: int) -> list[dict]:
    return [{"t": (i + 1) * 10, "khz": 1, "milli_c": c, "probe_ns": 1e6}
            for i, c in enumerate(milli_c)]


def test_a_machine_that_barely_heated_is_reported_as_already_warm():
    # Measured: a start at 64.8C settled in 5s where a cold start took ~30s. A
    # warmup figure from a warm board is the dangerous kind of true.
    assert tw._started_warm(_hot(64800, 64700, 64900, 64500)) is True


def test_a_machine_that_heated_through_the_sweep_is_not_called_warm():
    assert tw._started_warm(_hot(60100, 62700, 64300, 66500)) is False


def test_a_sweep_with_no_temperatures_makes_no_warm_start_claim():
    assert tw._started_warm(_hot()) is False


def test_two_samples_are_enough_to_judge_a_warm_start():
    # The guard needs at least two temperatures, not more than two. Requiring three
    # would make a short sweep silently skip the warning it exists to give.
    assert tw._started_warm(_hot(64800, 64900)) is True


def test_a_rise_exactly_on_the_warm_threshold_still_counts_as_warm():
    assert tw._started_warm(_hot(60000, 62000)) is True


def test_a_rise_one_millidegree_past_the_threshold_is_a_cold_start():
    assert tw._started_warm(_hot(60000, 62001)) is False


def test_the_warm_start_check_measures_the_rise_from_the_first_sample():
    # Against temps[0], not temps[1]. Starting from the second sample would miss
    # exactly the early climb that distinguishes a cold board.
    assert tw._started_warm(_hot(60000, 65000, 65100)) is False


def test_the_load_falls_back_when_the_core_count_is_unknown(monkeypatch):
    seen = []
    monkeypatch.setattr(tw.os, "cpu_count", lambda: None)
    monkeypatch.setattr(tw.subprocess, "Popen",
                        lambda cmd, **kw: seen.append(cmd) or _FakeProc())
    tw._load(1, 1.0)
    assert seen and "1-1" in seen[0], "a None core count must fall back, not crash"


class _FakeProc:
    def terminate(self):
        pass


def test_the_watch_waits_for_each_sample_time():
    # `now - started`, not `now + started`: summing two clock readings is always
    # past any mark, so every sample would be taken at once and the sweep would
    # report a settled machine it never actually watched.
    start = tw.time.perf_counter()
    subprocess.run(
        [sys.executable, str(SCRIPTS / "thermal_watch.py"), "--seconds", "5",
         "--threads", "1"],
        capture_output=True, text=True, timeout=300, check=True)
    assert tw.time.perf_counter() - start >= 5.0






def test_the_prose_and_the_config_block_agree_about_equilibrium():
    # The branch is `equilibrium is None`. Inverted, a run that settled prints the
    # "never settled" prose above a config block carrying a real warmup_seconds,
    # and a reader believes whichever of the two they happened to look at.
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "thermal_watch.py"), "--seconds", "1",
         "--threads", "1"],
        capture_output=True, text=True, timeout=300, check=True).stdout
    block = out.split("```yaml")[1]
    assert ("Equilibrium at" in out) == ("warmup_seconds: unknown" not in block), \
        "a settled run must not be described as unsettled, or the reverse"


def test_the_warm_start_note_states_its_threshold_in_celsius():
    # Read off the rendered note rather than recomputed here: asserting the
    # arithmetic against itself is how the previous version of this test passed
    # no matter what the conversion did.
    assert "2.0C" in tw._warm_start_note()


def test_the_warm_start_note_says_the_figure_is_not_from_cold():
    assert "not from cold" in tw._warm_start_note()


def test_the_warm_start_branch_actually_runs(monkeypatch, capsys):
    # Reached only on a machine that was already hot, which the gate's container is
    # not. Without this the whole branch — including the note it prints — is never
    # executed by any test, and a typo there surfaces on a real board or never.
    monkeypatch.setattr(tw, "_started_warm", lambda rows: True)
    monkeypatch.setattr(tw, "_load", lambda threads, seconds: [])
    monkeypatch.setattr(tw, "_max_of", lambda pattern: 64800)
    monkeypatch.setattr(tw, "_read_first", lambda pattern: 1497600)
    monkeypatch.setattr(tw, "PROBE_ITERATIONS", 1)
    monkeypatch.setattr(tw.os, "sched_setaffinity", lambda *_: None)
    monkeypatch.setattr(sys, "argv", ["thermal_watch.py", "--seconds", "1"])
    assert tw.main() == 0
    assert "already warm" in capsys.readouterr().out
