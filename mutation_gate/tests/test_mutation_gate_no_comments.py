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
from conftest import GDSCRIPT_SGCONFIG, require_gdscript_parser as _require_gdscript_parser

from mutation_gate import cli, mutants, no_comments, runner, token, vocabulary_check
from mutation_gate.repo import Config, GateError, Repo
from mutation_gate.waivers import Waiver, finding_waived

OPTED_IN = "no_comments = true\n"
FILE = "tests/test_a.py"
TS_FILE = "tests/test_a.ts"
TSX_FILE = "tests/test_a.tsx"


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


def _not_a_git_repo(*args, **kwargs):
    raise GateError("fatal: not a git repository")


def _gate(monkeypatch, tmp_path: Path, repo: Repo, added: dict[str, set[int]],
          pre: dict[str, str]) -> int:
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(mutants, "changed_lines", lambda root, staged: added)
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
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
    "# gdlint: disable=max-line-length\n",
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


def test_gdscript_comment_added_blocks_when_parser_is_ready(tmp_path, monkeypatch, capsys):
    """#218: no_comments.LANGUAGES excluded gdscript; the comment ban now
    reaches a .gd file through the same sgconfig scan #201 wired for mutants."""
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "func _ready():\n\tpass  # one\n",
                  "sgconfig.yml": GDSCRIPT_SGCONFIG})
    code = _gate(monkeypatch, tmp_path, repo, {"game/a.gd": {2}}, {})
    err = capsys.readouterr().err
    assert code == 1
    assert "game/a.gd:2" in err
    assert "# one" in err


def test_gdscript_without_parser_skips_with_a_visible_reason_instead_of_blocking(
    tmp_path, monkeypatch, capsys
):
    """--dry-run stays clear of coverage_map.blob_hashes, the seam past this
    point that needs real git — the same reason #201's own gdscript cli.main
    slice tests use --dry-run rather than --no-adversary."""
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": "func _ready():\n\tpass  # one\n"})
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(mutants, "changed_lines", lambda root, staged: {"game/a.gd": {2}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    _stub_git(monkeypatch, {})
    for mod in (cli, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")
    code = cli.main(["--staged", "--dry-run"])
    err = capsys.readouterr().err
    assert code == 0
    assert vocabulary_check.GDSCRIPT_MISSING in err


def test_check_passes_the_ready_config_into_every_ast_grep_call_for_gdscript(
    tmp_path, monkeypatch
):
    """Mirrors #201's mutants.py wiring test: a mocked probe proves a .gd file's
    scan (comment kind, then the pre-image copy's) always carries `--config=`,
    and a .py file in the same diff never sees it or the unsupported `-l gdscript`."""
    config = tmp_path / "sgconfig.yml"
    monkeypatch.setattr(mutants, "_gdscript_config", lambda root: config)
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

    monkeypatch.setattr(mutants.subprocess, "run", fake_run)
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": "pass  # one\n", "pkg/a.py": "y = 1  # two\n"})
    _stub_git(monkeypatch, {"game/a.gd": "pass  # zero\n"})
    no_comments.check(repo, {"game/a.gd": {1}, "pkg/a.py": {1}}, [], staged=True)
    gd_calls = [cmd for cmd in seen if any(a.endswith(".gd") for a in cmd)]
    py_calls = [cmd for cmd in seen if any(a.endswith(".py") for a in cmd)]
    assert len(gd_calls) == 2, "expected one call for the added file, one for its pre-image copy"
    assert all(cmd[:2] == ["ast-grep", "scan"] and f"--config={config}" in cmd for cmd in gd_calls)
    assert len(py_calls) == 1
    assert all(
        cmd[:2] == ["ast-grep", "run"] and not any(a.startswith("--config") for a in cmd)
        for cmd in py_calls
    )


def test_gdscript_preexisting_comment_on_an_edited_line_is_invisible(tmp_path, monkeypatch):
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "func _ready():\n\tvar health = 2  # one\n",
                  "sgconfig.yml": GDSCRIPT_SGCONFIG})
    pre = "func _ready():\n\tvar health = 1  # one\n"
    assert _findings(monkeypatch, repo, "game/a.gd", {2}, pre=pre) == []


def test_gdscript_pragma_is_carved_out_when_parser_is_ready(tmp_path, monkeypatch):
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "func _ready():\n\tpass  # noqa\n",
                  "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert _findings(monkeypatch, repo, "game/a.gd", {2}) == []


def test_gdscript_prose_comment_blocks_when_parser_is_ready(tmp_path, monkeypatch):
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "func _ready():\n\tpass  # one\n",
                  "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert _findings(monkeypatch, repo, "game/a.gd", {2}) == ["game/a.gd:2"]


@pytest.mark.parametrize("text", [
    "\t#region Movement\n",
    "\t#endregion Movement\n",
    "\t# gdlint: disable=max-line-length\n",
])
def test_gdscript_region_and_gdlint_pragmas_are_carved_out_when_parser_is_ready(
    tmp_path, monkeypatch, text
):
    """232: `#region`/`#endregion` parse as their own region_start/region_end
    kind, never `comment` — the grammar carves them out on its own."""
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": f"func _ready():\n{text}",
                  "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert _findings(monkeypatch, repo, "game/a.gd", {2}) == []


def test_gdscript_region_prose_blocks_when_parser_is_ready(tmp_path, monkeypatch):
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "func _ready():\n\t# region is weird\n",
                  "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert _findings(monkeypatch, repo, "game/a.gd", {2}) == ["game/a.gd:2"]


def test_gdscript_gdlint_lookalike_prose_blocks_when_parser_is_ready(tmp_path, monkeypatch):
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "func _ready():\n\t# gdlint is noisy\n",
                  "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert _findings(monkeypatch, repo, "game/a.gd", {2}) == ["game/a.gd:2"]


@pytest.mark.parametrize("text", ["#region\nvar x = 1\n#endregion\n", "#region Movement\nvar x = 1\n#endregion\n"])
def test_gdscript_top_level_region_is_carved_out_when_parser_is_ready(tmp_path, monkeypatch, text):
    """232: a bare `#region` and a top-level, unindented one both stay
    region_start/region_end, matching how Godot repos fold class bodies."""
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert _findings(monkeypatch, repo, "game/a.gd", {1, 3}) == []


def test_gdscript_warning_ignore_annotation_is_carved_out_when_parser_is_ready(tmp_path, monkeypatch):
    """232 title: `@warning_ignore(...)` parses as `annotation`, never
    `comment`, so it never reaches PRAGMA_RE either."""
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": 'func _ready():\n    @warning_ignore("unused_variable")\n    var y = 2\n',
                  "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert _findings(monkeypatch, repo, "game/a.gd", {2}) == []


def test_gdscript_missing_parser_skip_still_reaches_a_later_file(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "func _ready():\n\tpass  # one\n", "pkg/a.py": "y = 1  # two\n"})
    _stub_git(monkeypatch, {})
    found = no_comments.check(repo, {"game/a.gd": {2}, "pkg/a.py": {1}}, [], staged=True)
    assert [(f.file, f.line) for f in found] == [("pkg/a.py", 1)]


