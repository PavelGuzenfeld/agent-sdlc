"""Intent: dotfiles#61 — a lock held by a concurrent run must skip the Stop
hook (--worktree), not refuse it; --staged has no fallback and still refuses.
dotfiles#62 — a report a green pre-commit hook would swallow must still land
on disk. dotfiles#68 item 1 — the Stop hook's process cwd is the session's
launch directory, not wherever a Bash `cd` took the shell; --worktree must
read the real one from the hook's JSON payload on stdin, and --staged must
never touch stdin at all."""

import contextlib
import json
import sys
from pathlib import Path

from mutation_gate import cli
from mutation_gate.repo import Config, GateError, Repo


def _repo(tmp_path: Path) -> Repo:
    return Repo(root=tmp_path, origin="", remotes=(), config=Config())


def _no_ast_grep_on_path(monkeypatch) -> None:
    monkeypatch.setattr(cli.mutants.shutil, "which", lambda name: None)


def _not_a_git_repo(*args, **kwargs):
    raise GateError("fatal: not a git repository")


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


def test_staged_refuses_cleanly_when_ast_grep_is_missing_from_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"foo.py": {1}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    _no_ast_grep_on_path(monkeypatch)
    assert cli.main(["--staged"]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "ast-grep" in err


def test_staged_skips_ast_grep_check_when_no_gated_file_changed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"README.md": {1}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    _no_ast_grep_on_path(monkeypatch)
    assert cli.main(["--staged"]) == 0
    assert "ast-grep" not in capsys.readouterr().err


def test_staged_still_requires_ast_grep_when_a_gated_file_is_mixed_with_a_docs_file(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(
        cli.mutants, "changed_lines", lambda root, staged: {"README.md": {1}, "foo.py": {1}}
    )
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    _no_ast_grep_on_path(monkeypatch)
    assert cli.main(["--staged"]) == 2
    assert "ast-grep" in capsys.readouterr().err


def test_staged_requires_ast_grep_for_no_comments_when_only_a_test_file_changed(
    tmp_path, monkeypatch, capsys
):
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config(no_comments=True))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("x = 1  # one\n")
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(
        cli.mutants, "changed_lines", lambda root, staged: {"tests/test_a.py": {1}}
    )
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    _no_ast_grep_on_path(monkeypatch)
    assert cli.main(["--staged"]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "ast-grep" in err


def test_staged_skips_ast_grep_check_for_no_comments_when_no_gated_file_changed(
    tmp_path, monkeypatch, capsys
):
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config(no_comments=True))
    (tmp_path / "README.md").write_text("hello\n")
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"README.md": {1}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    _no_ast_grep_on_path(monkeypatch)
    assert cli.main(["--staged"]) == 0
    assert "ast-grep" not in capsys.readouterr().err


def test_staged_refuses_cleanly_when_git_is_missing_from_path(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert cli.main(["--staged", "--dry-run"]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "git" in err


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
