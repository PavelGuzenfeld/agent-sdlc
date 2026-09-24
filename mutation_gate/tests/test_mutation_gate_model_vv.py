"""Intent: dotfiles#56 — Layer 0 of model-vv.md becomes a hook. The seven
acceptance steps in the issue's design comment, one failure mode each."""

import subprocess
from pathlib import Path

import pytest

from mutation_gate import model_vv
from mutation_gate.repo import Config, GateError, Golden, Repo
from mutation_gate.waivers import Waiver

SPEC = "docs/model-spec.md"


def _repo(tmp_path: Path, **cfg) -> Repo:
    (tmp_path / ".git").mkdir(exist_ok=True)
    return Repo(root=tmp_path, origin="", remotes=(), config=Config(**cfg))


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _all_lines(root: Path, rel: str) -> set[int]:
    return set(range(1, len((root / rel).read_text().splitlines()) + 1))


def _model_repo(tmp_path: Path, spec: str | None) -> Repo:
    _write(tmp_path, "filters/imm.py", "def mix(a, b):\n    return a + b\n")
    _write(tmp_path, "tests/test_imm.py",
           "from filters import imm\n\n\ndef test_mix_adds():\n    # MS-3\n    assert imm.mix(1, 2) == 3\n")
    if spec is not None:
        _write(tmp_path, SPEC, spec)
    return _repo(tmp_path, model_paths=["filters/"])


def _checks(findings: list[model_vv.Finding]) -> list[str]:
    return [f.check for f in findings]


def test_model_file_changed_without_spec_blocks_no_spec(tmp_path):
    repo = _model_repo(tmp_path, spec=None)
    findings = model_vv.check(repo, {"filters/imm.py": {2}}, [], staged=False)
    assert _checks(findings) == ["no-spec"]
    assert findings[0].file == "filters/imm.py"


def test_test_citing_a_still_tagged_line_blocks_tagged(tmp_path):
    repo = _model_repo(tmp_path, spec="MS-3 mixing is a convex sum (needs intent)\n")
    findings = model_vv.check(repo, {"tests/test_imm.py": {5}}, [], staged=False)
    assert _checks(findings) == ["tagged"]
    assert (findings[0].test, findings[0].ms) == ("test_mix_adds", 3)


def test_reconstructed_tag_blocks_like_needs_intent(tmp_path):
    repo = _model_repo(tmp_path, spec="MS-3 mixing is a convex sum (reconstructed)\n")
    assert _checks(model_vv.check(repo, {"tests/test_imm.py": {5}}, [], staged=False)) == ["tagged"]


def test_untagged_cited_line_passes(tmp_path):
    repo = _model_repo(tmp_path, spec="MS-3 mixing is a convex sum\n")
    assert model_vv.check(repo, {"tests/test_imm.py": {5}, "filters/imm.py": {2}}, [], staged=False) == []


def test_renumbering_the_spec_orphans_an_untouched_citation_and_blocks_dangling(tmp_path):
    repo = _model_repo(tmp_path, spec="MS-4 mixing is a convex sum\n")
    findings = model_vv.check(repo, {SPEC: {1}}, [], staged=False)
    assert _checks(findings) == ["dangling"]
    assert (findings[0].file, findings[0].ms) == ("tests/test_imm.py", 3)


def test_new_test_function_without_a_citation_blocks_no_citation_by_name(tmp_path):
    repo = _model_repo(tmp_path, spec="MS-3 mixing is a convex sum\n")
    _write(tmp_path, "tests/test_imm.py",
           "from filters import imm\n\n\ndef test_mix_adds():\n    # MS-3\n    assert imm.mix(1, 2) == 3\n\n\n"
           "def test_x():\n    assert imm.mix(0, 0) == 0\n")
    findings = model_vv.check(repo, {"tests/test_imm.py": {9, 10}}, [], staged=False)
    assert _checks(findings) == ["no-citation"]
    assert findings[0].test == "test_x"


def test_untouched_test_function_in_a_touched_file_is_not_checked(tmp_path):
    repo = _model_repo(tmp_path, spec="MS-3 mixing is a convex sum\n")
    _write(tmp_path, "tests/test_imm.py",
           "from filters import imm\nimport os\n\n\ndef test_legacy():\n    assert imm.mix(0, 0) == 0\n")
    assert model_vv.check(repo, {"tests/test_imm.py": {2}}, [], staged=False) == []


