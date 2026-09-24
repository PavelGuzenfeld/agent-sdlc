"""Intent: #108 (decisions 16, 34, 35 of #103) — every directory or file segment
a diff adds, extension stripped, goes through the vocabulary and the `NOUN+`
mold; a file whose stem matches a class it declares takes the type mold
instead. A private module takes a trailing `_`; a leading `_` blocks except on
the core's tool-dictated list. standard's `diff-file-naming.sh` exemption list
is vendored in and pinned against its text. A segment under an
already-tracked directory is the only one checked; the directory itself is
skipped once it predates the diff.

Driven through cli.main as the #105 slice is: discover and the diff are
stubbed — the gate's own test image carries no git — the config load, the
packaged core, the ast-grep scan over the real staged files and the exit
code are real. One slice at the bottom runs a real git repository instead
and skips cleanly where git is absent; CI's mutation-gate-tests job installs
one."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from mutation_gate import cli, runner, token, vocabulary_path
from mutation_gate.repo import Config, GateError, Repo
from mutation_gate.waivers import Waiver

_GIT_IDENTITY = ("-c", "user.email=sentinel", "-c", "user.name=sentinel")


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _repo(tmp_path: Path, domain: str = "", config: Config | None = None) -> Repo:
    root = tmp_path / "repo"
    root.mkdir()
    _write(root, ".vocabulary.toml", domain)
    return Repo(root=root, origin="", remotes=(),
                config=config or Config(vocabulary=".vocabulary.toml"))


def _fake_git(cached: list[str] = (), worktree: list[str] = (),
              ls_tree: list[str] | None = (), ls_files: list[str] = ()):
    def fake(*args: str, cwd=None) -> str:
        if args[0] == "diff":
            added = cached if "--cached" in args else worktree
            return "".join(f"{p}\0" for p in added)
        if args[:3] == ("ls-tree", "-r", "--name-only"):
            if ls_tree is None:
                raise GateError("git ls-tree: fatal: Not a valid object name HEAD")
            return "".join(f"{p}\n" for p in ls_tree)
        if args == ("ls-files",):
            return "".join(f"{p}\n" for p in ls_files)
        raise AssertionError(f"unexpected git call {args}")
    return fake


def _added(monkeypatch, repo: Repo, files: dict[str, str], existing: list[str] | None = ()) -> None:
    for rel, text in files.items():
        _write(repo.root, rel, text)
    monkeypatch.setattr(vocabulary_path, "git", _fake_git(cached=list(files), ls_tree=existing))


def test_file_named_after_the_class_it_declares_passes(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/frame_parser.py": "class FrameParser:\n    pass\n"},
           existing=["src/existing.py"])
    assert vocabulary_path.check(repo, True, []) == []


def test_unknown_word_and_wrong_shape_block_on_the_mold_word(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/parse_stuff.py": "pass\n"}, existing=["src/existing.py"])
    found = vocabulary_path.check(repo, True, [])
    assert [(f.file, f.kind, f.name, f.detail) for f in found] == [
        ("src/parse_stuff.py", "namespace", "parse_stuff", "`stuff` is not in the dictionary"),
        ("src/parse_stuff.py", "namespace", "parse_stuff", "a namespace takes nouns only"),
    ]


def test_the_same_stem_blocks_purely_on_the_mold_once_the_word_is_known(tmp_path, monkeypatch):
    domain = '[[concept]]\nword = "stuff"\nmeaning = "generic material"\npos = ["noun"]\n'
    repo = _repo(tmp_path, domain)
    _added(monkeypatch, repo, {"src/parse_stuff.py": "pass\n"}, existing=["src/existing.py"])
    found = vocabulary_path.check(repo, True, [])
    assert [f.detail for f in found] == ["a namespace takes nouns only"]


def test_leading_underscore_file_blocks_suggesting_trailing_form(tmp_path, monkeypatch):
    domain = '[[concept]]\nword = "impl"\nmeaning = "a private implementation module"\npos = ["noun"]\n'
    repo = _repo(tmp_path, domain)
    _added(monkeypatch, repo, {"src/_impl.py": "pass\n"}, existing=["src/existing.py"])
    found = vocabulary_path.check(repo, True, [])
    assert [(f.name, f.suggestion) for f in found] == [("_impl", "impl_.py")]


def test_vague_word_file_segment_suggests_the_hint_with_no_suffix(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/manager.py": "pass\n"}, existing=["src/existing.py"])
    found = vocabulary_path.check(repo, True, [])
    assert [(f.rule, f.suggestion) for f in found if f.rule == "vague_word"] == [
        ("vague_word", "name what it does: scheduler, registry, pool, cache")
    ]


def test_init_cmakelists_and_readme_pass(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"__init__.py": "", "CMakeLists.txt": "", "README.md": ""})
    assert vocabulary_path.check(repo, True, []) == []


def test_tool_dictated_version_file_and_pybind_extension_pass(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/_version.py": "", "src/_core.so": ""},
           existing=["src/existing.py"])
    assert vocabulary_path.check(repo, True, []) == []


def test_dunder_main_passes(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"__main__.py": "pass\n"})
    assert vocabulary_path.check(repo, True, []) == []


def test_a_noun_phrase_file_with_no_declared_class_passes_the_namespace_mold(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/frame_count.py": "pass\n"}, existing=["src/existing.py"])
    assert vocabulary_path.check(repo, True, []) == []


def test_a_file_with_the_trailing_underscore_private_mark_passes(tmp_path, monkeypatch):
    domain = '[[concept]]\nword = "impl"\nmeaning = "a private implementation module"\npos = ["noun"]\n'
    repo = _repo(tmp_path, domain)
    _added(monkeypatch, repo, {"src/impl_.py": "pass\n"}, existing=["src/existing.py"])
    assert vocabulary_path.check(repo, True, []) == []


def test_five_word_segment_blocks_on_the_word_cap(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/frame_frame_frame_frame_frame.py": "pass\n"},
           existing=["src/existing.py"])
    found = vocabulary_path.check(repo, True, [])
    assert [f.detail for f in found] == ["5 words; a name has 1 to 4"]


def test_four_word_segment_of_known_nouns_passes(tmp_path, monkeypatch):
    domain = '[[concept]]\nword = "buffer"\nmeaning = "a holding area"\npos = ["noun"]\n'
    repo = _repo(tmp_path, domain)
    _added(monkeypatch, repo, {"src/frame_frame_frame_buffer.py": "pass\n"},
           existing=["src/existing.py"])
    assert vocabulary_path.check(repo, True, []) == []


def test_a_leading_underscore_directory_segment_blocks(tmp_path, monkeypatch):
    domain = '[[concept]]\nword = "frob"\nmeaning = "a stand-in name used in a fixture"\npos = ["noun"]\n'
    repo = _repo(tmp_path, domain)
    _added(monkeypatch, repo, {"_frob/thing.py": "pass\n"}, existing=None)
    found = vocabulary_path.check(repo, True, [])
    assert [(f.segment, f.rule, f.suggestion) for f in found if f.segment == "_frob"] == [
        ("_frob", "leading_underscore", "frob_")
    ]


def test_a_file_declaring_an_unrelated_class_does_not_take_the_type_mold(tmp_path, monkeypatch):
    domain = (
        '[[concept]]\nword = "move"\nmeaning = "change position over time"\n'
        'pos = ["verb"]\nforms = ["-ing"]\n\n'
        '[[concept]]\nword = "average"\nmeaning = "the mean value"\npos = ["noun"]\n'
    )
    repo = _repo(tmp_path, domain)
    _added(monkeypatch, repo, {"src/moving_average.py": "class Other:\n    pass\n"},
           existing=["src/existing.py"])
    found = vocabulary_path.check(repo, True, [])
    assert [(f.kind, f.detail) for f in found] == [("namespace", "a namespace takes nouns only")]


def test_editing_an_existing_badly_named_file_adds_no_finding(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.setattr(vocabulary_path, "git", _fake_git(cached=[]))
    assert vocabulary_path.check(repo, True, []) == []


def test_a_new_directory_is_checked_the_same_as_the_file_in_it(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"frob/thing.py": "pass\n"}, existing=None)
    found = vocabulary_path.check(repo, True, [])
    assert [(f.segment, f.kind, f.name, f.detail) for f in found] == [
        ("frob", "namespace", "frob", "`frob` is not in the dictionary"),
        ("thing.py", "namespace", "thing", "`thing` is not in the dictionary"),
    ]


def test_a_new_file_in_an_already_tracked_directory_checks_only_the_file(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/stuff.py": "pass\n"}, existing=["src/existing.py"])
    found = vocabulary_path.check(repo, True, [])
    assert [f.segment for f in found] == ["stuff.py"]


def test_a_dotdir_segment_blocks_the_file_under_it_from_being_checked_too(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/.cache/thing.py": "pass\n"}, existing=["src/existing.py"])
    assert vocabulary_path.check(repo, True, []) == []


def test_a_pattern_exempt_directory_still_lets_the_file_under_it_be_checked(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/__pycache__/thing.py": "pass\n"}, existing=["src/existing.py"])
    found = vocabulary_path.check(repo, True, [])
    assert [f.name for f in found] == ["thing"]


def test_a_waived_middle_segment_still_lets_the_last_segment_be_checked(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/frob/thing.py": "pass\n"}, existing=["src/existing.py"])
    waiver = Waiver(check="vocabulary-path", file="src/frob/thing.py", line=2,
                    reason="third-party naming")
    found = vocabulary_path.check(repo, True, [waiver])
    assert [f.name for f in found] == ["thing"]


def test_stem_matching_a_gerund_class_passes_the_type_mold_not_the_namespace_mold(tmp_path, monkeypatch):
    domain = (
        '[[concept]]\nword = "move"\nmeaning = "change position over time"\n'
        'pos = ["verb"]\nforms = ["-ing"]\n\n'
        '[[concept]]\nword = "average"\nmeaning = "the mean value"\npos = ["noun"]\n'
    )
    repo = _repo(tmp_path, domain)
    _added(monkeypatch, repo, {"src/moving_average.py": "class MovingAverage:\n    pass\n"},
           existing=["src/existing.py"])
    assert vocabulary_path.check(repo, True, []) == []


def test_stem_not_matching_any_declared_class_takes_the_namespace_mold(tmp_path, monkeypatch):
    domain = (
        '[[concept]]\nword = "move"\nmeaning = "change position over time"\n'
        'pos = ["verb"]\nforms = ["-ing"]\n\n'
        '[[concept]]\nword = "average"\nmeaning = "the mean value"\npos = ["noun"]\n'
    )
    repo = _repo(tmp_path, domain)
    _added(monkeypatch, repo, {"src/moving_average.py": "pass\n"}, existing=["src/existing.py"])
    found = vocabulary_path.check(repo, True, [])
    assert [(f.kind, f.detail) for f in found] == [("namespace", "a namespace takes nouns only")]


def test_waiver_keyed_on_check_file_and_segment_clears_the_finding(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/stuff.py": "pass\n"}, existing=["src/existing.py"])
    waiver = Waiver(check="vocabulary-path", file="src/stuff.py", line=2,
                    reason="third-party naming")
    assert vocabulary_path.check(repo, True, [waiver]) == []
    assert vocabulary_path.check(repo, True, []) != []


def test_check_never_loads_the_dictionary_when_nothing_was_added(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.setattr(vocabulary_path, "git", _fake_git(cached=[]))

    def boom(*a, **k):
        raise AssertionError("vocabulary.load must not run when nothing was added")

    monkeypatch.setattr(vocabulary_path.vocabulary, "load", boom)
    assert vocabulary_path.check(repo, True, []) == []


def test_excluded_path_is_not_inspected(tmp_path, monkeypatch):
    config = Config(vocabulary=".vocabulary.toml", exclude_paths=["third_party/"])
    repo = _repo(tmp_path, config=config)
    _added(monkeypatch, repo, {"third_party/frob.py": "pass\n"}, existing=None)
    assert vocabulary_path.check(repo, True, []) == []


def test_worktree_mode_reads_the_index_as_the_pre_image(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _write(repo.root, "src/stuff.py", "pass\n")
    monkeypatch.setattr(vocabulary_path, "git", _fake_git(
        cached=[], worktree=["src/stuff.py"], ls_files=["src/existing.py", "src/stuff.py"]))
    assert vocabulary_path.added_paths(repo, False) == ["src/stuff.py"]
    found = vocabulary_path.check(repo, False, [])
    assert [f.segment for f in found] == ["stuff.py"]
    assert vocabulary_path.check(repo, True, []) == []


def test_worktree_intent_to_add_does_not_hide_a_genuinely_new_directory(tmp_path, monkeypatch):
    """`git add -N` seeds an index entry, so a real `git ls-files` lists the
    intent-added file itself; the new directory it lives in must still be
    checked, not read back as pre-existing because of its own placeholder."""
    repo = _repo(tmp_path)
    _write(repo.root, "frob/thing.py", "pass\n")
    monkeypatch.setattr(vocabulary_path, "git", _fake_git(
        cached=[], worktree=["frob/thing.py"], ls_files=["frob/thing.py"]))
    found = vocabulary_path.check(repo, False, [])
    assert [f.name for f in found] == ["frob", "thing"]


def test_worktree_drops_every_intent_to_add_entry_not_only_the_first(tmp_path, monkeypatch):
    """Two intent-added files in one `ls-files` listing: dropping only the
    first (an off-by-one toward `break`) would leave `src` looking untracked
    and wrongly flag it as new."""
    repo = _repo(tmp_path)
    _write(repo.root, "frob/thing.py", "pass\n")
    _write(repo.root, "src/stuff.py", "pass\n")
    monkeypatch.setattr(vocabulary_path, "git", _fake_git(
        cached=[], worktree=["frob/thing.py", "src/stuff.py"],
        ls_files=["frob/thing.py", "src/existing.py", "src/stuff.py"]))
    found = vocabulary_path.check(repo, False, [])
    assert [f.segment for f in found] == ["frob", "thing.py", "stuff.py"]


def test_suggested_waiver_names_the_check_and_file(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"frob.py": "pass\n"}, existing=None)
    found = vocabulary_path.check(repo, True, [])
    text = vocabulary_path.suggest(repo, found[0])
    assert 'check = "vocabulary-path"' in text
    assert 'file = "frob.py"' in text


def test_describe_reports_the_file_kind_name_and_suggestion(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _added(monkeypatch, repo, {"src/_impl.py": "pass\n"}, existing=["src/existing.py"])
    found = vocabulary_path.check(repo, True, [])
    leading = next(f for f in found if f.suggestion)
    assert vocabulary_path.describe(leading) == (
        "src/_impl.py: namespace `_impl` — a leading `_` is not the private mark; "
        "private is a trailing `_` — try `impl_.py`"
    )


def _no_git(*args: str, cwd=None) -> str:
    raise GateError("git: not in the test image")


def _cli(monkeypatch, tmp_path: Path, repo: Repo) -> int:
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli.model_vv, "git", _no_git)
    monkeypatch.setattr(cli, "_gate_file", lambda *a, **k: (False, [], []))
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {})
    for mod in (cli, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")
    return cli.main(["--staged", "--no-adversary"])


def test_slice_cli_main_staged_passes_a_class_named_file(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    _write(repo.root, ".mutation-gate.toml", 'vocabulary = ".vocabulary.toml"\n')
    _added(monkeypatch, repo, {"src/frame_parser.py": "class FrameParser:\n    pass\n"},
           existing=["src/existing.py"])
    assert _cli(monkeypatch, tmp_path, repo) == 0
    assert "BLOCKED: vocabulary-path" not in capsys.readouterr().err


def test_slice_cli_main_staged_blocks_an_unknown_word_in_a_file_name(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    _write(repo.root, ".mutation-gate.toml", 'vocabulary = ".vocabulary.toml"\n')
    _added(monkeypatch, repo, {"src/parse_stuff.py": "pass\n"}, existing=["src/existing.py"])
    assert _cli(monkeypatch, tmp_path, repo) == 1
    err = capsys.readouterr().err
    assert "BLOCKED: vocabulary-path — 2 finding(s)." in err
    assert "src/parse_stuff.py: namespace `parse_stuff` — `stuff` is not in the dictionary" in err
    assert "src/parse_stuff.py: namespace `parse_stuff` — a namespace takes nouns only" in err


def test_slice_cli_main_refuses_with_exit_2_on_a_gate_error(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    _write(repo.root, ".mutation-gate.toml", 'vocabulary = ".vocabulary.toml"\n')

    def boom(*a, **k):
        raise GateError("ast-grep is not on PATH")

    monkeypatch.setattr(vocabulary_path, "check", boom)
    assert _cli(monkeypatch, tmp_path, repo) == 2
    assert "mutation-gate refused: ast-grep is not on PATH" in capsys.readouterr().err


def test_slice_cli_main_suggestion_names_the_first_added_file_not_the_second(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    _write(repo.root, ".mutation-gate.toml", 'vocabulary = ".vocabulary.toml"\n')
    _added(monkeypatch, repo, {"src/frob.py": "pass\n", "src/zork.py": "pass\n"},
           existing=["src/existing.py"])
    assert _cli(monkeypatch, tmp_path, repo) == 1
    err = capsys.readouterr().err
    assert 'file = "src/frob.py"' in err
    assert 'file = "src/zork.py"' not in err


@pytest.mark.skipif(shutil.which("git") is None,
                    reason="needs a real git binary; the gate's own test image has none")
def test_real_git_repo_frame_parser_passes_and_parse_stuff_blocks(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "src").mkdir()
    (root / "src" / "existing.py").write_text("pass\n")
    subprocess.run(["git", "add", "src/existing.py"], cwd=root, check=True)
    subprocess.run(["git", *_GIT_IDENTITY, "commit", "-q", "-m", "init"], cwd=root, check=True)
    _write(root, ".vocabulary.toml", "")
    _write(root, ".mutation-gate.toml", 'vocabulary = ".vocabulary.toml"\n')
    monkeypatch.chdir(root)
    monkeypatch.setattr(cli, "_gate_file", lambda *a, **k: (False, [], []))
    for mod in (cli, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")

    (root / "src" / "frame_parser.py").write_text("class FrameParser:\n    pass\n")
    subprocess.run(["git", "add", "src/frame_parser.py"], cwd=root, check=True)
    assert cli.main(["--staged", "--no-adversary"]) == 0

    subprocess.run(["git", "reset"], cwd=root, check=True)
    (root / "src" / "parse_stuff.py").write_text("pass\n")
    subprocess.run(["git", "add", "src/parse_stuff.py"], cwd=root, check=True)
    assert cli.main(["--staged", "--no-adversary"]) == 1
    err = capsys.readouterr().err
    assert "BLOCKED: vocabulary-path — 2 finding(s)." in err
    assert "`stuff` is not in the dictionary" in err

    subprocess.run(["git", *_GIT_IDENTITY, "commit", "-q", "-m", "add parse_stuff"],
                   cwd=root, check=True)
    (root / "src" / "parse_stuff.py").write_text("pass\npass\n")
    subprocess.run(["git", "add", "src/parse_stuff.py"], cwd=root, check=True)
    assert vocabulary_path.added_paths(Repo(root=root, origin="", remotes=(), config=Config()),
                                       True) == []
    assert cli.main(["--staged", "--no-adversary"]) == 0
    assert "a namespace takes nouns only" in err


VENDORED_STANDARD_SCRIPT = '''
# Built-in exception filenames (exact match, case-sensitive)
BUILTIN_EXEMPT_FILES=(
    "CMakeLists.txt"
    "Dockerfile"
    "README.md"
    "CLAUDE.md"
    "CHANGELOG.md"
    "CONTRIBUTING.md"
    "LICENSE"
    "Makefile"
    "Doxyfile"
    "package.xml"
    "pyproject.toml"
    "setup.py"
    "setup.cfg"
    "Cargo.toml"
    "Cargo.lock"
)

# Built-in exception filename patterns (regex, matched against filename)
BUILTIN_EXEMPT_PATTERNS=(
    '^requirements.*\\.txt$'
    '^\\.'                           # dotfiles (.gitignore, .clang-tidy, etc.)
    '^__init__\\.py$'
    '^__main__\\.py$'
    '^__pycache__$'
    '^py\\.typed$'
    '^[A-Z][A-Z_-]*\\.md$'          # ALL-CAPS markdown files (TESTING.md, SECURITY.md, etc.)
)

# Built-in exception path prefixes (matched against full path)
BUILTIN_EXEMPT_PATH_PATTERNS=(
    '^\\.'                           # dotdirs (.github/, .vscode/, etc.)
)
'''


def _bash_array(text: str, name: str) -> list[str]:
    block = re.search(rf"{name}=\((.*?)\n\)", text, re.S).group(1)
    return re.findall(r'''["']([^"']+)["']''', block)


def test_core_path_exemptions_match_the_vendored_standard_script_text():
    assert vocabulary_path.EXEMPT_FILES == frozenset(
        _bash_array(VENDORED_STANDARD_SCRIPT, "BUILTIN_EXEMPT_FILES"))
    assert [p.pattern for p in vocabulary_path.EXEMPT_PATTERNS] == _bash_array(
        VENDORED_STANDARD_SCRIPT, "BUILTIN_EXEMPT_PATTERNS")
    assert [p.pattern for p in vocabulary_path.EXEMPT_PATH_PATTERNS] == _bash_array(
        VENDORED_STANDARD_SCRIPT, "BUILTIN_EXEMPT_PATH_PATTERNS")
