"""Intent: #451 — a mutant run that exits non-zero without any test failing
(pytest internal or usage error, no tests collected) is the environment dying.
Scoring it KILLED hides a survivor, so the gate refuses like a bad baseline."""

import sys

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

    def _run(exit_code: int, prelude: str = "") -> runner.Result:
        command = f"{prelude}exit {exit_code}; echo {{tests}}"
        return runner.classify(repo, MUTANT, ["t.py"], command, 30.0)

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


GPU_OUT_OF_MEMORY = "printf 'torch.OutOfMemoryError: CUDA out of memory\\n'; "
NO_DOCKER_DAEMON = "printf 'Cannot connect to the Docker daemon at unix:///x.sock\\n'; "
NO_DOCKER_API = (
    "printf 'failed to connect to the docker API at unix:///nonexistent; check if the path is"
    " correct and if the daemon is running: dial unix /nonexistent: connect: no such file or directory\\n'; "
)
NO_DOCKER_API_FOR_BUILD = NO_DOCKER_API.replace("printf '", "printf 'ERROR: ")
NO_DOCKER_API_ON_STDERR = NO_DOCKER_API.replace("\\n'; ", "\\n' >&2; ")


@pytest.mark.parametrize(
    "prelude, cause",
    [
        (GPU_OUT_OF_MEMORY, "reported a GPU out-of-memory error and exited 1"),
        (NO_DOCKER_DAEMON, "reported no reachable docker daemon and exited 1"),
        (NO_DOCKER_API, "reported no reachable docker daemon and exited 1"),
        (NO_DOCKER_API_FOR_BUILD, "reported no reachable docker daemon and exited 1"),
        (NO_DOCKER_API_ON_STDERR, "reported no reachable docker daemon and exited 1"),
    ],
    ids=["gpu", "docker", "docker-api", "docker-build", "docker-api-stderr"],
)
def test_a_failed_run_that_printed_an_environment_fault_blocks_naming_it(
    run_mutant, prelude, cause
):
    with pytest.raises(repo_mod.GateError, match=cause):
        run_mutant(1, prelude)


@pytest.mark.parametrize(
    "exit_code, prelude, cause",
    [(137, "", r"SIGKILL \(exit 137\)"), (0, "kill -9 $$; ", r"SIGKILL \(exit -9\)")],
    ids=["137", "-9"],
)
def test_a_run_ended_by_sigkill_blocks_instead_of_counting_as_killed(
    run_mutant, exit_code, prelude, cause
):
    with pytest.raises(repo_mod.GateError, match=cause):
        run_mutant(exit_code, prelude)


def test_a_run_that_hit_a_gpu_out_of_memory_at_collection_blocks(run_mutant):
    prelude = "printf 'ERROR collecting t.py\\nE   RuntimeError: CUDA out of memory. Tried\\n'; "
    with pytest.raises(repo_mod.GateError, match="reported a GPU out-of-memory error and exited 2"):
        run_mutant(2, prelude)


def test_a_run_that_exits_143_is_still_killed(run_mutant):
    assert run_mutant(143).verdict == runner.KILLED


def test_a_mutant_that_breaks_an_import_is_still_killed(run_mutant):
    prelude = "printf 'E   ModuleNotFoundError: No module named x\\n'; "
    assert run_mutant(2, prelude).verdict == runner.KILLED


def test_a_mutant_that_raises_memory_error_is_still_killed(run_mutant):
    assert run_mutant(1, "printf 'E   MemoryError\\n'; ").verdict == runner.KILLED


def test_a_passing_run_that_printed_an_environment_fault_still_survives(run_mutant):
    assert run_mutant(0, GPU_OUT_OF_MEMORY).verdict == runner.SURVIVED


def test_an_environment_fault_leaves_the_source_unmutated(run_mutant, tmp_path):
    with pytest.raises(repo_mod.GateError):
        run_mutant(1, GPU_OUT_OF_MEMORY)
    assert (tmp_path / "src" / "x.py").read_text() == "a"


