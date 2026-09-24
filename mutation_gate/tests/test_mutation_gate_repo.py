"""Intent: a repo already gating one language must accept a second without
breaking the first.

Also: a repo whose tests sit beside their sources must be able to say so
without ungating those sources. dotfiles#66.

Also: the namespaces a checkout may gate under come from the environment, then
the repo's config, and an unconfigured checkout gates its own origin. agent-sdlc#8."""

import os
import subprocess
from pathlib import Path

import pytest

from mutation_gate import repo as repo_module
from mutation_gate.repo import (
    OWN_NAMESPACES_ENV,
    Config,
    GateError,
    LanguageConfig,
    Repo,
    git,
    git_bytes,
    post_image_path,
)


def test_git_missing_from_path_raises_gate_error_not_file_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(GateError, match="git not found on PATH"):
        git("rev-parse", "--show-toplevel")


def _stub_subprocess_run(monkeypatch, returncode: int, stdout: bytes = b"", stderr: bytes = b""):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(repo_module.subprocess, "run", fake_run)


def test_git_bytes_returns_raw_stdout_on_success(monkeypatch):
    _stub_subprocess_run(monkeypatch, returncode=0, stdout=b"\x00binary")
    assert git_bytes("show", ":x") == b"\x00binary"


def test_git_bytes_raises_gate_error_with_decoded_stderr_on_nonzero_exit(monkeypatch):
    _stub_subprocess_run(monkeypatch, returncode=7, stderr=b"fatal: bad revision")
    with pytest.raises(GateError, match="fatal: bad revision"):
        git_bytes("show", ":missing")


def _write(tmp_path: Path, toml: str) -> Path:
    (tmp_path / ".mutation-gate.toml").write_text(toml)
    return tmp_path


def test_flat_config_still_loads_as_before(tmp_path):
    root = _write(tmp_path, 'language = "gdscript"\ntest_paths = ["godot/tests"]\n')
    cfg = Config.load(root)
    assert cfg.language == "gdscript"
    assert cfg.for_language("gdscript").test_paths == ["godot/tests"]


def test_language_without_override_falls_back_to_flat_fields(tmp_path):
    root = _write(
        tmp_path,
        'language = "gdscript"\ntest_command = "tools/gate_gd_test.sh {tests}"\n',
    )
    cfg = Config.load(root)
    fallback = cfg.for_language("python")
    assert fallback.test_command == "tools/gate_gd_test.sh {tests}"


def test_language_override_dispatches_its_own_test_paths_and_command(tmp_path):
    root = _write(
        tmp_path,
        """
language = "gdscript"
test_paths = ["godot/project/tests"]
test_command = "tools/gate_gd_test.sh {tests}"

[languages.python]
test_paths = ["tests"]
test_command = "pytest -q {tests}"
""",
    )
    cfg = Config.load(root)
    gd = cfg.for_language("gdscript")
    py = cfg.for_language("python")
    assert gd.test_paths == ["godot/project/tests"]
    assert py.test_paths == ["tests"]
    assert py.test_command == "pytest -q {tests}"
    assert gd.test_command != py.test_command


def test_unknown_top_level_key_still_refused(tmp_path):
    root = _write(tmp_path, 'bogus = "x"\n')
    with pytest.raises(GateError, match="unknown key"):
        Config.load(root)


def test_unknown_key_inside_language_table_is_refused(tmp_path):
    root = _write(tmp_path, '[languages.python]\nbogus = "x"\n')
    with pytest.raises(GateError, match="languages.python"):
        Config.load(root)


def test_test_globs_loads_from_the_config_file_flat(tmp_path):
    root = _write(tmp_path, 'test_globs = ["webapp/lib/*.test.ts"]\n')
    assert Config.load(root).test_globs == ["webapp/lib/*.test.ts"]


def test_test_globs_loads_from_a_language_table(tmp_path):
    root = _write(
        tmp_path, '[languages.typescript]\ntest_globs = ["webapp/lib/*.test.ts"]\n'
    )
    cfg = Config.load(root)
    assert cfg.for_language("typescript").test_globs == ["webapp/lib/*.test.ts"]


