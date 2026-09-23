"""Intent: #105 (decisions 1, 2, 11, 15, 18, 22, 26, 33, 34 of #103) — with
`vocabulary = "<path>"` set, a name a diff declares must be built from dictionary
words and spell private as a trailing `_`; references, dunders, `override`/`final`,
`@override`, the core convention list and excluded paths are never findings; a
`[symbol]` word passes only as a local or parameter; every finding suggests a name.

Driven through cli.main as the no-comments slice is: discover and the diff are
stubbed, the config load, the dictionary, the ast-grep scan, the waiver match and
the exit code are real."""

import subprocess
from pathlib import Path

import pytest

from mutation_gate import cli, mutants, runner, token, vocabulary, vocabulary_check
from mutation_gate.repo import Config, GateError, Repo
from mutation_gate.waivers import Waiver

DOMAIN = ".vocabulary.toml"
OPTED_IN = f'vocabulary = "{DOMAIN}"\n'
LOC = '[reject]\nloc = "position"\n'
PARSE = '[[concept]]\nword = "parse"\nmeaning = "turn text into a structure"\npos = ["verb"]\n'
Q_SYMBOL = '[[symbol]]\nword = "Q"\nmeaning = "process noise covariance"\n'


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _repo(tmp_path: Path, toml: str, files: dict[str, str], domain: str = LOC) -> Repo:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    _write(root, ".mutation-gate.toml", toml)
    _write(root, DOMAIN, domain)
    for rel, text in files.items():
        _write(root, rel, text)
    return Repo(root=root, origin="", remotes=(), config=Config.load(root))


def _no_git(*args: str, cwd=None) -> str:
    raise GateError("git: not in the test image")


def _gate(monkeypatch, tmp_path: Path, repo: Repo, added: dict[str, set[int]]) -> int:
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli.model_vv, "git", _no_git)
    monkeypatch.setattr(cli, "_gate_file", lambda *a, **k: (False, [], []))
    monkeypatch.setattr(mutants, "changed_lines", lambda root, staged: added)
    for mod in (cli, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")
    return cli.main(["--staged", "--no-adversary"])


def test_staged_loc_assignment_blocks_and_suggests_position(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "loc = 1\n"})
    code = _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {1}})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary" in err
    assert "pkg/a.py:1: variable `loc`" in err
    assert "try `position`" in err


def test_staged_use_of_an_existing_loc_passes(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "loc = 1\nprint(loc)\n"})
    assert _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {2}}) == 0


def test_cpp_override_method_passes_without_a_dictionary_word(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"src/k.hpp": "class K {\n  void on_configure() override;\n};\n"})
    assert _gate(monkeypatch, tmp_path, repo, {"src/k.hpp": {2}}) == 0


def test_cpp_field_named_q_blocks_as_a_symbol_outside_a_local(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"src/k.hpp": "class K {\n  int Q;\n};\n"}, Q_SYMBOL)
    code = _gate(monkeypatch, tmp_path, repo, {"src/k.hpp": {2}})
    err = capsys.readouterr().err
    assert code == 1
    assert "src/k.hpp:2: field `Q`" in err
    assert "locals and parameters only" in err


def test_cpp_local_named_q_passes_with_q_in_symbol(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"src/k.cpp": "void f() {\n  int Q = 1;\n}\n"}, Q_SYMBOL)
    assert _gate(monkeypatch, tmp_path, repo, {"src/k.cpp": {2}}) == 0


def test_python_leading_underscore_def_blocks_suggesting_trailing_form(
    tmp_path, monkeypatch, capsys
):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "def _parse_frame():\n    pass\n"}, PARSE)
    code = _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {1, 2}})
    err = capsys.readouterr().err
    assert code == 1
    assert "pkg/a.py:1: function `_parse_frame`" in err
    assert "try `parse_frame_`" in err


def test_python_trailing_underscore_def_and_dunder_pass(tmp_path, monkeypatch):
    text = "class Frame:\n    def __init__(self):\n        pass\n\n    def parse_frame_(self):\n        pass\n"
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": text}, PARSE)
    assert _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {1, 2, 3, 4, 5, 6}}) == 0


def test_cpp_leading_underscore_member_blocks_suggesting_count_(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"src/k.hpp": "class K {\n  int _count;\n};\n"})
    code = _gate(monkeypatch, tmp_path, repo, {"src/k.hpp": {2}})
    err = capsys.readouterr().err
    assert code == 1
    assert "src/k.hpp:2: field `_count`" in err
    assert "try `count_`" in err


def test_key_unset_runs_nothing(tmp_path, monkeypatch):
    repo = _repo(tmp_path, "", {"pkg/a.py": "loc = 1\n"})
    monkeypatch.setattr(vocabulary_check, "declarations", lambda *a: pytest.fail("scanned"))
    assert repo.config.vocabulary == ""
    assert _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {1}}) == 0


