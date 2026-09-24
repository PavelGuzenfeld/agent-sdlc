"""Intent: #159 — mutants.changed_lines ran an unpinned `git diff -U0
--no-color` and only recognized `+++ b/` headers. diff.noprefix or
diff.mnemonicPrefix reshapes that header and silently dropped the file's
changed lines, so the gate mutated nothing there and no_comments (the same
fail-open class #151 fixed in no-leaks) scanned nothing there. Pin the diff
invocation with repo.DIFF_PREFIX_PIN_ARGS and parse with repo.post_image_path,
the helper no-leaks shares. `git` is stubbed; the test image carries no git
binary."""

import contextlib
import subprocess
from pathlib import Path

import pytest
from conftest import (
    GDSCRIPT_BROKEN_SGCONFIG,
    GDSCRIPT_SGCONFIG,
    require_gdscript_parser as _require_gdscript_parser,
)

from mutation_gate import cli, mutants, no_comments, vocabulary_check
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


def test_the_pinned_args_are_the_literal_flags_that_defeat_diff_prefix_config():
    assert DIFF_PREFIX_PIN_ARGS == ("--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/")


def test_the_staged_diff_invocation_is_pinned_and_is_the_only_git_call(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch, diff="")
    mutants.changed_lines(tmp_path, staged=True)
    assert calls == [
        ("diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/", "--cached")
    ]


def test_the_worktree_diff_invocation_is_pinned_and_is_the_only_git_call(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch, diff="")
    mutants.changed_lines(tmp_path, staged=False)
    assert calls == [
        ("diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/")
    ]


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
    assert mutants.changed_lines(tmp_path, staged=True) == {"fixture.py": {1}}


def test_a_quoted_post_image_header_still_attributes_the_line(monkeypatch, tmp_path):
    diff = (
        'diff --git "a/caf\\303\\251.py" "b/caf\\303\\251.py"\n'
        '--- "a/caf\\303\\251.py"\n'
        '+++ "b/caf\\303\\251.py"\n'
        "@@ -0,0 +1,1 @@\n"
        "+x = 1\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert mutants.changed_lines(tmp_path, staged=True) == {"café.py": {1}}


def test_generate_reaches_a_real_file_named_from_a_quoted_diff_header(monkeypatch, tmp_path):
    (tmp_path / "café.py").write_text("def f(x):\n    return x <= 1\n")
    diff = (
        'diff --git "a/caf\\303\\251.py" "b/caf\\303\\251.py"\n'
        '--- "a/caf\\303\\251.py"\n'
        '+++ "b/caf\\303\\251.py"\n'
        "@@ -0,0 +2,1 @@\n"
        "+    return x <= 1\n"
    )
    _stub_git(monkeypatch, diff=diff)
    changed = mutants.changed_lines(tmp_path, staged=True)
    generated = mutants.generate(tmp_path, changed, "python")
    assert ("x <= 1", "x < 1") in [(m.old, m.new) for m in generated]


def test_an_unparseable_noprefix_post_image_header_refuses(monkeypatch, tmp_path):
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


def test_an_unparseable_mnemonic_prefixed_post_image_header_refuses(monkeypatch, tmp_path):
    diff = (
        "diff --git a/fixture.py i/fixture.py\n"
        "--- w/fixture.py\n"
        "+++ i/fixture.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+x = 1\n"
    )
    _stub_git(monkeypatch, diff=diff)
    with pytest.raises(GateError):
        mutants.changed_lines(tmp_path, staged=True)


def test_changed_lines_refuses_through_the_shared_post_image_parser(monkeypatch, tmp_path):
    def _always_refuses(field: str) -> str | None:
        raise GateError("stub")

    monkeypatch.setattr(mutants, "post_image_path", _always_refuses)
    _stub_git(monkeypatch, diff=_diff("fixture.py", "x = 1"))
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
    assert "post-image header did not parse" in capsys.readouterr().err


def test_kind_hits_raises_gate_error_on_a_crashed_ast_grep_scan(monkeypatch, tmp_path):
    """#186: a return code outside run's own 0 (match) / 1 (no match) is a
    crash, not an empty result, even when stdout is not empty."""
    fixture = tmp_path / "fixture.py"
    fixture.write_text("x = 1\n")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 8, stdout="[]", stderr="Error: crashed parser\nHelp: retry"
        )

    monkeypatch.setattr(mutants.subprocess, "run", fake_run)
    with pytest.raises(GateError) as excinfo:
        mutants.kind_hits(fixture, "python", "comment")
    assert str(excinfo.value).splitlines() == [str(excinfo.value)]
    assert "crashed parser" in str(excinfo.value)
    assert "retry" not in str(excinfo.value)