def test_citation_in_a_docstring_counts(tmp_path):
    repo = _model_repo(tmp_path, spec="MS-3 mixing is a convex sum\n")
    _write(tmp_path, "tests/test_imm.py",
           'from filters import imm\n\n\ndef test_mix_adds():\n    """MS-3: convex."""\n    assert imm.mix(1, 2) == 3\n')
    assert model_vv.check(repo, {"tests/test_imm.py": {6}}, [], staged=False) == []


def test_change_outside_model_and_test_scope_is_silent(tmp_path):
    repo = _model_repo(tmp_path, spec=None)
    _write(tmp_path, "data/loader.py", "def load():\n    return []\n")
    assert model_vv.check(repo, {"data/loader.py": {1, 2}}, [], staged=False) == []


def test_probe_hit_outside_model_paths_blocks_even_with_no_model_paths_declared(tmp_path):
    repo = _repo(tmp_path)
    _write(tmp_path, "scripts/bearing.py", "from math import atan2\n")
    findings = model_vv.check(repo, {"scripts/bearing.py": {1}}, [], staged=False)
    assert _checks(findings) == ["probe"]
    assert findings[0].file == "scripts/bearing.py"


def test_probe_needs_wrap_and_pi_together(tmp_path):
    repo = _repo(tmp_path)
    _write(tmp_path, "scripts/a.py", "def wrap_text(s):\n    return s\n")
    _write(tmp_path, "scripts/b.py", "def wrap_angle(a, pi):\n    return a % (2 * pi)\n")
    assert model_vv.check(repo, {"scripts/a.py": {1}}, [], staged=False) == []
    assert _checks(model_vv.check(repo, {"scripts/b.py": {1}}, [], staged=False)) == ["probe"]


def test_probe_skips_test_files(tmp_path):
    repo = _repo(tmp_path)
    _write(tmp_path, "tests/test_geo.py", "from math import atan2\n")
    assert model_vv.check(repo, {"tests/test_geo.py": {1}}, [], staged=False) == []


def test_model_exclude_with_reason_clears_the_probe(tmp_path):
    _write(tmp_path, ".mutation-gate.toml",
           '[[model_exclude]]\npath = "scripts/"\nreason = "plot annotations, no estimation"\n')
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config.load(tmp_path))
    _write(tmp_path, "scripts/bearing.py", "from math import atan2\n")
    assert model_vv.check(repo, {"scripts/bearing.py": {1}}, [], staged=False) == []


def test_model_exclude_without_reason_is_refused(tmp_path):
    _write(tmp_path, ".mutation-gate.toml", '[[model_exclude]]\npath = "scripts/"\n')
    with pytest.raises(GateError, match="reason"):
        Config.load(tmp_path)


def test_model_paths_key_loads_from_config(tmp_path):
    _write(tmp_path, ".mutation-gate.toml",
           'model_paths = ["filters/"]\nmodel_test_paths = ["tests/model"]\nmodel_spec = "issue:24"\n')
    cfg = Config.load(tmp_path)
    assert (cfg.model_paths, cfg.model_test_paths) == (["filters/"], ["tests/model"])


def test_duplicate_spec_number_refuses(tmp_path):
    _write(tmp_path, SPEC, "MS-1 a\nMS-1 b\n")
    with pytest.raises(GateError, match="MS-1"):
        model_vv.load_spec(_repo(tmp_path))


def test_spec_grammar_accepts_bullet_bold_and_punctuation_forms(tmp_path):
    _write(tmp_path, SPEC, "- MS-1: bullet colon\n* **MS-2** bold\nMS-3. period\n  MS-4) paren\nSee MS-5 in prose\nMS-6x not a line\n")
    assert set(model_vv.load_spec(_repo(tmp_path))) == {1, 2, 3, 4}


def test_check_waiver_clears_only_the_matching_test(tmp_path):
    repo = _model_repo(tmp_path, spec="MS-3 mixing is a convex sum\n")
    _write(tmp_path, "tests/test_imm.py",
           "from filters import imm\n\n\ndef test_x():\n    assert imm.mix(0, 0) == 0\n\n\n"
           "def test_y():\n    assert imm.mix(1, 1) == 2\n")
    waiver = Waiver(reason="fixture smoke test", check="no-citation", file="tests/test_imm.py", test="test_x")
    findings = model_vv.check(repo, {"tests/test_imm.py": _all_lines(tmp_path, "tests/test_imm.py")}, [waiver], staged=False)
    assert [(f.check, f.test) for f in findings] == [("no-citation", "test_y")]