def test_broken_domain_file_refuses_with_exit_2(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "x = 1\n"}, '[[concept]]\nword = "frob"\n')
    code = _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {1}})
    assert code == 2
    assert "mutation-gate refused" in capsys.readouterr().err


def test_waiver_keyed_on_check_file_and_line_clears_the_finding(tmp_path, monkeypatch):
    waivers_toml = (f'[[waiver]]\ncheck = "vocabulary"\nfile = "pkg/a.py"\nline = 1\n'
                    'reason = "the fixture name is dictated by a third-party plugin API"\n')
    repo = _repo(tmp_path, OPTED_IN,
                 {"pkg/a.py": "loc = 1\n", ".mutation-gate-waivers.toml": waivers_toml})
    assert _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {1}}) == 0


def test_suggested_waiver_names_the_check_file_and_line(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "loc = 1\n"})
    _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {1}})
    err = capsys.readouterr().err
    assert 'check = "vocabulary"\nfile = "pkg/a.py"\nline = 1\n' in err
    assert DOMAIN in err


def _findings(tmp_path, rel: str, text: str, lines: set[int], domain: str = LOC,
              toml: str = OPTED_IN, wvs=()) -> list[str]:
    repo = _repo(tmp_path, toml, {rel: text}, domain)
    found = vocabulary_check.check(repo, {rel: lines}, list(wvs))
    return [f"{f.line}:{f.kind}:{f.name}:{f.detail}:{f.suggestion}" for f in found]


def test_declaration_on_an_unchanged_line_is_not_checked(tmp_path):
    assert _findings(tmp_path, "pkg/a.py", "loc = 1\nframe = 2\n", {2}) == []


def test_unknown_word_blocks_naming_the_word(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "frob = 1\n", {1})
    assert found == ["1:variable:frob:`frob` is not in the dictionary:"]


def test_vague_word_blocks_with_its_hint(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "class FrameManager:\n    pass\n", {1})
    assert found == [
        "1:type:FrameManager:`Manager` is vague — name what it does: scheduler, registry, pool, cache:"
    ]


def test_rejected_function_word_blocks_with_its_hint_and_no_rename(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "def read_and_parse():\n    pass\n", {1}, PARSE)
    assert found == ["1:function:read_and_parse:`and`: one action per name: split the function, "
                     "or name the combined step:"]


@pytest.mark.parametrize("name, word, suggestion", [
    ("frameLoc", "Loc", "framePosition"),
    ("FRAME_LOC", "LOC", "FRAME_POSITION"),
    ("Loc", "Loc", "Position"),
    ("loc_count", "loc", "position_count"),
])
def test_rejected_word_rename_keeps_the_case_style(tmp_path, name, word, suggestion):
    found = _findings(tmp_path, "pkg/a.py", f"{name} = 1\n", {1})
    assert found == [f"1:variable:{name}:`{word}`: loc is a rejected synonym of position:{suggestion}"]


def test_leading_underscore_and_unknown_word_are_separate_findings(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "_frob = 1\n", {1})
    assert found == [
        "1:variable:_frob:a leading `_` is not the private mark; private is a trailing `_`:frob_",
        "1:variable:_frob:`frob` is not in the dictionary:",
    ]


@pytest.mark.parametrize("name", ["_", "__slots__", "self", "cls", "main", "kwargs", "tmp_path"])
def test_bare_underscore_dunder_and_convention_names_are_exempt(tmp_path, name):
    assert _findings(tmp_path, "pkg/a.py", f"{name} = 1\n", {1}) == []


def test_name_mangled_double_underscore_is_not_a_dunder(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "class A:\n    __count = 1\n", {2})
    assert [f.split(":", 4)[4] for f in found] == ["count_"]


@pytest.mark.parametrize("decorator", ["@override", "@typing.override"])
def test_override_decorator_exempts_the_python_method(tmp_path, decorator):
    text = f"class Frame:\n    {decorator}\n    def frob(self):\n        pass\n"
    assert _findings(tmp_path, "pkg/a.py", text, {1, 2, 3, 4}) == []


def test_python_method_without_override_is_checked(tmp_path):
    text = "class Frame:\n    @property\n    def frob(self):\n        pass\n"
    assert [f.split(":")[2] for f in _findings(tmp_path, "pkg/a.py", text, {1, 2, 3, 4})] == ["frob"]


def test_cpp_final_method_is_exempt_and_plain_method_is_not(tmp_path):
    text = "class K {\n  void frob() final;\n  void frobnicate();\n};\n"
    found = _findings(tmp_path, "src/k.hpp", text, {2, 3})
    assert [f.split(":")[:3] for f in found] == [["3", "method", "frobnicate"]]


