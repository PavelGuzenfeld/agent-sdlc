"""Intent: dotfiles#100 — decision 5 of #93 as a hook. A repo that opts in with
`no_comments = true` is blocked by a comment the diff added; a comment that was
already in the file is invisible even when the code beside it changed; pragmas,
shebangs and license headers do not count; docstrings never do.

Driven through cli.main. The test image carries no git, so the two seams that
read it — discover and the diff / pre-image — are stubbed; the config load, the
ast-grep parse, the waiver match and the exit code are real."""

import subprocess
from pathlib import Path

import pytest

from mutation_gate import cli, mutants, no_comments, runner, token
from mutation_gate.repo import Config, GateError, Repo
from mutation_gate.waivers import Waiver, finding_waived

OPTED_IN = "no_comments = true\n"
FILE = "tests/test_a.py"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _repo(tmp_path: Path, toml: str, files: dict[str, str]) -> Repo:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    _write(root, ".mutation-gate.toml", toml)
    for rel, text in files.items():
        _write(root, rel, text)
    return Repo(root=root, origin="", remotes=(), config=Config.load(root))


def _stub_git(monkeypatch, pre: dict[str, str]) -> None:
    def fake_git(*args: str, cwd=None) -> str:
        rel = args[-1].split(":", 1)[1]
        if rel not in pre:
            raise GateError(f"git show: path {rel!r} does not exist")
        return pre[rel]

    monkeypatch.setattr(no_comments, "git", fake_git)


def _gate(monkeypatch, tmp_path: Path, repo: Repo, added: dict[str, set[int]],
          pre: dict[str, str]) -> int:
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(mutants, "changed_lines", lambda root, staged: added)
    _stub_git(monkeypatch, pre)
    for mod in (cli, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")
    return cli.main(["--staged", "--no-adversary"])


def _stub_comment_scan(monkeypatch, returncode: int, stderr: str = "", stdout: str = "") -> None:
    """Only the comment-kind scan is faked; `ast-grep --version` stays real."""
    real_run = mutants.subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["ast-grep", "run"] and cmd[cmd.index("--kind") + 1] == "comment":
            return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(mutants.subprocess, "run", fake_run)


def test_added_comment_line_blocks_and_names_the_line(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {FILE: "x = 1  # one\n"})
    code = _gate(monkeypatch, tmp_path, repo, {FILE: {1}}, {})
    err = capsys.readouterr().err
    assert code == 1
    assert f"{FILE}:1" in err
    assert "# one" in err


def test_crashed_ast_grep_scan_refuses_instead_of_passing_silently(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {FILE: "x = 1\n"})
    _stub_comment_scan(monkeypatch, returncode=8, stderr="Error: crashed parser\nHelp: retry",
                       stdout="[]")
    code = _gate(monkeypatch, tmp_path, repo, {FILE: {1}}, {})
    err = capsys.readouterr().err
    assert code == 2
    assert err.count("\n") == 1
    assert "crashed parser" in err


def test_genuine_no_match_from_ast_grep_still_passes(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {FILE: "x = 1\n"})
    _stub_comment_scan(monkeypatch, returncode=1, stderr="")
    assert _gate(monkeypatch, tmp_path, repo, {FILE: {1}}, {}) == 0


def test_pragma_comment_is_not_flagged(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {FILE: "x = 1  # pyright: ignore[reportUnusedVariable]\n"})
    assert _gate(monkeypatch, tmp_path, repo, {FILE: {1}}, {}) == 0


def test_no_comments_absent_by_default(tmp_path, monkeypatch):
    repo = _repo(tmp_path, "", {FILE: "x = 1  # one\n"})
    assert repo.config.no_comments is False
    assert _gate(monkeypatch, tmp_path, repo, {FILE: {1}}, {}) == 0


def test_preexisting_comment_on_an_edited_line_is_invisible(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {FILE: "x = 2  # one\n"})
    pre = {FILE: "x = 1  # one\n"}
    assert _gate(monkeypatch, tmp_path, repo, {FILE: {1}}, pre) == 0


def test_waiver_keyed_on_check_file_and_line_clears_the_finding(tmp_path, monkeypatch):
    waivers_toml = (f'[[waiver]]\ncheck = "no-comments"\nfile = "{FILE}"\nline = 1\n'
                    'reason = "the fixture line under test is itself a comment"\n')
    repo = _repo(tmp_path, OPTED_IN,
                 {FILE: "x = 1  # one\n", ".mutation-gate-waivers.toml": waivers_toml})
    assert _gate(monkeypatch, tmp_path, repo, {FILE: {1}}, {}) == 0


def _findings(monkeypatch, repo: Repo, rel: str, lines: set[int], wvs=(),
              pre: str | None = None) -> list[str]:
    _stub_git(monkeypatch, {} if pre is None else {rel: pre})
    found = no_comments.check(repo, {rel: lines}, list(wvs), staged=True)
    return [f"{f.file}:{f.line}" for f in found]


def test_cpp_block_comment_reaching_an_added_line_blocks_once(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"src/a.cpp": "int x = 1;\n/* two\n   lines */\nint y = 2;\n"})
    assert _findings(monkeypatch, repo, "src/a.cpp", {3}) == ["src/a.cpp:3"]