@pytest.mark.parametrize("stderr", ["", "\n \t\n"])
def test_path_error_uses_status_code_for_empty_output(monkeypatch, tmp_path, stderr):
    """#202: no usable stderr still needs a one-line refusal."""
    fixture = tmp_path / "fixture.py"
    fixture.write_text("x = 1\n")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 9, stdout="", stderr=stderr)

    monkeypatch.setattr(mutants.subprocess, "run", fake_run)
    with pytest.raises(GateError, match=r"exit 9$"):
        mutants.kind_hits(fixture, "python", "comment")


def test_pattern_error_reads_first_line_of_error_output(monkeypatch, tmp_path):
    """#202: mutants._ast_grep truncated at 200 chars instead of the first
    line, so a multi-line ast-grep error gave a multi-line refusal."""
    fixture = tmp_path / "fixture.py"
    fixture.write_text("x = 1\n")
    first_line = "bad pattern " + "x" * 200

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 8, stdout="", stderr=f"{first_line}\nsee --help")

    monkeypatch.setattr(mutants.subprocess, "run", fake_run)
    with pytest.raises(GateError) as excinfo:
        mutants._ast_grep(fixture, "python", "$A", "$A", None)
    assert str(excinfo.value).splitlines() == [str(excinfo.value)]
    assert first_line in str(excinfo.value)
    assert "see --help" not in str(excinfo.value)


@pytest.mark.parametrize("stderr", ["", "\n \t\n"])
def test_pattern_error_uses_status_code_for_empty_output(monkeypatch, tmp_path, stderr):
    fixture = tmp_path / "fixture.py"
    fixture.write_text("x = 1\n")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 8, stdout="", stderr=stderr)

    monkeypatch.setattr(mutants.subprocess, "run", fake_run)
    with pytest.raises(GateError, match=r"exit 8$"):
        mutants._ast_grep(fixture, "python", "$A", "$A", None)


def test_pattern_error_sends_output_to_reader(monkeypatch, tmp_path):
    """#202: one helper backs every ast-grep refusal; this pins _ast_grep's."""
    fixture = tmp_path / "fixture.py"
    fixture.write_text("x = 1\n")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 8, stdout="", stderr="boom")

    monkeypatch.setattr(mutants.subprocess, "run", fake_run)
    monkeypatch.setattr(mutants, "render_error_line", lambda result: "stub-line")
    with pytest.raises(GateError, match="stub-line"):
        mutants._ast_grep(fixture, "python", "$A", "$A", None)


def test_path_error_sends_output_to_reader(monkeypatch, tmp_path):
    """#202: one helper backs every ast-grep refusal; this pins kind_hits'."""
    fixture = tmp_path / "fixture.py"
    fixture.write_text("x = 1\n")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 8, stdout="", stderr="boom")

    monkeypatch.setattr(mutants.subprocess, "run", fake_run)
    monkeypatch.setattr(mutants, "render_error_line", lambda result: "stub-line")
    with pytest.raises(GateError, match="stub-line"):
        mutants.kind_hits(fixture, "python", "comment")