def test_python_class_body_assignment_is_a_field_and_self_attribute_too(tmp_path):
    text = "class A:\n    Q = 1\n\n    def __init__(self):\n        self.Q = 2\n"
    found = _findings(tmp_path, "pkg/a.py", text, {2, 5}, Q_SYMBOL)
    assert [f.split(":")[:3] for f in found] == [["2", "field", "Q"], ["5", "field", "Q"]]


def test_python_local_and_parameter_take_a_symbol(tmp_path):
    text = "def read(Q, n=1, *args, **kwargs):\n    Q = n\n    return Q\n"
    assert _findings(tmp_path, "pkg/a.py", text, {1, 2, 3}, Q_SYMBOL) == []


def test_python_parameter_and_local_are_declarations(tmp_path):
    text = "def read(loc, idx: int = 1):\n    pos = loc\n    return pos\n"
    found = _findings(tmp_path, "pkg/a.py", text, {1, 2, 3})
    assert [f.split(":")[:3] for f in found] == [
        ["1", "parameter", "idx"], ["1", "parameter", "loc"], ["2", "local", "pos"]
    ]


def test_cpp_parameter_takes_a_symbol(tmp_path):
    assert _findings(tmp_path, "src/k.cpp", "void read(double Q);\n", {1}, Q_SYMBOL) == []


def test_lower_case_symbol_spelling_matches_the_symbol_table(tmp_path):
    assert _findings(tmp_path, "pkg/a.py", "def read(X):\n    return X\n", {1}) == []


def test_module_variable_named_by_a_symbol_blocks(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "x = 1\n", {1})
    assert found == ["1:variable:x:`x`: first axis coordinate; locals and parameters only:"]


def test_cpp_declaration_kinds_are_told_apart(tmp_path):
    text = ("namespace frob {\n"
            "enum class Frob { frobbed };\n"
            "int frobs = 1;\n"
            "int frob_count(int frobbing, char** argv) {\n"
            "  double* frobbed = nullptr;\n"
            "  return frobs;\n"
            "}\n"
            "}\n")
    found = _findings(tmp_path, "src/k.cpp", text, set(range(1, 9)))
    assert [f.split(":")[:3] for f in found] == [
        ["1", "namespace", "frob"],
        ["2", "enumerator", "frobbed"],
        ["2", "type", "Frob"],
        ["3", "variable", "frobs"],
        ["4", "function", "frob_count"],
        ["4", "parameter", "frobbing"],
        ["5", "local", "frobbed"],
    ]


def test_cpp_header_is_read_as_cpp_not_c(tmp_path):
    assert [f.split(":")[:3] for f in _findings(tmp_path, "src/k.h", "int frob = 1;\n", {1})] == [
        ["1", "variable", "frob"]
    ]


def test_excluded_path_is_not_inspected(tmp_path):
    toml = OPTED_IN + 'exclude_paths = ["third_party/"]\n'
    assert _findings(tmp_path, "third_party/v.py", "loc = 1\n", {1}, toml=toml) == []


def test_excluded_file_does_not_hide_the_file_after_it(tmp_path):
    toml = OPTED_IN + 'exclude_paths = ["a_vendored/"]\n'
    repo = _repo(tmp_path, toml, {"a_vendored/v.py": "loc = 1\n", "pkg/a.py": "loc = 1\n"})
    found = vocabulary_check.check(repo, {"a_vendored/v.py": {1}, "pkg/a.py": {1}}, [])
    assert [(f.file, f.line) for f in found] == [("pkg/a.py", 1)]


def test_waiver_on_another_line_does_not_cover_this_one(tmp_path):
    waiver = Waiver(check="vocabulary", file="pkg/a.py", line=1, reason="fixture")
    found = _findings(tmp_path, "pkg/a.py", "loc = 1\nidx = 2\n", {1, 2}, wvs=[waiver])
    assert [f.split(":")[:3] for f in found] == [["2", "variable", "idx"]]


def test_failed_scan_refuses_instead_of_passing(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("frame = 1\n")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 8, stdout="", stderr="Cannot parse rule"))
    with pytest.raises(GateError, match="Cannot parse rule"):
        vocabulary_check.declarations(tmp_path / "a.py", "python")


@pytest.mark.parametrize("name, expected", [
    ("parse_frame_", ["parse", "frame"]),
    ("frame__", ["frame"]),
    ("parseFrame", ["parse", "Frame"]),
    ("HTTPServer", ["HTTP", "Server"]),
    ("sha256_digest", ["sha256", "digest"]),
    ("Frame2D", ["Frame2D"]),
    ("Q_k", ["Q", "k"]),
    ("__init__", ["init"]),
])
def test_name_splits_on_case_and_underscore_with_digit_chunks_whole(name, expected):
    assert vocabulary_check.words(name) == expected


def test_core_convention_list_is_loaded_from_the_packaged_core(tmp_path):
    dictionary = vocabulary.load(tmp_path, "")
    assert {"main", "self", "setUp", "monkeypatch"} <= dictionary.conventions
