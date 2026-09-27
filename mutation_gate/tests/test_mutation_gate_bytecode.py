"""Intent: #322 — Python trusts a cached .pyc while the source's whole-second
mtime and size are unchanged. A same-size mutant restored within the second left
bytecode that kept running the mutant after the gate put the original back."""

import importlib.util
import os
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest

from mutation_gate import runner
from mutation_gate.mutants import Mutant
from mutation_gate.repo import Config, Repo

ORIGINAL = "def is_adult(age):\n    return age >= 18\n"
SAME_SIZE_MUTANT = ORIGINAL.replace("18", "19")
TESTS = (
    "from age import is_adult\n\n\n"
    "def test_eighteen_is_the_first_adult_age():\n"
    "    assert is_adult(18)\n"
    "    assert not is_adult(17)\n"
)
PYTEST = f"{sys.executable} -m pytest -q -p no:cacheprovider {{tests}}"


@pytest.fixture
def gated(tmp_path, monkeypatch):
    for var in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(runner, "CACHE_ROOT", tmp_path / "cache")
    (tmp_path / "age.py").write_text(ORIGINAL)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_age.py").write_text(TESTS)
    (tmp_path / "conftest.py").write_text("")
    return Repo(root=tmp_path, origin="", remotes=(), config=Config())


def users_own_pytest(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        PYTEST.format(tests="tests").split(), cwd=root, capture_output=True, text=True,
    )


def same_size_mutant() -> Mutant:
    start = ORIGINAL.index("18")
    return Mutant(file="age.py", start=start, end=start + 2, line=2, old="18", new="19", kind="int")


def test_the_users_own_tests_pass_against_the_restored_file_after_a_same_size_mutant(gated):
    result = runner.classify(gated, same_size_mutant(), ["tests"], PYTEST)

    assert result.verdict == runner.KILLED
    assert (gated.root / "age.py").read_text() == ORIGINAL
    assert not list(gated.root.rglob("*.pyc"))
    run = users_own_pytest(gated.root)
    assert run.returncode == 0, run.stdout


def test_a_stale_pyc_matching_the_sources_mtime_and_size_does_not_fail_the_baseline(gated):
    source = gated.root / "age.py"
    source.write_text(SAME_SIZE_MUTANT)
    subprocess.run([sys.executable, "-c", "import age"], cwd=gated.root, check=True)
    stamp = source.stat().st_mtime_ns
    source.write_text(ORIGINAL)
    os.utime(source, ns=(stamp, stamp))

    runner.baseline_green(gated, ["tests"], PYTEST)


def test_a_mutant_run_never_loads_bytecode_the_repo_cached_for_the_original(gated):
    """An unchecked-hash .pyc is trusted whatever the source's mtime, so it stands
    in deterministically for an original .pyc whose stamp the mutant happens to match."""
    py_compile.compile(
        str(gated.root / "age.py"), cfile=importlib.util.cache_from_source(str(gated.root / "age.py")),
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )

    result = runner.classify(gated, same_size_mutant(), ["tests"], PYTEST)

    assert result.verdict == runner.KILLED