def test_docstring_is_not_a_comment(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": 'def f():\n    """Added prose."""\n    return 1\n'})
    assert _findings(monkeypatch, repo, "pkg/a.py", {2}) == []


@pytest.mark.parametrize("text", [
    "#!/usr/bin/env python3\n",
    "# SPDX-License-Identifier: MIT\n",
    "# Copyright 2026 Someone\n",
    "x = 1  # noqa: E501\n",
    "x: int = 1  # type: ignore\n",
    "# ruff: noqa\n",
])
def test_shebang_license_and_pragma_lines_are_carved_out(tmp_path, monkeypatch, text):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": text})
    assert _findings(monkeypatch, repo, "pkg/a.py", {1}) == []


@pytest.mark.parametrize("text", ["int x = 1;  // NOLINT(readability)\n", "// clang-format off\n"])
def test_cpp_pragmas_are_carved_out(tmp_path, monkeypatch, text):
    repo = _repo(tmp_path, OPTED_IN, {"src/a.cpp": text})
    assert _findings(monkeypatch, repo, "src/a.cpp", {1}) == []


def test_prose_comment_in_cpp_blocks(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"src/a.cpp": "int x = 1;  // one\n"})
    assert _findings(monkeypatch, repo, "src/a.cpp", {1}) == ["src/a.cpp:1"]


def test_excluded_path_is_not_inspected(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN + 'exclude_paths = ["third_party/"]\n',
                 {"third_party/v.py": "x = 1  # vendored\n"})
    assert _findings(monkeypatch, repo, "third_party/v.py", {1}) == []


def test_excluded_file_does_not_hide_the_file_after_it(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN + 'exclude_paths = ["a_vendored/"]\n',
                 {"a_vendored/v.py": "x = 1  # vendored\n", "pkg/a.py": "y = 1  # one\n"})
    _stub_git(monkeypatch, {})
    found = no_comments.check(repo, {"a_vendored/v.py": {1}, "pkg/a.py": {1}}, [], staged=True)
    assert [(f.file, f.line) for f in found] == [("pkg/a.py", 1)]


def test_comment_moved_to_another_line_is_still_the_old_comment(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "import os\n# kept\nx = 1\n"})
    assert _findings(monkeypatch, repo, "pkg/a.py", {1, 2}, pre="# kept\nx = 1\n") == []


def test_comment_on_the_line_below_a_changed_line_is_not_touched(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "x = 1\n# two\n"})
    assert _findings(monkeypatch, repo, "pkg/a.py", {1}) == []


def test_two_edited_lines_each_keep_their_own_old_comment(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "y = 1  # a\nz = 2  # a\n"})
    assert _findings(monkeypatch, repo, "pkg/a.py", {1, 2}, pre="x = 1  # a\nx = 2  # a\n") == []


def test_comment_on_the_line_above_a_changed_line_is_not_touched(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "# one\nx = 1\n"})
    assert _findings(monkeypatch, repo, "pkg/a.py", {2}) == []


def test_new_comment_after_a_kept_one_is_still_new(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "x = 2  # one\ny = 1  # two\n"})
    assert _findings(monkeypatch, repo, "pkg/a.py", {1, 2}, pre="x = 1  # one\n") == ["pkg/a.py:2"]


def test_pragma_before_a_prose_comment_does_not_hide_it(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "x = 1  # noqa\ny = 2  # two\n"})
    assert _findings(monkeypatch, repo, "pkg/a.py", {1, 2}) == ["pkg/a.py:2"]


def test_second_copy_of_an_existing_comment_is_new(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "# kept\nx = 1\n# kept\n"})
    assert _findings(monkeypatch, repo, "pkg/a.py", {3}, pre="# kept\nx = 1\n") == ["pkg/a.py:3"]


def test_waiver_on_another_line_does_not_cover_this_one(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "x = 1  # one\ny = 2  # two\n"})
    waiver = Waiver(check="no-comments", file="pkg/a.py", line=1, reason="fixture")
    assert _findings(monkeypatch, repo, "pkg/a.py", {1, 2}, [waiver]) == ["pkg/a.py:2"]


def test_line_scoped_waiver_does_not_cover_a_finding_that_carries_no_line():
    waiver = Waiver(check="no-citation", file="tests/test_imm.py", line=1, reason="fixture")
    assert finding_waived([waiver], "no-citation", "tests/test_imm.py") is None