def test_check_waiver_never_covers_a_mutant(tmp_path):
    from mutation_gate.mutants import Mutant
    waiver = Waiver(reason="r", check="no-spec", file="filters/imm.py")
    assert not waiver.covers(Mutant("filters/imm.py", 2, 0, 1, "+", "-", "arith"))


def test_model_test_paths_puts_a_cpp_test_in_scope_and_TEST_body_without_citation_blocks(tmp_path):
    _write(tmp_path, "gst/common/kalman_box.cpp", "double f() { return 0.0; }\n")
    _write(tmp_path, "tests/model/test_kalman_box.cpp",
           "#include <gtest/gtest.h>\nTEST(KalmanBox, CrossCorrelationIsZero) {\n  // MS-2\n  EXPECT_EQ(0.0, 0.0);\n}\n"
           "TEST_F(Fix, Gate)\n{\n  EXPECT_TRUE(true);\n}\n")
    _write(tmp_path, SPEC, "MS-2 cross-correlation is exactly zero\n")
    repo = _repo(tmp_path, language="cpp", model_paths=["gst/common/kalman_box.cpp"],
                 model_test_paths=["tests/model"])
    findings = model_vv.check(repo, {"tests/model/test_kalman_box.cpp": {3, 8}}, [], staged=False)
    assert [(f.check, f.test) for f in findings] == [("no-citation", "Fix, Gate")]


def _golden_repo(tmp_path: Path, artifact_text: str) -> Repo:
    _write(tmp_path, "model/ct_model.py", "A = [[0, 1], [0, 0]]\n")
    _write(tmp_path, "model/generated/fq.py", artifact_text)
    return _repo(tmp_path, golden=[Golden(source="model/ct_model.py", artifact="model/generated/fq.py")])


def _sha(tmp_path: Path, rel: str) -> str:
    import hashlib
    return hashlib.sha256((tmp_path / rel).read_bytes()).hexdigest()


def test_golden_artifact_without_the_source_hash_blocks_when_source_changed(tmp_path):
    repo = _golden_repo(tmp_path, "# source sha256: 0000\nF = 1\n")
    findings = model_vv.check(repo, {"model/ct_model.py": {1}}, [], staged=False)
    assert [(f.check, f.file) for f in findings] == [("golden", "model/generated/fq.py")]


def test_golden_artifact_carrying_the_source_hash_passes(tmp_path):
    repo = _golden_repo(tmp_path, "placeholder\n")
    _write(tmp_path, "model/generated/fq.py", f"# source sha256: {_sha(tmp_path, 'model/ct_model.py')}\nF = 1\n")
    assert model_vv.check(repo, {"model/generated/fq.py": {1}}, [], staged=False) == []


def test_stale_golden_is_not_checked_when_neither_file_changed(tmp_path):
    repo = _golden_repo(tmp_path, "no hash here\n")
    _write(tmp_path, "other.py", "x = 1\n")
    assert model_vv.check(repo, {"other.py": {1}}, [], staged=False) == []


def test_golden_finding_is_not_waivable(tmp_path):
    repo = _golden_repo(tmp_path, "no hash here\n")
    waiver = Waiver(reason="r", check="golden", file="model/generated/fq.py")
    assert _checks(model_vv.check(repo, {"model/ct_model.py": {1}}, [waiver], staged=False)) == ["golden"]


def test_golden_with_a_missing_source_file_refuses(tmp_path):
    repo = _golden_repo(tmp_path, "x\n")
    (tmp_path / "model/ct_model.py").unlink()
    with pytest.raises(GateError, match="missing"):
        model_vv.check(repo, {"model/generated/fq.py": {1}}, [], staged=False)


def test_golden_config_entry_with_an_extra_or_missing_key_is_refused(tmp_path):
    _write(tmp_path, ".mutation-gate.toml", '[[golden]]\nsource = "a.py"\n')
    with pytest.raises(GateError, match="golden"):
        Config.load(tmp_path)