def test_added_ts_comment_line_blocks_and_names_the_line(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {TS_FILE: "const x = 1;  // one\n"})
    code = _gate(monkeypatch, tmp_path, repo, {TS_FILE: {1}}, {})
    err = capsys.readouterr().err
    assert code == 1
    assert f"{TS_FILE}:1" in err
    assert "// one" in err


def test_added_tsx_jsx_comment_line_blocks_and_names_the_line(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {TSX_FILE: "const x = <div>{/* one */}</div>;\n"})
    code = _gate(monkeypatch, tmp_path, repo, {TSX_FILE: {1}}, {})
    err = capsys.readouterr().err
    assert code == 1
    assert f"{TSX_FILE}:1" in err
    assert "/* one */" in err


def test_added_tsx_line_comment_blocks_and_names_the_line(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {TSX_FILE: "const x = 1;  // one\n"})
    code = _gate(monkeypatch, tmp_path, repo, {TSX_FILE: {1}}, {})
    err = capsys.readouterr().err
    assert code == 1
    assert f"{TSX_FILE}:1" in err
    assert "// one" in err


PRAGMA_TEXTS = [
    "// @ts-expect-error\n",
    "// @ts-ignore\n",
    "// eslint-disable-next-line no-unused-vars\n",
    "// eslint-disable-line no-unused-vars\n",
    "/* eslint-disable no-unused-vars */\n",
    "/// <reference types=\"node\" />\n",
    "/* istanbul ignore next */\n",
]


@pytest.mark.parametrize("text", PRAGMA_TEXTS)
def test_ts_pragmas_are_carved_out(tmp_path, monkeypatch, text):
    repo = _repo(tmp_path, OPTED_IN, {TS_FILE: text})
    assert _gate(monkeypatch, tmp_path, repo, {TS_FILE: {1}}, {}) == 0


@pytest.mark.parametrize("text", PRAGMA_TEXTS)
def test_tsx_pragmas_are_carved_out(tmp_path, monkeypatch, text):
    repo = _repo(tmp_path, OPTED_IN, {TSX_FILE: text})
    assert _gate(monkeypatch, tmp_path, repo, {TSX_FILE: {1}}, {}) == 0


@pytest.mark.parametrize("text", [
    "// eslint is noisy\n",
    "// @todo fix this later\n",
    "/// some prose, not a reference directive\n",
    "/* istanbul was not consulted */\n",
])
def test_ts_prose_that_merely_resembles_a_pragma_still_blocks(tmp_path, monkeypatch, text):
    repo = _repo(tmp_path, OPTED_IN, {TS_FILE: text})
    assert _gate(monkeypatch, tmp_path, repo, {TS_FILE: {1}}, {}) == 1


def test_ts_pragma_on_an_earlier_line_does_not_hide_a_later_prose_comment(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN,
                 {TS_FILE: "// @ts-expect-error\nconst y = 2;  // two\n"})
    code = _gate(monkeypatch, tmp_path, repo, {TS_FILE: {1, 2}}, {})
    err = capsys.readouterr().err
    assert code == 1
    assert f"{TS_FILE}:2" in err


def test_ts_preexisting_comment_on_an_edited_line_is_invisible(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"src/a.ts": "const x = 2;  // one\n"})
    assert _findings(monkeypatch, repo, "src/a.ts", {1}, pre="const x = 1;  // one\n") == []


def test_jsdoc_block_is_not_flagged_in_ts(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {TS_FILE: "/**\n * Added prose.\n */\nfunction f() {}\n"})
    assert _gate(monkeypatch, tmp_path, repo, {TS_FILE: {1, 2, 3}}, {}) == 0


def test_jsdoc_style_block_still_blocks_in_cpp(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"src/a.cpp": "/**\n * Added prose.\n */\nint f() { return 1; }\n"})
    assert _findings(monkeypatch, repo, "src/a.cpp", {1, 2, 3}) == ["src/a.cpp:1"]


def test_gdscript_missing_parser_message_prints_once_for_two_files(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": "pass  # one\n", "game/b.gd": "pass  # two\n"})
    _stub_git(monkeypatch, {})
    no_comments.check(repo, {"game/a.gd": {1}, "game/b.gd": {1}}, [], staged=True)
    assert capsys.readouterr().err.count(vocabulary_check.GDSCRIPT_MISSING) == 1
