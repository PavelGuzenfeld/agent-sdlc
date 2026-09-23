"""Intent: #71 decision 10 — `mutation-gate no-new-docs` blocks a newly added
`.md` file that matches neither the built-in allowlist, `.md` under
test_paths, nor a repo's own `doc_allow = [{glob, reason}]`. Editing an
existing `.md` file is never "added", so it always passes. `git` is stubbed —
the gate's test image has none."""

from pathlib import Path

import pytest

from mutation_gate import cli, no_new_docs
from mutation_gate.repo import Config, DocAllow, GateError, Repo


def _added(paths: list[str]) -> str:
    return "".join(f"{p}\0" for p in paths)


def _stub_git(monkeypatch, *, added: str = ""):
    calls: list[tuple[str, ...]] = []

    def fake_git(*args: str, cwd=None) -> str:
        calls.append(args)
        if args[0] == "diff":
            return added
        raise AssertionError(f"unexpected git call {args}")

    monkeypatch.setattr(no_new_docs, "git", fake_git)
    return calls


def _repo(tmp_path: Path, config: Config | None = None) -> Repo:
    return Repo(root=tmp_path, origin="", remotes=(), config=config or Config())


def _local(monkeypatch, tmp_path: Path, config: Config | None = None) -> int:
    monkeypatch.setattr(no_new_docs, "discover", lambda: _repo(tmp_path, config))
    return cli.main(["no-new-docs"])


def _range(monkeypatch, tmp_path: Path, config: Config | None = None) -> int:
    monkeypatch.setattr(no_new_docs, "discover", lambda: _repo(tmp_path, config))
    return cli.main(["no-new-docs", "--range", "base..HEAD"])


def test_an_unlisted_new_md_file_is_blocked(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, added=_added(["design.md"]))
    assert _local(monkeypatch, tmp_path) == 1
    err = capsys.readouterr().err
    assert "1 new .md file(s)" in err
    assert "design.md" in err
    assert "doc_allow" in err


def test_no_added_md_files_passes(monkeypatch, tmp_path):
    _stub_git(monkeypatch, added="")
    assert _local(monkeypatch, tmp_path) == 0


def test_an_added_non_md_file_is_ignored(monkeypatch, tmp_path):
    _stub_git(monkeypatch, added=_added(["design.txt"]))
    assert _local(monkeypatch, tmp_path) == 0


@pytest.mark.parametrize("name", [
    "README.md", "LICENSE.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
    "SECURITY.md", "NOTICE.md", "CHANGELOG.md", "AGENTS.md",
])
def test_default_allowlist_root_files_pass(monkeypatch, tmp_path, name):
    (tmp_path / name).write_text("x")
    _stub_git(monkeypatch, added=_added([name]))
    assert _local(monkeypatch, tmp_path) == 0


def test_a_file_under_dot_github_passes_a_sibling_dot_dir_is_still_blocked(monkeypatch, tmp_path, capsys):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "x.md").write_text("x")
    (tmp_path / ".gitlab").mkdir()
    (tmp_path / ".gitlab" / "y.md").write_text("x")
    _stub_git(monkeypatch, added=_added([".github/x.md", ".gitlab/y.md"]))
    assert _local(monkeypatch, tmp_path) == 1
    err = capsys.readouterr().err
    assert ".gitlab/y.md" in err
    assert ".github/x.md" not in err


def test_a_synced_rule_under_dot_claude_rules_passes(monkeypatch, tmp_path):
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "voice.md").write_text("x")
    _stub_git(monkeypatch, added=_added([".claude/rules/voice.md"]))
    assert _local(monkeypatch, tmp_path) == 0


def test_a_file_under_test_paths_passes_a_sibling_outside_it_is_blocked(monkeypatch, tmp_path, capsys):
    config = Config(test_paths=["tests/notes"])
    _stub_git(monkeypatch, added=_added(["tests/notes/readme.md", "other.md"]))
    assert _local(monkeypatch, tmp_path, config=config) == 1
    err = capsys.readouterr().err
    assert "other.md" in err
    assert "tests/notes/readme.md" not in err


def test_a_doc_allow_glob_blocks_without_config(monkeypatch, tmp_path, capsys):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "y.md").write_text("x")
    _stub_git(monkeypatch, added=_added(["docs/y.md"]))
    assert _local(monkeypatch, tmp_path) == 1
    assert "docs/y.md" in capsys.readouterr().err