def test_blind_export_holds_model_files_only_at_their_repo_paths(tmp_path):
    repo = _model_repo(tmp_path, spec="MS-3 mixing\n")
    _write(tmp_path, "filters/knet/gain.py", "w = 1\n")
    _write(tmp_path, ".git/HEAD", "ref: refs/heads/main\n")
    dest = tmp_path / "export"
    copied = model_vv.build_blind_export(repo, dest)
    assert copied == ["filters/imm.py", "filters/knet/gain.py"]
    assert sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()) == copied


def test_blind_pass_runs_only_when_a_model_file_changed(tmp_path):
    repo = _model_repo(tmp_path, spec="MS-3 mixing\n")
    assert model_vv.model_changed(repo, {"tests/test_imm.py": {1}}) is False
    assert model_vv.model_changed(repo, {"filters/imm.py": {1}}) is True


def test_blind_pass_reports_why_it_did_not_run_without_claude(tmp_path, monkeypatch):
    repo = _model_repo(tmp_path, spec="MS-3 mixing\n")
    monkeypatch.setattr(model_vv.shutil, "which", lambda name: None)
    assert model_vv.blind_pass(repo) == "blind pass skipped: `claude` not on PATH"


def test_blind_pass_invokes_claude_with_the_blind_isolation_flags_and_closed_stdin(tmp_path, monkeypatch):
    import subprocess as sp
    repo = _model_repo(tmp_path, spec="MS-3 mixing\n")
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"], seen["stdin"] = argv, kwargs["stdin"]
        return sp.CompletedProcess(argv, 0, stdout="B1 intent\n", stderr="")

    monkeypatch.setattr(model_vv.adversary.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(model_vv.adversary.subprocess, "run", fake_run)
    assert model_vv.blind_pass(repo) == "B1 intent"
    assert seen["argv"][-5:] == ["--strict-mcp-config", "--tools", "Read", "Grep", "Glob"]
    assert "--restricted" in seen["argv"] and "--disable-slash-commands" in seen["argv"]
    assert seen["stdin"] == sp.DEVNULL


def _issue_repo(tmp_path: Path, monkeypatch, body: str | None, cache_home: Path | None = None):
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home or tmp_path / "cache"))
    monkeypatch.setattr(model_vv, "fetch_issue_body", lambda repo, number: body)
    _write(tmp_path, "filters/imm.py", "def mix(a, b):\n    return a + b\n")
    _write(tmp_path, "tests/test_imm.py",
           "from filters import imm\n\n\ndef test_mix_adds():\n    # MS-3\n    assert imm.mix(1, 2) == 3\n")
    return _repo(tmp_path, model_paths=["filters/"], model_spec="issue:24")


def test_model_spec_key_loads_from_config_and_defaults_to_the_file(tmp_path):
    (tmp_path / ".mutation-gate.toml").write_text('model_paths = ["filters/"]\nmodel_spec = "issue:24"\n')
    assert Config.load(tmp_path).model_spec == "issue:24"
    assert Config().model_spec == SPEC


def test_model_paths_with_no_model_spec_key_is_refused_for_issue_n(tmp_path):
    _write(tmp_path, ".mutation-gate.toml", 'model_paths = ["filters/"]\n')
    with pytest.raises(GateError, match="issue:N"):
        Config.load(tmp_path)


def test_model_paths_with_an_explicit_file_model_spec_is_refused(tmp_path):
    _write(tmp_path, ".mutation-gate.toml",
           'model_paths = ["filters/"]\nmodel_spec = "docs/other-spec.md"\n')
    with pytest.raises(GateError, match="issue:N"):
        Config.load(tmp_path)


def test_no_model_paths_leaves_the_default_file_model_spec_unrefused(tmp_path):
    _write(tmp_path, ".mutation-gate.toml", 'test_paths = ["tests"]\n')
    assert Config.load(tmp_path).model_spec == SPEC


def test_untagged_line_in_the_spec_issue_passes(tmp_path, monkeypatch):
    repo = _issue_repo(tmp_path, monkeypatch, "Spec\n\n- MS-3: convex.\n")
    assert model_vv.check(repo, {"tests/test_imm.py": _all_lines(tmp_path, "tests/test_imm.py")}, [], staged=False) == []


def test_tagged_line_in_the_spec_issue_blocks_tagged(tmp_path, monkeypatch):
    repo = _issue_repo(tmp_path, monkeypatch, "- MS-3: convex. (needs intent)\n")
    findings = model_vv.check(repo, {"tests/test_imm.py": _all_lines(tmp_path, "tests/test_imm.py")}, [], staged=False)
    assert _checks(findings) == ["tagged"]