def test_ast_grep_routes_gdscript_through_scan_with_the_custom_language_config(tmp_path):
    """#201: `ast-grep run -l gdscript` rejects gdscript outright ("gdscript is
    not supported"); the custom language only loads through `scan --config`."""
    _require_gdscript_parser()
    config = tmp_path / "sgconfig.yml"
    config.write_text(GDSCRIPT_SGCONFIG)
    fixture = tmp_path / "a.gd"
    fixture.write_text("var x = 1 + 2\n")
    hits = mutants._ast_grep(fixture, "gdscript", "$A + $B", "$A - $B", config)
    assert [(h["text"], h["replacement"]) for h in hits] == [("1 + 2", "1 - 2")]


def test_generate_produces_a_gdscript_mutant_when_the_parser_is_ready(tmp_path, capsys):
    _require_gdscript_parser()
    (tmp_path / "sgconfig.yml").write_text(GDSCRIPT_SGCONFIG)
    (tmp_path / "a.gd").write_text("func _ready():\n\tvar x = 1 + 2\n")
    generated = mutants.generate(tmp_path, {"a.gd": {2}}, "gdscript")
    assert ("1 + 2", "1 - 2") in [(m.old, m.new) for m in generated]
    assert vocabulary_check.GDSCRIPT_MISSING not in capsys.readouterr().err


def test_gdscript_mutation_skipped_names_the_installer_and_the_missing_file():
    assert vocabulary_check.GDSCRIPT_MISSING == (
        "gdscript skipped: no sgconfig.yml — install the parser with "
        "bin/install-gdscript-parser and commit one"
    )


def test_generate_skips_gdscript_with_a_visible_reason_when_the_parser_is_not_ready(
    tmp_path, capsys
):
    (tmp_path / "a.gd").write_text("func _ready():\n\tvar x = 1 + 2\n")
    generated = mutants.generate(tmp_path, {"a.gd": {2}}, "gdscript")
    assert generated == []
    assert vocabulary_check.GDSCRIPT_MISSING in capsys.readouterr().err


def test_generate_skips_gdscript_with_a_visible_reason_when_the_library_is_broken(
    tmp_path, capsys
):
    """A committed sgconfig.yml pointing at a missing library is still not
    ready — treat it the same as no sgconfig.yml, per vocabulary_check."""
    (tmp_path / "sgconfig.yml").write_text(GDSCRIPT_BROKEN_SGCONFIG)
    (tmp_path / "a.gd").write_text("func _ready():\n\tvar x = 1 + 2\n")
    generated = mutants.generate(tmp_path, {"a.gd": {2}}, "gdscript")
    assert generated == []
    assert vocabulary_check.GDSCRIPT_MISSING in capsys.readouterr().err


def test_generate_still_reaches_a_later_file_after_skipping_an_unready_gdscript_one(
    tmp_path,
):
    """Skipping the unready .gd file must `continue` the file loop, not `break`
    out of it and drop every file sorted after it."""
    (tmp_path / "a.gd").write_text("func _ready():\n\tvar x = 1 + 2\n")
    (tmp_path / "b.py").write_text("x = 1 + 2\n")
    generated = mutants.generate(tmp_path, {"a.gd": {2}, "b.py": {1}}, "python")
    assert ("1 + 2", "1 - 2") in [(m.old, m.new) for m in generated]


def test_generate_passes_the_ready_config_into_every_ast_grep_call_for_gdscript(
    tmp_path, monkeypatch
):
    """A mocked probe proves the wiring without the real parser: once
    `_gdscript_config` reports ready, `--config=` must reach every ast-grep
    call for that file, never the unsupported `-l gdscript`."""
    config = tmp_path / "sgconfig.yml"
    monkeypatch.setattr(mutants, "_gdscript_config", lambda root: config)
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    monkeypatch.setattr(mutants.subprocess, "run", fake_run)
    (tmp_path / "a.gd").write_text("var x = 1\n")
    mutants.generate(tmp_path, {"a.gd": {1}}, "gdscript")
    assert seen
    assert all(cmd[:2] == ["ast-grep", "scan"] and f"--config={config}" in cmd for cmd in seen)
    assert not any("-l" in cmd or "gdscript" in cmd for cmd in seen)


