"""Intent: dotfiles#79 — repo_lock existed to stop two gates running at once,
but it checked path.exists() and then wrote, which is not atomic. Two gates
starting inside that gap both took the lock and each restored the other's backup
mid-mutant. The symptom was a baseline refusal on a tree whose suite passed."""

import os
from pathlib import Path

import pytest

from mutation_gate import repo as repo_mod, runner


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CACHE_ROOT", tmp_path / "cache")
    return repo_mod.Repo(
        root=tmp_path, origin="", remotes=(), config=repo_mod.Config()
    )


def _lock_path(repo) -> Path:
    return runner.CACHE_ROOT / repo.key / "lock"


def test_a_second_gate_is_refused_while_the_first_holds_the_lock(repo):
    with runner.repo_lock(repo):
        with pytest.raises(repo_mod.GateError, match="concurrent runs corrupt"):
            with runner.repo_lock(repo):
                pass


def test_the_refusal_names_the_pid_holding_the_lock(repo):
    # "pid unknown" sends you to `ps` with nothing to look for.
    with runner.repo_lock(repo):
        with pytest.raises(repo_mod.GateError, match=rf"pid {os.getpid()}\b"):
            with runner.repo_lock(repo):
                pass


def test_a_gate_that_loses_the_race_refuses_instead_of_overwriting_the_winner(
    repo, monkeypatch
):
    """The defect itself. A lock left by a dead holder sends the gate down the
    takeover path; the no-op unlink stands in for another gate re-creating the
    file in that instant. Creation must still fail and refuse. A gate that
    decides with exists() and then writes takes the lock anyway, which is the
    bug — so this is the one test that separates the two."""
    path = _lock_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("999999999")
    monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)

    with pytest.raises(repo_mod.GateError, match="concurrent runs corrupt"):
        with runner.repo_lock(repo):
            pass
    assert path.read_text().strip() == "999999999", "clobbered the other gate's lock"


def test_a_refused_gate_leaves_the_holders_lock_intact(repo):
    with runner.repo_lock(repo):
        with pytest.raises(repo_mod.GateError):
            with runner.repo_lock(repo):
                pass
        assert _lock_path(repo).read_text().strip() == str(os.getpid())
    assert not _lock_path(repo).exists(), "the refusal broke the holder's release"


def test_the_holders_pid_survives_the_claim_so_the_refusal_can_name_it(repo):
    with runner.repo_lock(repo):
        assert _lock_path(repo).read_text().strip() == str(os.getpid())


def test_a_lock_left_by_a_dead_holder_is_taken_over_rather_than_blocking_forever(repo):
    path = _lock_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("999999999")  # no such pid
    with runner.repo_lock(repo):
        assert path.read_text().strip() == str(os.getpid())


def test_an_unreadable_lock_is_treated_as_stale_not_as_a_live_holder(repo):
    path = _lock_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    with runner.repo_lock(repo):
        assert path.read_text().strip() == str(os.getpid())


def test_the_lock_is_released_when_the_gate_finishes(repo):
    with runner.repo_lock(repo):
        pass
    assert not _lock_path(repo).exists()


def test_the_lock_is_released_when_the_gate_raises(repo):
    with pytest.raises(ValueError):
        with runner.repo_lock(repo):
            raise ValueError("the run died mid-mutant")
    assert not _lock_path(repo).exists()