def test_issue_fetch_failure_falls_back_to_the_cached_copy(tmp_path, monkeypatch):
    cache_home = tmp_path / "cache"
    warm = _issue_repo(tmp_path, monkeypatch, "- MS-3: convex.\n", cache_home)
    assert model_vv.load_spec(warm) == {3: "- MS-3: convex."}
    cold = _issue_repo(tmp_path, monkeypatch, None, cache_home)
    assert model_vv.load_spec(cold) == {3: "- MS-3: convex."}


def test_issue_fetch_failure_without_a_cache_refuses(tmp_path, monkeypatch):
    repo = _issue_repo(tmp_path, monkeypatch, None)
    with pytest.raises(GateError, match="issue:24"):
        model_vv.load_spec(repo)


def test_issue_source_is_never_a_changed_file_so_only_touched_tests_are_checked(tmp_path, monkeypatch):
    repo = _issue_repo(tmp_path, monkeypatch, "- MS-3: convex. (needs intent)\n")
    assert model_vv.check(repo, {"filters/other.py": {1}}, [], staged=False) == []


def _fake_gh(tmp_path: Path, monkeypatch, script: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text("#!/bin/sh\n" + script)
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ['PATH']}")


def test_fetch_issue_body_returns_gh_stdout_on_success(tmp_path, monkeypatch):
    _fake_gh(tmp_path, monkeypatch, "printf -- '- MS-3: convex.\\n'\n")
    assert model_vv.fetch_issue_body(_repo(tmp_path), "24") == "- MS-3: convex.\n"


def test_fetch_issue_body_returns_none_when_gh_fails(tmp_path, monkeypatch):
    _fake_gh(tmp_path, monkeypatch, "printf -- '- MS-3: stale.\\n'\nexit 1\n")
    assert model_vv.fetch_issue_body(_repo(tmp_path), "24") is None


def test_no_spec_finding_comes_before_the_citation_findings(tmp_path):
    repo = _model_repo(tmp_path, spec=None)
    _write(tmp_path, "tests/test_imm.py",
           "from filters import imm\n\n\ndef test_x():\n    assert imm.mix(0, 0) == 0\n")
    findings = model_vv.check(
        repo, {"filters/imm.py": {2}, "tests/test_imm.py": _all_lines(tmp_path, "tests/test_imm.py")},
        [], staged=False,
    )
    assert _checks(findings) == ["no-spec", "no-citation"]


def test_source_error_reads_first_line_of_error_output(monkeypatch, tmp_path):
    """#202: model_vv.test_extents truncated at 200 chars instead of the
    first line, so a multi-line ast-grep error gave a multi-line refusal."""
    fixture = tmp_path / "test_a.py"
    fixture.write_text("def test_a():\n    assert True\n")
    first_line = "bad kind " + "x" * 200

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 8, stdout="", stderr=f"{first_line}\nsee --help")

    monkeypatch.setattr(model_vv.subprocess, "run", fake_run)
    with pytest.raises(GateError) as excinfo:
        model_vv.test_extents(fixture, "python")
    assert str(excinfo.value).splitlines() == [str(excinfo.value)]
    assert first_line in str(excinfo.value)
    assert "see --help" not in str(excinfo.value)


def test_source_error_uses_status_code_for_empty_output(monkeypatch, tmp_path):
    fixture = tmp_path / "test_a.py"
    fixture.write_text("def test_a():\n    assert True\n")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 8, stdout="", stderr="")

    monkeypatch.setattr(model_vv.subprocess, "run", fake_run)
    with pytest.raises(GateError, match=r"exit 8$"):
        model_vv.test_extents(fixture, "python")


def test_source_error_sends_output_to_reader(monkeypatch, tmp_path):
    """#202: one helper backs every ast-grep refusal; this pins test_extents'."""
    fixture = tmp_path / "test_a.py"
    fixture.write_text("def test_a():\n    assert True\n")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 8, stdout="", stderr="boom")

    monkeypatch.setattr(model_vv.subprocess, "run", fake_run)
    monkeypatch.setattr(model_vv.mutants, "render_error_line", lambda result: "stub-line")
    with pytest.raises(GateError, match="stub-line"):
        model_vv.test_extents(fixture, "python")
