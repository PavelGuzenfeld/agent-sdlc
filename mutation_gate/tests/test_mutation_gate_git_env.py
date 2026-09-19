"""Intent: flowdiff#81 and flowdiff#83 — git exports GIT_DIR, GIT_INDEX_FILE and
GIT_WORK_TREE into every hook it runs, and they override `-C`. The gate runs a
repo's test command from a pre-commit hook, so a suite that builds a throwaway
repo staged into the commit being gated: the gated run could alter what it was
gating, and the suite failed for a reason that read as a broken suite.

The gate's own git calls keep the inherited environment on purpose -- under a
hook GIT_INDEX_FILE is the index being committed, which is what --staged reads.
Only the repo's own command is scrubbed."""

import subprocess
from pathlib import Path

from mutation_gate import repo as repo_mod
from mutation_gate import runner
from mutation_gate.repo import Config, Repo


def gated(tmp_path: Path) -> Repo:
    return Repo(root=tmp_path, origin="", remotes=(), config=Config(pass_pattern="ok"))


def test_a_test_command_does_not_inherit_the_index_of_the_commit_being_gated(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / ".git" / "index.lock"))
    verdict = runner.run_capped(gated(tmp_path), 'test -z "$GIT_INDEX_FILE" && echo ok')
    assert verdict == runner.PASSED


def test_a_test_command_does_not_inherit_the_repo_being_gated(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_DIR", str(tmp_path / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path))
    verdict = runner.run_capped(gated(tmp_path), 'test -z "$GIT_DIR$GIT_WORK_TREE" && echo ok')
    assert verdict == runner.PASSED


def test_the_rest_of_the_environment_still_reaches_the_test_command(tmp_path, monkeypatch):
    # Scrubbing every GIT_* would drop GIT_AUTHOR_NAME; dropping PATH would stop
    # the command being findable at all.
    monkeypatch.setenv("GATE_CANARY", "kept")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "kept too")
    verdict = runner.run_capped(
        gated(tmp_path),
        'test "$GATE_CANARY" = kept && test "$GIT_AUTHOR_NAME" = "kept too" && test -n "$PATH" && echo ok',
    )
    assert verdict == runner.PASSED


def test_the_gates_own_git_keeps_the_environment_the_hook_gave_it(monkeypatch):
    """The other half of the invariant: --staged has to read the index being
    committed, which under a hook is the one GIT_INDEX_FILE names. Scrubbing here
    would quietly gate .git/index instead, a different set of changes."""
    seen: dict = {}
    monkeypatch.setattr(
        repo_mod.subprocess, "run",
        lambda cmd, **kw: seen.update(kw) or subprocess.CompletedProcess(cmd, 0, "", ""),
    )

    repo_mod.git("rev-parse", "--show-toplevel")

    assert seen.get("env") is None
