"""Intent: dotfiles#61 — a lock held by a concurrent run must skip the Stop
hook (--worktree), not refuse it; --staged has no fallback and still refuses.
dotfiles#62 — a report a green pre-commit hook would swallow must still land
on disk. dotfiles#68 item 1 — the Stop hook's process cwd is the session's
launch directory, not wherever a Bash `cd` took the shell; --worktree must
read the real one from the hook's JSON payload on stdin, and --staged must
never touch stdin at all."""

import json
import sys
from pathlib import Path

from mutation_gate import cli
from mutation_gate.repo import Config, GateError, Repo


def _repo(tmp_path: Path) -> Repo:
    return Repo(root=tmp_path, origin="", remotes=(), config=Config())


def _locked(repo):
    raise GateError(f"another mutation-gate is running in {repo.root.name}")


def _discover_spy(tmp_path, seen):
    def _discover(cwd=None):
        seen["cwd"] = cwd
        return _repo(tmp_path)
    return _discover


def test_worktree_skips_instead_of_refusing_when_the_repo_is_locked(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", _locked)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert cli.main(["--worktree"]) == 0


def test_staged_still_refuses_when_the_repo_is_locked(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", _locked)
    assert cli.main(["--staged"]) == 2


def test_worktree_reads_cwd_from_the_hook_stdin_json(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "discover", _discover_spy(tmp_path, seen))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: "stop here")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdin, "read", lambda: json.dumps({"cwd": str(tmp_path / "sub")}))
    assert cli.main(["--worktree"]) == 0
    assert seen["cwd"] == Path(tmp_path / "sub")


def test_worktree_falls_back_to_process_cwd_when_stdin_is_a_tty(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "discover", _discover_spy(tmp_path, seen))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: "stop here")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert cli.main(["--worktree"]) == 0
    assert seen["cwd"] is None


def test_staged_never_reads_stdin_for_a_cwd(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "discover", _discover_spy(tmp_path, seen))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: "stop here")

    def _boom():
        raise AssertionError("staged mode must not read stdin")

    monkeypatch.setattr(sys.stdin, "isatty", _boom)
    assert cli.main(["--staged"]) == 0
    assert seen["cwd"] is None


def test_write_report_saves_to_cache_root_keyed_by_repo(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(cli, "CACHE_ROOT", cache)
    repo = _repo(tmp_path / "repo")
    path = cli._write_report(repo, "adversary", "findings text\n")
    assert path == cache / repo.key / "reports" / "adversary.md"
    assert path.read_text() == "findings text\n"