def test_generate_does_not_probe_gdscript_readiness_for_an_unrelated_language(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        mutants, "_gdscript_config",
        lambda root: pytest.fail("probed gdscript readiness for a python-only diff"),
    )
    (tmp_path / "a.py").write_text("x = 1 + 2\n")
    mutants.generate(tmp_path, {"a.py": {1}}, "python")


def _not_a_git_repo(*args, **kwargs):
    raise GateError("fatal: not a git repository")


def test_staged_dry_run_generates_gdscript_mutants_when_the_parser_is_ready(
    tmp_path, monkeypatch, capsys
):
    """Slice (#201): cli.main --staged on a .gd change generates mutants
    through the sgconfig custom-language path once the parser is ready."""
    _require_gdscript_parser()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    (tmp_path / "sgconfig.yml").write_text(GDSCRIPT_SGCONFIG)
    (tmp_path / "a.gd").write_text("func _ready():\n\tvar x = 1 + 2\n")
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"a.gd": {2}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    assert cli.main(["--staged", "--dry-run"]) == 0
    assert "1 + 2 => 1 - 2" in capsys.readouterr().err


def test_staged_dry_run_says_skipped_when_the_gdscript_parser_is_not_ready(
    tmp_path, monkeypatch, capsys
):
    """Slice (#201): the same .gd change says so and skips, rather than
    refusing the commit, when no sgconfig.yml is committed."""
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    (tmp_path / "a.gd").write_text("func _ready():\n\tvar x = 1 + 2\n")
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"a.gd": {2}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    assert cli.main(["--staged", "--dry-run"]) == 0
    err = capsys.readouterr().err
    assert vocabulary_check.GDSCRIPT_MISSING in err
    assert "a.gd: 0 candidate test file(s), 0 mutant(s)" in err


def test_staged_dry_run_probes_gdscript_readiness_once_across_no_comments_vocabulary_and_mutants(
    tmp_path, monkeypatch, capsys
):
    """#233: no-comments, vocabulary and mutants each ask whether the parser
    is ready for the same .gd change; the probe and its skip line must not
    repeat just because three checks asked."""
    repo = Repo(root=tmp_path, origin="", remotes=(),
                config=Config(no_comments=True, vocabulary=".vocabulary.toml"))
    (tmp_path / ".vocabulary.toml").write_text("")
    (tmp_path / "sgconfig.yml").write_text(GDSCRIPT_BROKEN_SGCONFIG)
    (tmp_path / "a.gd").write_text("func _ready():\n\tvar x = 1 + 2\n")
    (tmp_path / "b.gd").write_text("func _ready():\n\tvar x = 1 + 2\n")
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(
        cli.mutants, "changed_lines", lambda root, staged: {"a.gd": {2}, "b.gd": {2}}
    )
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    monkeypatch.setattr(cli.vocabulary_path, "git", lambda *a, **k: "")

    no_comments_calls = []
    real_no_comments_check = no_comments.check

    def counting_no_comments_check(*a, **k):
        no_comments_calls.append(1)
        return real_no_comments_check(*a, **k)

    monkeypatch.setattr(cli.no_comments, "check", counting_no_comments_check)

    vocabulary_calls = []
    real_vocabulary_check = vocabulary_check.check

    def counting_vocabulary_check(*a, **k):
        vocabulary_calls.append(1)
        return real_vocabulary_check(*a, **k)

    monkeypatch.setattr(cli.vocabulary_check, "check", counting_vocabulary_check)

    probe_calls = []
    real_run = vocabulary_check.subprocess.run

    def counting_run(cmd, **kwargs):
        if any('"id": "probe"' in str(part) for part in cmd):
            probe_calls.append(cmd)
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(vocabulary_check.subprocess, "run", counting_run)

    assert cli.main(["--staged", "--dry-run"]) == 0
    err = capsys.readouterr().err
    assert no_comments_calls == [1]
    assert vocabulary_calls == [1]
    assert "a.gd: 0 candidate test file(s), 0 mutant(s)" in err
    assert "b.gd: 0 candidate test file(s), 0 mutant(s)" in err
    assert err.count(vocabulary_check.GDSCRIPT_MISSING) == 1
    assert len(probe_calls) == 1


