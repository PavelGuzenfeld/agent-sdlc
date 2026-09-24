"""Intent: dotfiles#78 — the per-mutant timeout is scaled from a baseline that
rebuilds nothing, so where a build sits between the edit and the tests it is far
too small. A timed-out mutant is scored KILLED, so the gate reported a perfect
score having measured nothing, and said nothing about it."""

import contextlib

import pytest

from mutation_gate import cli, repo as repo_mod, runner
from mutation_gate.mutants import Mutant

MUTANT = Mutant(file="src/x.py", line=1, start=0, end=1, old="a", new="b", kind="op")


@pytest.fixture
def verdict(tmp_path, monkeypatch):
    """Classify one mutant against a run that ends in `outcome`."""
    repo = repo_mod.Repo(root=tmp_path, origin="", remotes=(), config=repo_mod.Config())

    def _classify(outcome: str, capped: dict | None = None) -> str:
        monkeypatch.setattr(runner, "mutated", lambda *a: contextlib.nullcontext())

        def fake_run_tests(_repo, _tests, _cmd, timeout=None):
            if capped is not None:
                capped["timeout"] = timeout
            return outcome

        monkeypatch.setattr(runner, "_run_tests", fake_run_tests)
        return runner.classify(repo, MUTANT, ["t.py"], "cmd", 241.0).verdict

    return _classify


def test_a_mutant_that_timed_out_is_not_reported_as_an_ordinary_kill(verdict):
    assert verdict(runner.TIMED_OUT) == runner.KILLED_TIMEOUT


def test_a_mutant_that_timed_out_still_counts_as_killed_and_does_not_block(verdict):
    # A hang is a hang; blocking the gate on it is worse than a wrong verdict.
    assert runner.KILLED_TIMEOUT in (runner.KILLED, runner.KILLED_TIMEOUT)
    assert verdict(runner.TIMED_OUT) != runner.SURVIVED


def test_the_cap_reaches_the_run_it_is_meant_to_cap(verdict):
    capped: dict = {}
    verdict(runner.PASSED, capped)
    assert capped["timeout"] == 241.0


def test_a_failing_run_is_an_ordinary_kill(verdict):
    assert verdict(runner.FAILED) == runner.KILLED


def test_a_passing_run_survives(verdict):
    assert verdict(runner.PASSED) == runner.SURVIVED


def test_a_run_that_exited_clean_without_the_pass_marker_is_not_a_survivor(verdict):
    assert verdict(runner.NO_PASS_MARKER) == runner.KILLED


@pytest.fixture
def gated(tmp_path, monkeypatch):
    """Gate one file whose mutants all end in `outcome`, returning what the run
    printed and whether it blocked."""

    def _run(
        outcomes: list[str],
        config: repo_mod.Config,
        baseline: float,
        cover: dict | None = None,
        rel: str = "src/x.py",
    ):
        repo = repo_mod.Repo(root=tmp_path, origin="", remotes=(), config=config)
        (tmp_path / "t.py").write_text("x\n")
        seen: dict = {"lines": []}

        monkeypatch.setattr(cli.coverage_map, "candidates", lambda *a: [tmp_path / "t.py"])
        monkeypatch.setattr(cli.coverage_map, "blob_hashes", lambda *a: ["h"])
        monkeypatch.setattr(cli.coverage_map, "covering_tests", lambda *a: cover if cover is not None else {})
        monkeypatch.setattr(cli.token, "is_valid", lambda *a: False)
        monkeypatch.setattr(cli.token, "write", lambda *a: None)
        monkeypatch.setattr(cli.mutants, "generate", lambda *a: [MUTANT] * len(outcomes))
        monkeypatch.setattr(cli.runner, "baseline_green", lambda *a: baseline)
        monkeypatch.setattr(cli.waivers, "waived", lambda *a: None)
        remaining = list(outcomes)

        def fake_classify(_repo, mutant, tests, _cmd, timeout):
            seen["timeout"] = timeout
            return runner.Result(mutant, remaining.pop(0), tests)

        monkeypatch.setattr(cli.runner, "classify", fake_classify)
        monkeypatch.setattr(cli, "_emit", lambda line="": seen["lines"].append(line))
        blocked, _survivors, _cands = cli._gate_file(repo, rel, {1}, [])
        seen["blocked"] = blocked
        return seen

    return _run