def _colocated(tmp_path: Path, globs: list[str]) -> Repo:
    lib = tmp_path / "webapp" / "lib" / "geo"
    lib.mkdir(parents=True)
    (lib.parent / "decimate.ts").write_text("export function decimate() {}\n")
    (lib.parent / "decimate.test.ts").write_text("test('d', () => {});\n")
    (lib / "hull.ts").write_text("export function hull() {}\n")
    (lib / "hull.test.ts").write_text("test('h', () => {});\n")
    config = Config(languages={"typescript": LanguageConfig(test_globs=globs)})
    return Repo(root=tmp_path, origin="", remotes=(), config=config)


def test_colocated_test_beside_its_source_is_a_test(tmp_path):
    repo = _colocated(tmp_path, ["webapp/lib/*.test.ts"])
    assert repo.is_test("webapp/lib/decimate.test.ts")


def test_source_beside_a_colocated_test_stays_gated(tmp_path):
    repo = _colocated(tmp_path, ["webapp/lib/*.test.ts"])
    assert not repo.is_test("webapp/lib/decimate.ts")


def test_glob_star_does_not_cross_a_directory(tmp_path):
    repo = _colocated(tmp_path, ["webapp/lib/*.test.ts"])
    assert not repo.is_test("webapp/lib/geo/hull.test.ts")


def test_recursive_glob_reaches_a_nested_colocated_test(tmp_path):
    repo = _colocated(tmp_path, ["webapp/lib/**/*.test.ts"])
    assert repo.is_test("webapp/lib/geo/hull.test.ts")


def test_a_helper_under_a_test_path_is_still_a_test(tmp_path):
    repo = Repo(
        root=tmp_path,
        origin="",
        remotes=(),
        config=Config(test_globs=["webapp/lib/*.test.ts"]),
    )
    assert repo.is_test("tests/conftest.py")


def test_a_glob_matching_nothing_on_disk_gates_the_path(tmp_path):
    repo = _colocated(tmp_path, ["webapp/lib/*.spec.ts"])
    assert not repo.is_test("webapp/lib/decimate.test.ts")


def test_a_path_matching_only_the_second_of_two_globs_is_still_a_test(tmp_path):
    repo = Repo(
        root=tmp_path,
        origin="",
        remotes=(),
        config=Config(test_globs=["webapp/lib/*.spec.ts", "webapp/lib/*.test.ts"]),
    )
    assert repo.is_test("webapp/lib/decimate.test.ts")