def test_a_doc_allow_glob_passes_a_sibling_outside_the_glob_is_still_blocked(monkeypatch, tmp_path, capsys):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "y.md").write_text("x")
    (tmp_path / "notes.md").write_text("x")
    config = Config(doc_allow=[DocAllow(glob="docs/**/*", reason="design notes")])
    _stub_git(monkeypatch, added=_added(["docs/y.md", "notes.md"]))
    assert _local(monkeypatch, tmp_path, config=config) == 1
    err = capsys.readouterr().err
    assert "notes.md" in err
    assert "docs/y.md" not in err


def test_multiple_blocked_files_are_all_reported(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, added=_added(["design.md", "notes.md"]))
    assert _local(monkeypatch, tmp_path) == 1
    err = capsys.readouterr().err
    assert "2 new .md file(s)" in err
    assert "design.md" in err
    assert "notes.md" in err


def test_local_form_diffs_only_the_staged_added_files(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch)
    _local(monkeypatch, tmp_path)
    assert calls == [("diff", "--name-only", "-z", "--no-renames", "--diff-filter=A", "--cached")]


def test_range_form_diffs_only_the_added_files_in_the_given_range(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch)
    _range(monkeypatch, tmp_path)
    assert calls == [("diff", "--name-only", "-z", "--no-renames", "--diff-filter=A", "base..HEAD")]


def test_range_form_blocks_the_same_way_as_local(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, added=_added(["design.md"]))
    assert _range(monkeypatch, tmp_path) == 1
    assert "design.md" in capsys.readouterr().err


def test_a_failing_diff_refuses(monkeypatch, tmp_path):
    def boom(*args, cwd=None):
        raise GateError("git diff: fatal")

    monkeypatch.setattr(no_new_docs, "git", boom)
    assert _local(monkeypatch, tmp_path) == 2


_DOC_ALLOW_ERROR = r"every \[\[doc_allow\]\] needs `glob` and a `reason`"


def test_doc_allow_with_reason_loads(tmp_path):
    (tmp_path / ".mutation-gate.toml").write_text(
        '[[doc_allow]]\nglob = "docs/**/*"\nreason = "design notes"\n'
    )
    cfg = Config.load(tmp_path)
    assert cfg.doc_allow == [DocAllow(glob="docs/**/*", reason="design notes")]


def test_doc_allow_without_reason_is_refused(tmp_path):
    (tmp_path / ".mutation-gate.toml").write_text('[[doc_allow]]\nglob = "docs/**/*"\n')
    with pytest.raises(GateError, match=_DOC_ALLOW_ERROR):
        Config.load(tmp_path)


def test_doc_allow_with_an_empty_reason_is_refused(tmp_path):
    (tmp_path / ".mutation-gate.toml").write_text(
        '[[doc_allow]]\nglob = "docs/**/*"\nreason = ""\n'
    )
    with pytest.raises(GateError, match=_DOC_ALLOW_ERROR):
        Config.load(tmp_path)


def test_doc_allow_without_glob_is_refused(tmp_path):
    (tmp_path / ".mutation-gate.toml").write_text('[[doc_allow]]\nreason = "design notes"\n')
    with pytest.raises(GateError, match=_DOC_ALLOW_ERROR):
        Config.load(tmp_path)


def test_hook_refuses_loudly_on_a_reasonless_doc_allow_entry(monkeypatch, tmp_path, capsys):
    (tmp_path / ".mutation-gate.toml").write_text('[[doc_allow]]\nglob = "docs/**/*"\n')
    _stub_git(monkeypatch, added=_added(["design.md"]))
    monkeypatch.setattr(
        no_new_docs, "discover",
        lambda: Repo(root=tmp_path, origin="", remotes=(), config=Config.load(tmp_path)),
    )
    assert cli.main(["no-new-docs"]) == 2
    err = capsys.readouterr().err
    assert "no-new-docs refused" in err
    assert "reason" in err


def test_this_repos_own_doc_allow_covers_docs_skills_commands_rules_with_reasons():
    root = Path(__file__).resolve().parents[2]
    cfg = Config.load(root)
    globs = [a.glob for a in cfg.doc_allow]
    for prefix in ("docs", "skills", "commands", "rules"):
        assert any(g.startswith(f"{prefix}/") for g in globs), prefix
    assert all(a.reason for a in cfg.doc_allow)