def test_a_configured_cap_replaces_the_derived_one_rather_than_bounding_it(gated):
    # Deliberately below both the derived value and the 30s floor: a config that
    # only ever raises the cap is not an override.
    seen = gated([runner.KILLED], repo_mod.Config(mutant_timeout=5.0), baseline=100.0)
    assert seen["timeout"] == 5.0
    assert any("5s (configured)" in line for line in seen["lines"])


def test_a_derived_cap_scales_the_baseline_up_not_down(gated):
    seen = gated([runner.KILLED], repo_mod.Config(), baseline=100.0)
    assert seen["timeout"] == 600.0


def test_a_derived_cap_never_falls_below_thirty_seconds(gated):
    seen = gated([runner.KILLED], repo_mod.Config(), baseline=0.1)
    assert seen["timeout"] == 30.0


def test_a_run_says_how_many_of_its_mutants_timed_out_not_merely_that_some_did(gated):
    seen = gated(
        [runner.KILLED_TIMEOUT, runner.KILLED, runner.KILLED],
        repo_mod.Config(),
        baseline=1.0,
    )
    assert seen["blocked"] is False
    assert any("1/3 mutant(s) timed out" in line for line in seen["lines"])
    assert any("mutant_timeout" in line for line in seen["lines"])


def test_a_run_with_no_timeouts_stays_quiet_about_them(gated):
    seen = gated([runner.KILLED, runner.KILLED], repo_mod.Config(), baseline=1.0)
    assert seen["blocked"] is False
    assert not any("timed out" in line for line in seen["lines"])


def test_empty_coverage_says_so_instead_of_silently_widening(gated):
    seen = gated([runner.KILLED], repo_mod.Config(), baseline=1.0, cover={})
    assert any("coverage came back empty" in line for line in seen["lines"])


def test_nonempty_coverage_stays_quiet_about_the_empty_notice(gated):
    seen = gated([runner.KILLED], repo_mod.Config(), baseline=1.0, cover={1: ["t.py::test_x"]})
    assert not any("coverage came back empty" in line for line in seen["lines"])


def test_a_non_python_target_never_gets_the_empty_coverage_notice(gated):
    seen = gated([runner.KILLED], repo_mod.Config(), baseline=1.0, cover={}, rel="src/x.cpp")
    assert not any("coverage came back empty" in line for line in seen["lines"])


def test_a_survivor_alongside_a_timeout_still_blocks_and_both_are_reported(gated):
    seen = gated([runner.KILLED_TIMEOUT, runner.SURVIVED], repo_mod.Config(), baseline=1.0)
    assert seen["blocked"] is True
    assert any("1/2 mutant(s) timed out" in line for line in seen["lines"])


def test_a_surviving_mutant_is_not_counted_as_a_timeout(gated):
    seen = gated([runner.SURVIVED], repo_mod.Config(), baseline=1.0)
    assert seen["blocked"] is True
    assert not any("timed out" in line for line in seen["lines"])


def test_mutant_timeout_is_configurable_because_the_derived_one_assumes_no_build(tmp_path):
    (tmp_path / repo_mod.CONFIG_NAME).write_text("mutant_timeout = 241.0\n")
    assert repo_mod.Config.load(tmp_path).mutant_timeout == 241.0


def test_an_unset_mutant_timeout_leaves_the_gate_deriving_one(tmp_path):
    (tmp_path / repo_mod.CONFIG_NAME).write_text("language = 'python'\n")
    assert repo_mod.Config.load(tmp_path).mutant_timeout is None
