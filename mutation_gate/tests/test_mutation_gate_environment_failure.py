"""Intent: #451 — a mutant run that exits non-zero without any test failing
(pytest internal or usage error, no tests collected) is the environment dying.
Scoring it KILLED hides a survivor, so the gate refuses like a bad baseline."""

import pytest

from mutation_gate import cli, repo as repo_mod, runner
from mutation_gate.mutants import Mutant

MUTANT = Mutant(file="src/x.py", line=1, start=0, end=1, old="a", new="b", kind="op")


@pytest.fixture
def run_mutant(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CACHE_ROOT", tmp_path / "cache")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("a")
    repo = repo_mod.Repo(root=tmp_path, origin="", remotes=(), config=repo_mod.Config())

    def _run(exit_code: int) -> runner.Result:
        return runner.classify(repo, MUTANT, ["t.py"], f"exit {exit_code}; echo {{tests}}", 30.0)

    return _run


@pytest.mark.parametrize("exit_code", [3, 4, 5])
def test_a_run_that_aborts_without_a_test_failing_blocks_instead_of_counting_as_killed(
    run_mutant, exit_code
):
    with pytest.raises(repo_mod.GateError, match="no test failed"):
        run_mutant(exit_code)


def test_a_run_where_a_test_failed_is_still_killed(run_mutant):
    assert run_mutant(1).verdict == runner.KILLED


def test_a_run_that_passes_still_survives(run_mutant):
    assert run_mutant(0).verdict == runner.SURVIVED


def test_an_aborted_run_leaves_the_source_unmutated(run_mutant, tmp_path):
    with pytest.raises(repo_mod.GateError):
        run_mutant(4)
    assert (tmp_path / "src" / "x.py").read_text() == "a"


def test_a_parametrized_test_id_containing_a_pipe_reaches_the_mutant_run_whole(
    tmp_path, monkeypatch
):
    repo = repo_mod.Repo(root=tmp_path, origin="", remotes=(), config=repo_mod.Config())
    (tmp_path / "t.py").write_text("x\n")
    monkeypatch.setattr(cli.coverage_map, "candidates", lambda *a: [tmp_path / "t.py"])
    monkeypatch.setattr(cli.coverage_map, "blob_hashes", lambda *a: ["h"])
    monkeypatch.setattr(cli.coverage_map, "covering_tests", lambda *a: {1: ["t.py::test[a|b]|run"]})
    monkeypatch.setattr(cli.token, "is_valid", lambda *a: False)
    monkeypatch.setattr(cli.token, "write", lambda *a: None)
    monkeypatch.setattr(cli.mutants, "generate", lambda *a: [MUTANT])
    monkeypatch.setattr(cli.runner, "baseline_green", lambda *a: 1.0)
    monkeypatch.setattr(cli.runner, "rerun_unmutated", lambda *a: None)
    monkeypatch.setattr(cli, "_emit", lambda line="": None)
    selected: list[list[str]] = []

    def fake_classify(_repo, mutant, tests, _cmd, _timeout):
        selected.append(tests)
        return runner.Result(mutant, runner.KILLED, tests)

    monkeypatch.setattr(cli.runner, "classify", fake_classify)
    cli._gate_file(repo, "src/x.py", {1}, [])
    assert selected == [["t.py::test[a|b]"]]
