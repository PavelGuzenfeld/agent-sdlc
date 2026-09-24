"""Intent: #159 — mutants.changed_lines ran an unpinned `git diff -U0
--no-color` and only recognized `+++ b/` headers. diff.noprefix or
diff.mnemonicPrefix reshapes that header and silently dropped the file's
changed lines, so the gate mutated nothing there and no_comments (the same
fail-open class #151 fixed in no-leaks) scanned nothing there. Pin the diff
invocation with repo.DIFF_PREFIX_PIN_ARGS and parse with repo.post_image_path,
the helper no-leaks shares. `git` is stubbed; the test image carries no git
binary."""

import contextlib

import pytest

from mutation_gate import cli, mutants
from mutation_gate.repo import Config, DIFF_PREFIX_PIN_ARGS, GateError, Repo


def _stub_git(monkeypatch, diff: str):
    calls: list[tuple[str, ...]] = []

    def fake_git(*args: str, cwd=None) -> str:
        calls.append(args)
        return diff

    monkeypatch.setattr(mutants, "git", fake_git)
    return calls


def _diff(path: str, *lines: str, start: int = 1) -> str:
    body = "".join(f"+{line}\n" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +{start},{len(lines)} @@\n"
        f"{body}"
    )


def test_the_diff_invocation_is_pinned_against_diff_prefix_config(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch, diff="")
    mutants.changed_lines(tmp_path, staged=True)
    assert ("diff", "-U0", "--no-color", *DIFF_PREFIX_PIN_ARGS, "--cached") in calls


def test_a_multi_line_hunk_attributes_every_added_line(monkeypatch, tmp_path):
    _stub_git(monkeypatch, diff=_diff("fixture.py", "x = 1", "y = 2", start=5))
    assert mutants.changed_lines(tmp_path, staged=True) == {"fixture.py": {5, 6}}


def test_a_hunk_with_no_explicit_count_defaults_to_one_line(monkeypatch, tmp_path):
    diff = (
        "diff --git a/fixture.py b/fixture.py\n"
        "--- a/fixture.py\n"
        "+++ b/fixture.py\n"
        "@@ -0,0 +3 @@\n"
        "+x = 1\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert mutants.changed_lines(tmp_path, staged=True) == {"fixture.py": {3}}


def test_a_pure_deletion_hunk_leaves_the_file_out_of_the_result(monkeypatch, tmp_path):
    diff = (
        "diff --git a/fixture.py b/fixture.py\n"
        "--- a/fixture.py\n"
        "+++ b/fixture.py\n"
        "@@ -3,1 +2,0 @@\n"
        "-x = 1\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert mutants.changed_lines(tmp_path, staged=True) == {}


def test_a_dev_null_post_image_for_a_deleted_file_is_not_attributed(monkeypatch, tmp_path):
    diff = (
        "diff --git a/fixture.py b/fixture.py\n"
        "--- a/fixture.py\n"
        "+++ /dev/null\n"
        "@@ -1,1 +0,0 @@\n"
        "-x = 1\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert mutants.changed_lines(tmp_path, staged=True) == {}


def test_an_added_line_shaped_like_a_post_image_header_inside_a_hunk_is_not_mistaken_for_one(
    monkeypatch, tmp_path
):
    diff = (
        "diff --git a/fixture.py b/fixture.py\n"
        "--- a/fixture.py\n"
        "+++ b/fixture.py\n"
        "@@ -0,0 +1,1 @@\n"
        "++ b/spoof.py\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert mutants.changed_lines(tmp_path, staged=True) == {"fixture.py": {1}}


def test_a_staged_change_still_yields_the_right_changed_lines_once_pinned(monkeypatch, tmp_path):
    _stub_git(monkeypatch, diff=_diff("fixture.py", "x = 1"))
    assert mutants.changed_lines(tmp_path, staged=False) == {"fixture.py": {1}}


def test_an_unparseable_post_image_header_refuses(monkeypatch, tmp_path):
    diff = (
        "diff --git a/fixture.py b/fixture.py\n"
        "--- fixture.py\n"
        "+++ fixture.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+x = 1\n"
    )
    _stub_git(monkeypatch, diff=diff)
    with pytest.raises(GateError):
        mutants.changed_lines(tmp_path, staged=True)


def test_staged_refuses_cleanly_through_the_cli_when_the_header_is_unparseable(
    tmp_path, monkeypatch, capsys
):
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    diff = (
        "diff --git a/fixture.py b/fixture.py\n"
        "--- fixture.py\n"
        "+++ fixture.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+x = 1\n"
    )
    _stub_git(monkeypatch, diff)
    assert cli.main(["--staged"]) == 2
    assert "refused" in capsys.readouterr().err