def test_is_test_never_walks_the_filesystem(tmp_path, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("is_test must not touch the filesystem")

    monkeypatch.setattr(Path, "glob", _boom)
    monkeypatch.setattr(Path, "iterdir", _boom)
    monkeypatch.setattr(os, "scandir", _boom)
    monkeypatch.setattr(os, "listdir", _boom)
    repo = Repo(
        root=tmp_path,
        origin="",
        remotes=(),
        config=Config(test_globs=["webapp/lib/*.test.ts"]),
    )
    assert repo.is_test("webapp/lib/decimate.test.ts")
    assert not repo.is_test("webapp/lib/decimate.ts")


def test_is_test_never_walks_the_filesystem_for_a_language_scoped_glob(tmp_path, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("is_test must not touch the filesystem")

    monkeypatch.setattr(Path, "glob", _boom)
    monkeypatch.setattr(Path, "iterdir", _boom)
    monkeypatch.setattr(os, "scandir", _boom)
    monkeypatch.setattr(os, "listdir", _boom)
    repo = Repo(
        root=tmp_path,
        origin="",
        remotes=(),
        config=Config(languages={"typescript": LanguageConfig(test_globs=["webapp/lib/*.test.ts"])}),
    )
    assert repo.is_test("webapp/lib/decimate.test.ts")
    assert not repo.is_test("webapp/lib/decimate.ts")


def test_a_trailing_bare_double_star_matches_a_test_directory_not_a_file(tmp_path):
    repo = Repo(
        root=tmp_path, origin="", remotes=(), config=Config(test_globs=["webapp/tests/**"])
    )
    assert not repo.is_test("webapp/tests/decimate.test.ts")


def test_a_double_star_glob_reaches_a_zero_depth_colocated_test(tmp_path):
    repo = Repo(
        root=tmp_path,
        origin="",
        remotes=(),
        config=Config(test_globs=["webapp/lib/**/*.test.ts"]),
    )
    assert repo.is_test("webapp/lib/decimate.test.ts")


def test_a_glob_is_case_sensitive_like_path_glob(tmp_path):
    repo = Repo(
        root=tmp_path, origin="", remotes=(), config=Config(test_globs=["webapp/LIB/*.test.ts"])
    )
    assert not repo.is_test("webapp/lib/decimate.test.ts")


def _repo(tmp_path: Path, origin: str, remotes: tuple[str, ...] = ("origin",)) -> Repo:
    return Repo(root=tmp_path, origin=origin, remotes=remotes, config=Config.load(tmp_path))


def test_env_namespaces_accept_a_matching_origin(tmp_path, monkeypatch):
    monkeypatch.setenv(OWN_NAMESPACES_ENV, "some-org/:another-org/")
    repo = _repo(tmp_path, "https://github.com/another-org/x.git")
    assert repo.fork_signal is None


def test_env_namespaces_flag_a_foreign_origin(tmp_path, monkeypatch):
    monkeypatch.setenv(OWN_NAMESPACES_ENV, "some-org/:another-org/")
    repo = _repo(tmp_path, "https://github.com/third-party/x.git")
    assert repo.fork_signal == "origin https://github.com/third-party/x.git is outside your namespaces"


def test_env_namespaces_drop_empty_segments(tmp_path, monkeypatch):
    monkeypatch.setenv(OWN_NAMESPACES_ENV, ":some-org/::")
    repo = _repo(tmp_path, "https://github.com/third-party/x.git")
    assert repo.fork_signal is not None


def test_env_namespaces_override_the_config_key(tmp_path, monkeypatch):
    monkeypatch.setenv(OWN_NAMESPACES_ENV, "some-org/")
    _write(tmp_path, 'own_namespaces = ["third-party/"]\n')
    repo = _repo(tmp_path, "https://github.com/third-party/x.git")
    assert repo.fork_signal is not None


def test_config_namespaces_accept_a_matching_origin(tmp_path, monkeypatch):
    monkeypatch.delenv(OWN_NAMESPACES_ENV, raising=False)
    _write(tmp_path, 'own_namespaces = ["some-org/", "another-org/"]\n')
    repo = _repo(tmp_path, "https://github.com/some-org/x.git")
    assert repo.fork_signal is None


def test_config_namespaces_flag_a_foreign_origin(tmp_path, monkeypatch):
    monkeypatch.delenv(OWN_NAMESPACES_ENV, raising=False)
    _write(tmp_path, 'own_namespaces = ["some-org/", "another-org/"]\n')
    repo = _repo(tmp_path, "https://github.com/third-party/x.git")
    assert repo.fork_signal == "origin https://github.com/third-party/x.git is outside your namespaces"


def test_unconfigured_checkout_gates_any_origin(tmp_path, monkeypatch):
    monkeypatch.delenv(OWN_NAMESPACES_ENV, raising=False)
    repo = _repo(tmp_path, "https://github.com/third-party/x.git")
    assert repo.fork_signal is None


def test_unconfigured_checkout_still_flags_an_upstream_remote(tmp_path, monkeypatch):
    monkeypatch.delenv(OWN_NAMESPACES_ENV, raising=False)
    repo = _repo(tmp_path, "https://github.com/third-party/x.git", remotes=("origin", "upstream"))
    assert repo.fork_signal == "a remote named 'upstream' exists (fork of an upstream)"


@pytest.mark.parametrize(
    "field, expected",
    [
        ("b/fixture.py", "fixture.py"),
        ("/dev/null", None),
        (r'"b/caf\303\251.py"', "café.py"),
        (r'"b/tab\tname.py"', "tab\tname.py"),
        (r'"b/quote\"name.py"', 'quote"name.py'),
        (r'"b/back\\slash.py"', "back\\slash.py"),
        (r'"b/ctrl\001byte.py"', "ctrl\x01byte.py"),
        (r'"b/all\a\b\f\n\r\t\v\\end.py"', "all\a\b\f\n\r\t\v\\end.py"),
        (r'"b/\303\2511.py"', "é1.py"),
        (r'"b/bad\377.py"', "bad\udcff.py"),
    ],
)
def test_post_image_path_unescapes_git_c_style_quoting(field, expected):
    assert post_image_path(field) == expected


def test_post_image_path_leaves_an_unquoted_escape_sequence_unescaped():
    assert post_image_path(r"b/back\tail.py") == "back\\tail.py"