ECHOING_TESTS = """
def fallback(message):
    return False

def check(message):
    assert message == "x"

def test_echoes_the_marker_in_source():
    assert fallback("CUDA out of memory")

def test_echoes_the_marker_in_a_frame_argument():
    check("CUDA out of memory")

def test_echoes_the_docker_marker_in_a_frame_argument():
    check("Cannot connect to the Docker daemon")

def test_echoes_the_docker_api_marker_in_a_frame_argument():
    check("failed to connect to the docker API")

def test_echoes_the_marker_in_diff_context():
    assert "a\\nCUDA out of memory" == "b\\nCUDA out of memory"
"""

RAISING_TEST = """
def allocate(message):
    raise RuntimeError(message + ". Tried to allocate 2 MiB")

def test_raises_the_marker():
    allocate("CUDA out of memory")
"""


PRINTING_TEST = """
def test_prints_the_marker_then_fails():
    print("CUDA out of memory")
    assert 1 == 2
"""

LONG_ID_RAISING_TEST = RAISING_TEST.replace(
    "test_raises_the_marker", "test_raises_the_marker" + "_from_a_test_with_a_long_name" * 3
)


@pytest.fixture
def run_pytest(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CACHE_ROOT", tmp_path / "cache")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("a")
    repo = repo_mod.Repo(root=tmp_path, origin="", remotes=(), config=repo_mod.Config())

    def _run(test_source: str, traceback_style: str, color: str = "no") -> runner.Result:
        (tmp_path / "test_t.py").write_text(test_source)
        command = (
            f"{sys.executable} -m pytest -q -p no:cacheprovider --color={color}"
            f" --tb={traceback_style} {{tests}}"
        )
        return runner.classify(repo, MUTANT, ["test_t.py"], command, 60.0)

    return _run


@pytest.mark.parametrize("traceback_style", ["auto", "short", "line", "native", "no"])
def test_a_marker_only_in_echoed_test_code_is_still_killed(run_pytest, traceback_style):
    assert run_pytest(ECHOING_TESTS, traceback_style).verdict == runner.KILLED


@pytest.mark.parametrize("traceback_style", ["auto", "short", "line", "native", "no"])
def test_a_marker_in_the_raised_error_blocks(run_pytest, traceback_style):
    with pytest.raises(repo_mod.GateError, match="reported a GPU out-of-memory error and exited 1"):
        run_pytest(RAISING_TEST, traceback_style)


@pytest.mark.parametrize("traceback_style", ["auto", "short", "line", "native", "no"])
def test_a_marker_printed_bare_in_captured_stdout_is_still_killed(run_pytest, traceback_style):
    assert run_pytest(PRINTING_TEST, traceback_style).verdict == runner.KILLED


@pytest.mark.parametrize("traceback_style", ["auto", "short", "line", "native", "no"])
def test_a_marker_in_the_raised_error_blocks_under_color(run_pytest, traceback_style):
    with pytest.raises(repo_mod.GateError, match="reported a GPU out-of-memory error and exited 1"):
        run_pytest(RAISING_TEST, traceback_style, color="yes")


@pytest.mark.parametrize("traceback_style", ["auto", "short", "line", "native", "no"])
def test_a_marker_only_in_echoed_test_code_is_still_killed_under_color(run_pytest, traceback_style):
    assert run_pytest(ECHOING_TESTS, traceback_style, color="yes").verdict == runner.KILLED


def test_a_marker_raised_by_a_long_test_id_under_tb_no_blocks_outside_ci(run_pytest, monkeypatch):
    for name in ("COLUMNS", "CI", "BUILD_NUMBER"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(repo_mod.GateError, match="reported a GPU out-of-memory error and exited 1"):
        run_pytest(LONG_ID_RAISING_TEST, "no")


def test_a_marker_raised_at_collection_under_tb_no_blocks(run_pytest):
    with pytest.raises(repo_mod.GateError, match="reported a GPU out-of-memory error and exited 2"):
        run_pytest('raise RuntimeError("CUDA out of memory")\n', "no")


def test_a_marker_on_a_raw_traceback_final_line_blocks(tmp_path, run_mutant):
    (tmp_path / "boom.py").write_text('raise RuntimeError("CUDA out of memory")\n')
    with pytest.raises(repo_mod.GateError, match="reported a GPU out-of-memory error and exited 1"):
        run_mutant(1, f"{sys.executable} boom.py; ")


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