def test_staged_dry_run_says_skipped_once_with_no_sgconfig_at_all(
    tmp_path, monkeypatch, capsys
):
    """#233 (adversary): the missing-sgconfig case, not just the broken-library
    one, must still print a single skip line across every enabled check."""
    repo = Repo(root=tmp_path, origin="", remotes=(),
                config=Config(no_comments=True, vocabulary=".vocabulary.toml"))
    (tmp_path / ".vocabulary.toml").write_text("")
    (tmp_path / "a.gd").write_text("func _ready():\n\tvar x = 1 + 2\n")
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"a.gd": {2}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    monkeypatch.setattr(cli.vocabulary_path, "git", lambda *a, **k: "")
    assert cli.main(["--staged", "--dry-run"]) == 0
    err = capsys.readouterr().err
    assert err.count(vocabulary_check.GDSCRIPT_MISSING) == 1


def test_staged_dry_run_never_probes_gdscript_readiness_for_a_python_only_change(
    tmp_path, monkeypatch, capsys
):
    """#233 (adversary): a diff with no .gd file must not trigger the probe at
    all, at the cli.main level, not just inside one module's own function."""
    repo = Repo(root=tmp_path, origin="", remotes=(),
                config=Config(no_comments=True, vocabulary=".vocabulary.toml"))
    (tmp_path / ".vocabulary.toml").write_text("")
    (tmp_path / "a.py").write_text("position = 1 + 2\n")
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"a.py": {1}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    monkeypatch.setattr(cli.vocabulary_path, "git", lambda *a, **k: "")
    monkeypatch.setattr(
        vocabulary_check, "_gdscript_ready",
        lambda root: pytest.fail("probed gdscript readiness for a python-only diff"),
    )
    assert cli.main(["--staged", "--dry-run"]) == 0
    assert vocabulary_check.GDSCRIPT_MISSING not in capsys.readouterr().err


def test_staged_dry_run_probes_gdscript_readiness_once_when_the_parser_is_ready(
    tmp_path, monkeypatch, capsys
):
    """#233 (adversary): the once-per-run guarantee must hold on the happy
    path too, not only when the parser is missing or broken."""
    _require_gdscript_parser()
    repo = Repo(root=tmp_path, origin="", remotes=(),
                config=Config(no_comments=True, vocabulary=".vocabulary.toml"))
    (tmp_path / ".vocabulary.toml").write_text("")
    (tmp_path / "sgconfig.yml").write_text(GDSCRIPT_SGCONFIG)
    (tmp_path / "a.gd").write_text("func _ready():\n\tvar position = 1 + 2\n")
    (tmp_path / "b.gd").write_text("func _ready():\n\tvar position = 1 + 2\n")
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(
        cli.mutants, "changed_lines", lambda root, staged: {"a.gd": {2}, "b.gd": {2}}
    )
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    monkeypatch.setattr(cli.vocabulary_path, "git", lambda *a, **k: "")

    probe_calls = []
    real_run = vocabulary_check.subprocess.run

    def counting_run(cmd, **kwargs):
        if any('"id": "probe"' in str(part) for part in cmd):
            probe_calls.append(cmd)
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(vocabulary_check.subprocess, "run", counting_run)

    assert cli.main(["--staged", "--dry-run"]) == 0
    err = capsys.readouterr().err
    assert vocabulary_check.GDSCRIPT_MISSING not in err
    assert len(probe_calls) == 1
