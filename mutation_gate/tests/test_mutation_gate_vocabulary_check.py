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
from conftest import (
    GDSCRIPT_BROKEN_SGCONFIG,
    GDSCRIPT_SGCONFIG,
    require_gdscript_parser as _require_gdscript_parser,
)

from mutation_gate import cli, mutants, runner, token, vocabulary, vocabulary_check, vocabulary_path
from mutation_gate.repo import Config, GateError, Repo
from mutation_gate.waivers import Waiver

DOMAIN = ".vocabulary.toml"
OPTED_IN = f'vocabulary = "{DOMAIN}"\n'
LOC = '[reject]\nloc = "position"\n'
Q_SYMBOL = '[[symbol]]\nword = "Q"\nmeaning = "process noise covariance"\n'
GODOT_ENGINE_VIRTUALS = [
    "_init", "_get", "_set", "_get_property_list", "_to_string", "_notification",
    "_iter_get", "_iter_init", "_iter_next", "_property_can_revert", "_property_get_revert",
    "_validate_property",
    "_enter_tree", "_exit_tree", "_ready", "_process", "_physics_process", "_input",
    "_unhandled_input", "_unhandled_key_input", "_shortcut_input", "_get_configuration_warnings",
    "_get_accessibility_configuration_warnings", "_get_focused_accessibility_element",
    "_draw",
    "_gui_input", "_can_drop_data", "_drop_data", "_get_drag_data", "_get_cursor_shape",
    "_get_minimum_size", "_get_maximum_size", "_get_tooltip", "_has_point",
    "_make_custom_tooltip", "_structured_text_parser", "_accessibility_get_contextual_info",
    "_get_accessibility_container_name", "_get_tooltip_auto_translate_mode_at",
]


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
    monkeypatch.setattr(cli.vocabulary_path, "git", lambda *a, **k: "")
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


def test_staged_vague_word_declaration_shows_its_hint_as_the_suggestion(
    tmp_path, monkeypatch, capsys
):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "manager = 1\n"})
    code = _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {1}})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert ("  pkg/a.py:1: variable `manager` — `manager` is vague — try "
            "`name what it does: scheduler, registry, pool, cache`") in err.splitlines()


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
    assert "try `spell out what the symbol stands for, or make it a local/parameter`" in err


def test_cpp_local_named_q_passes_with_q_in_symbol(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"src/k.cpp": "void f() {\n  int Q = 1;\n}\n"}, Q_SYMBOL)
    assert _gate(monkeypatch, tmp_path, repo, {"src/k.cpp": {2}}) == 0


def test_python_leading_underscore_def_blocks_suggesting_trailing_form(
    tmp_path, monkeypatch, capsys
):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "def _parse_frame():\n    pass\n"})
    code = _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {1, 2}})
    err = capsys.readouterr().err
    assert code == 1
    assert "pkg/a.py:1: function `_parse_frame`" in err
    assert "try `parse_frame_`" in err


def test_python_trailing_underscore_def_and_dunder_pass(tmp_path, monkeypatch):
    text = "class Frame:\n    def __init__(self):\n        pass\n\n    def parse_frame_(self):\n        pass\n"
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": text})
    assert _gate(monkeypatch, tmp_path, repo, {"pkg/a.py": {1, 2, 3, 4, 5, 6}}) == 0


def test_cpp_leading_underscore_member_blocks_suggesting_count_(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"src/k.hpp": "class K {\n  int _count;\n};\n"})
    code = _gate(monkeypatch, tmp_path, repo, {"src/k.hpp": {2}})
    err = capsys.readouterr().err
    assert code == 1
    assert "src/k.hpp:2: field `_count`" in err
    assert "try `count_`" in err


def test_staged_test_function_of_core_words_passes(tmp_path, monkeypatch):
    repo = _repo(tmp_path, OPTED_IN, {"tests/test_a.py": "def test_empty_frame_reads():\n    pass\n"})
    assert _gate(monkeypatch, tmp_path, repo, {"tests/test_a.py": {1, 2}}) == 0


def test_staged_test_function_with_an_unknown_word_blocks(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"tests/test_a.py": "def test_frob_frame():\n    pass\n"})
    code = _gate(monkeypatch, tmp_path, repo, {"tests/test_a.py": {1, 2}})
    err = capsys.readouterr().err
    assert code == 1
    assert "tests/test_a.py:1: function `test_frob_frame` — `frob` is not in the dictionary" in err


def test_lookup_test_answers_noun_and_verb_from_the_core(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vocabulary, "discover", lambda cwd=None: Repo(
        root=tmp_path, origin="", remotes=(), config=Config()))
    assert cli.main(["vocabulary", "lookup", "test"]) == 0
    assert capsys.readouterr().out.startswith("test: noun, verb\n")


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


def test_vague_word_blocks_with_its_hint_as_the_suggestion(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "class FrameManager:\n    pass\n", {1})
    assert found == [
        "1:type:FrameManager:`Manager` is vague:name what it does: scheduler, registry, pool, cache"
    ]


def test_rejected_function_word_blocks_with_its_hint_and_no_rename(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "def read_and_parse():\n    pass\n", {1})
    assert found == ["1:function:read_and_parse:`and`: one action per name: split the function, "
                     "or name the combined step:"]


@pytest.mark.parametrize("text, rule", [
    ("frob = 1\n", vocabulary_check.RULE_UNKNOWN_WORD),
    ("def read_and_parse():\n    pass\n", vocabulary_check.RULE_FUNCTION_WORD),
    ("def read_or_parse():\n    pass\n", vocabulary_check.RULE_FUNCTION_WORD),
    ("def read_not_parse():\n    pass\n", vocabulary_check.RULE_FUNCTION_WORD),
])
def test_unknown_and_function_word_findings_carry_no_suggestion_by_design(tmp_path, text, rule):
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": text})
    found = vocabulary_check.check(repo, {"pkg/a.py": {1}}, [])
    assert [(f.rule, f.suggestion) for f in found] == [(rule, "")]


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
    assert _findings(tmp_path, "src/k.cpp", "void run(double Q);\n", {1}, Q_SYMBOL) == []


def test_lower_case_symbol_spelling_matches_the_symbol_table(tmp_path):
    assert _findings(tmp_path, "pkg/a.py", "def read(X):\n    return X\n", {1}) == []


def test_module_variable_named_by_a_symbol_blocks(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "x = 1\n", {1})
    assert found == ["1:variable:x:`x`: first axis coordinate; locals and parameters only:"
                     "spell out what the symbol stands for, or make it a local/parameter"]


def test_symbol_scope_spells_out_a_dictionary_noun_phrase_meaning(tmp_path):
    domain = '[[symbol]]\nword = "q"\nmeaning = "Process state"\n'
    found = _findings(tmp_path, "pkg/a.py", "q = 1\n", {1}, domain)
    assert found == ["1:variable:q:`q`: Process state; locals and parameters only:"
                     "process_state"]


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


def test_target_error_reads_first_line_of_error_output(tmp_path, monkeypatch):
    """#202: vocabulary_check.declarations put the whole stderr in the refusal
    instead of its first line, so a multi-line ast-grep error gave a
    multi-line refusal."""
    (tmp_path / "a.py").write_text("frame = 1\n")
    first_line = "Cannot parse rule " + "x" * 200
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 8, stdout="", stderr=f"{first_line}\nsee --help"))
    with pytest.raises(GateError) as excinfo:
        vocabulary_check.declarations(tmp_path / "a.py", "python")
    assert str(excinfo.value).splitlines() == [str(excinfo.value)]
    assert first_line in str(excinfo.value)
    assert "see --help" not in str(excinfo.value)


def test_target_error_uses_status_code_for_empty_output(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("frame = 1\n")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 8, stdout="", stderr=""))
    with pytest.raises(GateError, match=r"exit 8$"):
        vocabulary_check.declarations(tmp_path / "a.py", "python")


def test_target_error_sends_output_to_reader(tmp_path, monkeypatch):
    """#202: one helper backs every ast-grep refusal; this pins declarations'."""
    (tmp_path / "a.py").write_text("frame = 1\n")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 8, stdout="", stderr="boom"))
    monkeypatch.setattr(vocabulary_check.mutants, "render_error_line", lambda result: "stub-line")
    with pytest.raises(GateError, match="stub-line"):
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
    assert {"main", "self", "setUp", "monkeypatch"} <= dictionary.convention_for("python").names


def test_core_convention_list_does_not_leak_python_names_into_gdscript(tmp_path):
    dictionary = vocabulary.load(tmp_path, "")
    leaked = dictionary.convention_for("gdscript").names & (
        dictionary.convention_for("python").names | dictionary.convention_for("cpp").names
    )
    assert leaked == set()


def test_core_convention_list_carries_gdscript_engine_virtuals_and_autoconnect_prefix(tmp_path):
    dictionary = vocabulary.load(tmp_path, "")
    convention = dictionary.convention_for("gdscript")
    assert {"_ready", "_process", "_physics_process", "_input"} <= convention.names
    assert "_on_" in convention.prefixes


@pytest.mark.parametrize("name", GODOT_ENGINE_VIRTUALS)
def test_core_convention_list_carries_every_godot_engine_virtual(tmp_path, name):
    dictionary = vocabulary.load(tmp_path, "")
    assert name in dictionary.convention_for("gdscript").names


def test_lookup_with_no_file_falls_back_to_the_union_across_languages(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vocabulary, "discover", lambda cwd=None: Repo(
        root=tmp_path, origin="", remotes=(), config=Config()))
    assert cli.main(["vocabulary", "lookup", "--kind", "function", "_ready"]) == 0
    assert capsys.readouterr().out == "_ready: fits the function mold\n"


def test_gated_files_drops_non_gated_languages_and_excluded_paths(tmp_path, monkeypatch):
    repo = _repo(tmp_path, 'exclude_paths = ["third_party/"]\n',
                 {"pkg/a.py": "x = 1\n", "src/k.cpp": "int y = 1;\n"})
    listing = "pkg/a.py\0src/k.cpp\0README.md\0third_party/v.py\0"
    monkeypatch.setattr(vocabulary_check, "git", lambda *a, cwd=None: listing)
    assert vocabulary_check.gated_files(repo) == ["pkg/a.py", "src/k.cpp"]


def test_tsx_pascal_case_function_is_checked_as_a_type_not_a_function(tmp_path):
    found = _findings(tmp_path, "ui/a.tsx", "function FrameManager() {}\n", {1})
    assert found == [
        "1:type:FrameManager:`Manager` is vague:name what it does: scheduler, registry, pool, cache"
    ]


def test_tsx_camel_case_function_keeps_the_function_mold_and_blocks_on_an_unknown_word(tmp_path):
    found = _findings(tmp_path, "ui/a.tsx", "function renderStuff() {}\n", {1})
    assert found == ["1:function:renderStuff:`Stuff` is not in the dictionary:"]


def test_tsx_hook_shaped_arrow_function_keeps_the_function_mold(tmp_path):
    assert _findings(tmp_path, "ui/a.tsx", "const useCount = () => {};\n", {1}) == []


def test_tsx_hook_declared_with_the_function_keyword_keeps_the_function_mold(tmp_path):
    assert _findings(tmp_path, "ui/a.tsx", "function useCount() {}\n", {1}) == []


def test_tsx_hook_with_an_unknown_word_blocks_as_a_function_not_a_type(tmp_path):
    found = _findings(tmp_path, "ui/a.tsx", "const useFrob = () => {};\n", {1})
    assert found == ["1:function:useFrob:`Frob` is not in the dictionary:"]


def test_tsx_hook_declared_with_function_keyword_and_an_unknown_word_blocks(tmp_path):
    found = _findings(tmp_path, "ui/a.tsx", "function useFrob() {}\n", {1})
    assert found == ["1:function:useFrob:`Frob` is not in the dictionary:"]


def test_tsx_pascal_case_function_that_passes_is_checked_on_the_type_mold(tmp_path):
    assert _findings(tmp_path, "ui/a.tsx", "function FrameViewer() {}\n", {1}) == []


def test_tsx_pascal_case_arrow_function_is_checked_as_a_type(tmp_path):
    found = _findings(tmp_path, "ui/a.tsx", "const FrameManager = () => {};\n", {1})
    assert found == [
        "1:type:FrameManager:`Manager` is vague:name what it does: scheduler, registry, pool, cache"
    ]


def test_ts_pascal_case_function_stays_on_the_function_mold_outside_tsx(tmp_path):
    found = _findings(tmp_path, "ui/a.ts", "function FrameViewer() {}\n", {1})
    assert [f.split(":")[:2] for f in found] == [["1", "function"]]


def test_tsx_pascal_case_function_ending_in_ing_blocks_as_a_type(tmp_path):
    found = _findings(tmp_path, "ui/a.tsx", "function FrameParsing() {}\n", {1})
    assert found == [
        "1:type:FrameParsing:a type takes a noun phrase ending in a noun, never an -ing form:"
        "ParsingFrame"
    ]


def test_ts_interface_i_prefix_blocks_as_a_non_local_symbol(tmp_path):
    found = _findings(tmp_path, "ui/a.ts", "interface IFrame {}\n", {1})
    assert found == ["1:type:IFrame:`I`: loop index; locals and parameters only:"
                     "spell out what the symbol stands for, or make it a local/parameter"]


def test_ts_private_keyword_leading_underscore_blocks_suggesting_trailing_form(tmp_path):
    text = "class Frame {\n  private _count: number;\n}\n"
    assert _findings(tmp_path, "ui/a.ts", text, {2}) == [
        "2:field:_count:a leading `_` is not the private mark; private is a trailing `_`:count_"
    ]


def test_ts_hash_private_member_without_trailing_underscore_blocks(tmp_path):
    text = "class Frame {\n  #count: number;\n}\n"
    assert _findings(tmp_path, "ui/a.ts", text, {2}) == [
        "2:field:#count:a private member takes a trailing `_`:#count_"
    ]


def test_ts_private_keyword_field_with_no_underscore_at_all_blocks_suggesting_trailing(tmp_path):
    text = "class Frame {\n  private count: number;\n}\n"
    assert _findings(tmp_path, "ui/a.ts", text, {2}) == [
        "2:field:count:a private member takes a trailing `_`:count_"
    ]


@pytest.mark.parametrize("field", ["private count_: number;", "#count_: number;"])
def test_ts_private_member_with_trailing_underscore_passes(tmp_path, field):
    text = f"class Frame {{\n  {field}\n}}\n"
    assert _findings(tmp_path, "ui/a.ts", text, {2}) == []


@pytest.mark.parametrize("method, name", [
    ("private run(): void {}", "run"), ("#run(): void {}", "#run"),
])
def test_ts_private_method_without_trailing_underscore_blocks(tmp_path, method, name):
    text = f"class Frame {{\n  {method}\n}}\n"
    assert _findings(tmp_path, "ui/a.ts", text, {2}) == [
        f"2:method:{name}:a private member takes a trailing `_`:{name}_"
    ]


@pytest.mark.parametrize("method", ["private run_(): void {}", "#run_(): void {}"])
def test_ts_private_method_with_trailing_underscore_passes(tmp_path, method):
    text = f"class Frame {{\n  {method}\n}}\n"
    assert _findings(tmp_path, "ui/a.ts", text, {2}) == []


def test_ts_private_method_leaves_the_getter_and_setter_alone(tmp_path):
    text = ("class Frame {\n  get count(): number { return 1; }\n"
            "  set count(v: number) {}\n}\n")
    assert _findings(tmp_path, "ui/a.ts", text, {2, 3}) == []


def test_ts_getter_takes_the_variable_mold_and_setter_is_exempt(tmp_path):
    text = "class Frame {\n  get count(): number { return 1; }\n  set count(v: number) {}\n}\n"
    assert _findings(tmp_path, "ui/a.ts", text, {2, 3}) == []


def test_ts_getter_with_an_unknown_word_blocks(tmp_path):
    text = "class Frame {\n  get frob(): number { return 1; }\n}\n"
    found = _findings(tmp_path, "ui/a.ts", text, {2})
    assert found == ["2:property:frob:`frob` is not in the dictionary:"]


def test_ts_getter_with_a_misordered_head_noun_blocks_on_the_property_mold(tmp_path):
    text = "class Frame {\n  get countTarget(): number { return 1; }\n}\n"
    found = _findings(tmp_path, "ui/a.ts", text, {2})
    assert found == [
        "2:property:countTarget:`count` is a head noun: last in its noun phrase, or last "
        "before a prepositional tail:targetCount"
    ]


def test_ts_setter_with_an_unknown_word_is_still_exempt(tmp_path):
    text = "class Frame {\n  get count(): number { return 1; }\n  set frob(v: number) {}\n}\n"
    assert _findings(tmp_path, "ui/a.ts", text, {2, 3}) == []


def test_python_on_prefix_no_longer_borrows_the_gdscript_exemption(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "_on_button_pressed = 1\n", {1})
    assert found == [
        "1:variable:_on_button_pressed:a leading `_` is not the private mark; "
        "private is a trailing `_`:on_button_pressed_",
        "1:variable:_on_button_pressed:`on_` starts the handler mold, not open to a variable:",
    ]


def test_python_ready_no_longer_borrows_the_gdscript_convention_name(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "_ready = 1\n", {1})
    assert found == [
        "1:variable:_ready:a leading `_` is not the private mark; private is a trailing `_`:ready_",
        "1:variable:_ready:a variable takes a noun phrase, with at most one prepositional tail:",
    ]


def test_on_prefix_is_exempt_via_the_core_convention_list(tmp_path):
    _require_gdscript_parser()
    text = "func _on_button_pressed():\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) == []


def _without_gdscript_conventions(monkeypatch, keep_prefixes=True, keep_ready=True):
    real_load = vocabulary.load

    def _loaded(root, domain):
        d = real_load(root, domain)
        convention = d.conventions["gdscript"]
        prefixes = convention.prefixes if keep_prefixes else frozenset()
        names = convention.names if keep_ready else convention.names - {"_ready"}
        conventions = {**d.conventions, "gdscript": vocabulary.Convention(names, prefixes)}
        return vocabulary.Dictionary(d.concepts, d.matches, d.collections, d.distinct, conventions)

    monkeypatch.setattr(vocabulary_check.vocabulary, "load", _loaded)


def test_on_prefix_exemption_is_read_from_the_dictionary_not_hardcoded(tmp_path, monkeypatch):
    _require_gdscript_parser()
    _without_gdscript_conventions(monkeypatch, keep_prefixes=False)
    text = "func _on_button_pressed():\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) != []


def test_ready_convention_name_exemption_is_read_from_the_dictionary_not_hardcoded(
    tmp_path, monkeypatch
):
    _require_gdscript_parser()
    _without_gdscript_conventions(monkeypatch, keep_ready=False)
    text = "func _ready():\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) != []


def test_gdscript_missing_message_names_the_install_script(tmp_path, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": "signal change_health\n"})
    vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    err = capsys.readouterr().err
    assert "bin/install-gdscript-parser" in err


def test_gdscript_readiness_short_circuits_without_a_sgconfig_file(tmp_path, monkeypatch):
    def _boom(*a, **k):
        pytest.fail("ast-grep invoked despite no sgconfig.yml")

    monkeypatch.setattr(vocabulary_check.subprocess, "run", _boom)
    assert vocabulary_check._gdscript_ready(tmp_path) is None


def test_gdscript_readiness_probe_succeeds_when_ast_grep_returns_zero(tmp_path, monkeypatch):
    config = tmp_path / "sgconfig.yml"
    config.write_text(GDSCRIPT_SGCONFIG)
    monkeypatch.setattr(vocabulary_check.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="[]", stderr=""))
    assert vocabulary_check._gdscript_ready(tmp_path) == config


def test_declarations_passes_the_config_flag_for_a_custom_language(tmp_path):
    config = tmp_path / "sgconfig.yml"
    config.write_text(GDSCRIPT_BROKEN_SGCONFIG)
    gd = tmp_path / "a.gd"
    gd.write_text("signal health_changed\n")
    with pytest.raises(GateError, match="custom language"):
        vocabulary_check.declarations(gd, "gdscript", config)


def test_check_does_not_probe_gdscript_readiness_for_a_python_only_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(
        vocabulary_check, "_gdscript_ready",
        lambda root: pytest.fail("probed gdscript readiness for a python-only diff"),
    )
    repo = _repo(tmp_path, OPTED_IN, {"pkg/a.py": "position = 1\n"})
    assert vocabulary_check.check(repo, {"pkg/a.py": {1}}, []) == []


def test_gdscript_with_a_broken_library_is_skipped_like_a_missing_one(tmp_path, capsys):
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "signal health_changed\n", "sgconfig.yml": GDSCRIPT_BROKEN_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    err = capsys.readouterr().err
    assert found == []
    assert vocabulary_check.GDSCRIPT_MISSING in err


def test_gdscript_without_sgconfig_is_skipped_with_a_visible_reason(tmp_path, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": "signal change_health\n"})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    err = capsys.readouterr().err
    assert found == []
    assert vocabulary_check.GDSCRIPT_MISSING in err


def test_gdscript_missing_parser_message_prints_once_for_two_files(tmp_path, capsys):
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": "signal x_changed\n", "game/b.gd": "signal y_changed\n"})
    vocabulary_check.check(repo, {"game/a.gd": {1}, "game/b.gd": {1}}, [])
    assert capsys.readouterr().err.count(vocabulary_check.GDSCRIPT_MISSING) == 1


def test_gdscript_missing_parser_skip_still_reaches_a_later_file(tmp_path):
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": "signal x_changed\n", "pkg/b.py": "frob = 1\n"})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}, "pkg/b.py": {1}}, [])
    assert [(f.file, f.name) for f in found] == [("pkg/b.py", "frob")]


def test_leading_underscore_skips_a_missing_gdscript_parser_and_still_reaches_the_next_file(
    tmp_path, monkeypatch, capsys
):
    repo = _repo(tmp_path, "", {"game/a.gd": "signal x_changed\n", "pkg/b.py": "_frob = 1\n"})
    listing = "game/a.gd\0pkg/b.py\0"
    monkeypatch.setattr(vocabulary_check, "git", lambda *a, cwd=None: listing)
    rows = vocabulary_check.leading_underscore(repo)
    err = capsys.readouterr().err
    assert rows == [("pkg/b.py", 1, "_frob", "frob_")]
    assert vocabulary_check.GDSCRIPT_MISSING in err


def test_leading_underscore_does_not_probe_gdscript_readiness_for_a_python_only_diff(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        vocabulary_check, "_gdscript_ready",
        lambda root: pytest.fail("probed gdscript readiness for a python-only diff"),
    )
    repo = _repo(tmp_path, "", {"pkg/a.py": "_frob = 1\n"})
    monkeypatch.setattr(vocabulary_check, "git", lambda *a, cwd=None: "pkg/a.py\0")
    assert vocabulary_check.leading_underscore(repo) == [("pkg/a.py", 1, "_frob", "frob_")]


def test_leading_underscore_audit_skips_the_tool_dictated_path_list(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, "", {
        "src/_version.py": "",
        "pkg/_core.so": "",
        "src/_impl.py": "def _parse_frame():\n    pass\n",
    })
    listing = "src/_version.py\0pkg/_core.so\0src/_impl.py\0"
    monkeypatch.setattr(vocabulary_check, "git", lambda *a, cwd=None: listing)
    monkeypatch.setattr(vocabulary, "discover", lambda cwd=None: repo)
    assert cli.main(["vocabulary", "audit", "--leading-underscore"]) == 0
    out = capsys.readouterr().out
    assert out == "src/_impl.py:1 _parse_frame parse_frame_\nsrc/_impl.py:0 _impl.py impl_.py\n"


def test_leading_underscore_path_row_is_exempt_under_a_dot_directory(tmp_path, monkeypatch):
    repo = _repo(tmp_path, "", {".ci/_release.py": "def _parse_frame():\n    pass\n"})
    listing = ".ci/_release.py\0"
    monkeypatch.setattr(vocabulary_check, "git", lambda *a, cwd=None: listing)
    rows = vocabulary_check.leading_underscore(repo)
    assert rows == [(".ci/_release.py", 1, "_parse_frame", "parse_frame_")]


def test_leading_underscore_reaches_a_file_past_an_exempt_directory_segment(tmp_path, monkeypatch):
    repo = _repo(tmp_path, "", {"pkg/__pycache__/_frob.py": ""})
    listing = "pkg/__pycache__/_frob.py\0"
    monkeypatch.setattr(vocabulary_check, "git", lambda *a, cwd=None: listing)
    rows = vocabulary_check.leading_underscore(repo)
    assert rows == [("pkg/__pycache__/_frob.py", 0, "_frob.py", "frob_.py")]


def test_leading_underscore_tool_dictated_exemption_is_read_from_the_core_list(tmp_path, monkeypatch):
    monkeypatch.setattr(vocabulary_path, "TOOL_DICTATED_FILES", frozenset())
    repo = _repo(tmp_path, "", {"src/_version.py": ""})
    listing = "src/_version.py\0"
    monkeypatch.setattr(vocabulary_check, "git", lambda *a, cwd=None: listing)
    rows = vocabulary_check.leading_underscore(repo)
    assert rows == [("src/_version.py", 0, "_version.py", "version_.py")]


def test_leading_underscore_still_flags_a_declaration_inside_a_tool_dictated_file(tmp_path, monkeypatch):
    repo = _repo(tmp_path, "", {"src/_version.py": "def _parse_frame():\n    pass\n"})
    listing = "src/_version.py\0"
    monkeypatch.setattr(vocabulary_check, "git", lambda *a, cwd=None: listing)
    rows = vocabulary_check.leading_underscore(repo)
    assert rows == [("src/_version.py", 1, "_parse_frame", "parse_frame_")]


def test_staged_tsx_component_passes_and_camel_case_function_blocks(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, OPTED_IN,
                 {"ui/a.tsx": "function FrameViewer() {}\nfunction renderStuff() {}\n"})
    code = _gate(monkeypatch, tmp_path, repo, {"ui/a.tsx": {1, 2}})
    err = capsys.readouterr().err
    assert code == 1
    assert "ui/a.tsx:2: function `renderStuff`" in err
    assert "FrameViewer" not in err


def test_staged_gdscript_without_parser_skips_with_a_message_instead_of_blocking(
    tmp_path, monkeypatch, capsys
):
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": "signal change_health\n"})
    code = _gate(monkeypatch, tmp_path, repo, {"game/a.gd": {1}})
    err = capsys.readouterr().err
    assert code == 0
    assert vocabulary_check.GDSCRIPT_MISSING in err


def test_gdscript_signal_takes_the_event_mold(tmp_path):
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "signal health_changed\n", "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) == []


def test_gdscript_signal_is_actually_scanned_as_an_event(tmp_path):
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "signal manager_changed\n", "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.kind, f.rule) for f in found] == [("event", vocabulary_check.RULE_VAGUE_WORD)]


def test_gdscript_signal_not_ending_in_a_past_participle_blocks(tmp_path):
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "signal change_health\n", "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.kind, f.rule) for f in found] == [("event", vocabulary_check.RULE_MOLD)]


def test_gdscript_private_variable_leading_underscore_blocks_suggesting_trailing(tmp_path):
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "var _health := 100\n", "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.kind, f.rule, f.suggestion) for f in found] == [
        ("variable", vocabulary_check.RULE_LEADING_UNDERSCORE, "health_")
    ]


def test_gdscript_trailing_underscore_variable_and_function_pass(tmp_path):
    _require_gdscript_parser()
    text = "var health_ := 100\nfunc run_():\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1, 2}}, []) == []


def test_gdscript_private_function_leading_underscore_blocks_suggesting_trailing(tmp_path):
    _require_gdscript_parser()
    repo = _repo(tmp_path, OPTED_IN,
                 {"game/a.gd": "func _run():\n\tpass\n", "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.kind, f.rule, f.suggestion) for f in found] == [
        ("function", vocabulary_check.RULE_LEADING_UNDERSCORE, "run_")
    ]


def test_gdscript_autoconnect_handler_and_engine_virtuals_are_exempt(tmp_path):
    _require_gdscript_parser()
    text = ("func _ready():\n\tpass\nfunc _process(delta):\n\tpass\n"
            "func _physics_process(delta):\n\tpass\nfunc _input(event):\n\tpass\n"
            "func _on_button_pressed():\n\tpass\n")
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1, 3, 5, 7, 9}}, []) == []


@pytest.mark.parametrize("name", GODOT_ENGINE_VIRTUALS)
def test_gdscript_engine_virtual_is_exempt(tmp_path, name):
    _require_gdscript_parser()
    text = f"func {name}():\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) == []


def test_gdscript_getter_property_and_plain_variable_are_told_apart(tmp_path):
    _require_gdscript_parser()
    text = "var frob: int:\n\tget:\n\t\treturn frob\nvar frobnicate := 1\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1, 4}}, [])
    assert [(f.kind, f.name) for f in found] == [("property", "frob"), ("variable", "frobnicate")]


def test_gdscript_constructor_parameter_with_unknown_word_blocks(tmp_path):
    _require_gdscript_parser()
    text = "func _init(frob):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.line, f.kind, f.rule, f.name) for f in found] == [
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob")
    ]


def test_gdscript_constructor_typed_and_default_parameters_are_checked(tmp_path):
    _require_gdscript_parser()
    text = "func _init(frobtype: int, frobdefault = 1, frobboth: int = 1):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert {(f.kind, f.rule, f.name) for f in found} == {
        ("parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frobtype"),
        ("parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frobdefault"),
        ("parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frobboth"),
    }


def test_gdscript_constructor_itself_passes_with_a_known_parameter(tmp_path):
    _require_gdscript_parser()
    text = "func _init(health):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) == []


def test_gdscript_ordinary_function_parameter_with_unknown_word_blocks(tmp_path):
    _require_gdscript_parser()
    text = "func run(frob):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.line, f.kind, f.rule, f.name) for f in found] == [
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob")
    ]


def test_gdscript_ordinary_function_known_parameter_passes(tmp_path):
    _require_gdscript_parser()
    text = "func run(health):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) == []


def test_gdscript_ordinary_function_typed_and_default_parameters_are_checked(tmp_path):
    _require_gdscript_parser()
    text = "func run(frobtype: int, frobdefault = 1, frobboth: int = 1):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert {(f.line, f.kind, f.rule, f.name) for f in found} == {
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frobtype"),
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frobdefault"),
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frobboth"),
    }


def test_gdscript_static_function_parameter_is_checked(tmp_path):
    _require_gdscript_parser()
    text = "static func run(frob):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.line, f.kind, f.rule, f.name) for f in found] == [
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob")
    ]


def test_gdscript_ordinary_function_with_several_parameters_checks_each_one(tmp_path):
    _require_gdscript_parser()
    text = "func run(health, frob):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.line, f.kind, f.rule, f.name) for f in found] == [
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob")
    ]


def test_gdscript_signal_with_several_parameters_checks_each_one(tmp_path):
    _require_gdscript_parser()
    text = "signal value_changed(health, frob)\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.line, f.kind, f.rule, f.name) for f in found] == [
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob")
    ]


def test_gdscript_engine_virtual_parameter_is_exempt_regardless_of_the_parameter_name(tmp_path):
    _require_gdscript_parser()
    text = "func _process(frob):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) == []


def test_gdscript_engine_virtual_exemption_does_not_bleed_into_the_next_function(tmp_path):
    _require_gdscript_parser()
    text = "func _process(delta):\n\tpass\nfunc run(frob):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1, 2, 3, 4}}, [])
    assert [(f.line, f.kind, f.rule, f.name) for f in found] == [
        (3, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob")
    ]


def test_gdscript_function_named_like_a_python_convention_still_checks_its_parameter(tmp_path):
    """#250: `main` is a Python/C++ entrypoint convention, not a Godot engine
    virtual; it must not skip a GDScript function's own parameters."""
    _require_gdscript_parser()
    text = "func main(frob):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert {(f.line, f.kind, f.rule, f.name) for f in found} == {
        (1, "function", vocabulary_check.RULE_UNKNOWN_WORD, "main"),
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob"),
    }


def test_gdscript_request_function_from_the_ticket_still_checks_its_parameter(tmp_path):
    """#250's own repro: `request` is a pytest fixture name, not a GDScript one."""
    _require_gdscript_parser()
    text = "func request(url):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert {(f.line, f.kind, f.rule, f.name) for f in found} == {
        (1, "function", vocabulary_check.RULE_UNKNOWN_WORD, "request"),
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "url"),
    }


def test_cpp_argc_parameter_of_main_is_still_exempt(tmp_path):
    found = _findings(tmp_path, "src/k.cpp", "int main(int argc, char** argv) {\n  return 0;\n}\n", {1})
    assert found == []


def test_python_entrypoint_function_and_its_argv_parameter_pass(tmp_path):
    assert _findings(tmp_path, "pkg/a.py", "def main(argv):\n    pass\n", {1, 2}) == []


def test_gdscript_non_virtual_underscore_function_parameter_still_blocks(tmp_path):
    _require_gdscript_parser()
    text = "func _run(frob):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert {(f.line, f.kind, f.rule, f.name) for f in found} == {
        (1, "function", vocabulary_check.RULE_LEADING_UNDERSCORE, "_run"),
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob"),
    }


def test_gdscript_autoconnect_handler_parameter_still_blocks(tmp_path):
    _require_gdscript_parser()
    text = "func _on_button_pressed(frob):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.line, f.kind, f.rule, f.name) for f in found] == [
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob")
    ]


@pytest.mark.parametrize("name,parameter", [("_process", "delta"), ("_notification", "what")])
def test_gdscript_engine_virtual_function_parameter_is_exempt(tmp_path, name, parameter):
    _require_gdscript_parser()
    text = f"func {name}({parameter}):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) == []


def test_gdscript_engine_virtual_parameter_exemption_is_read_from_the_dictionary_not_hardcoded(
    tmp_path, monkeypatch
):
    _require_gdscript_parser()
    _without_gdscript_conventions(monkeypatch, keep_ready=False)
    text = "func _ready(delta):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert ("parameter", vocabulary_check.RULE_UNKNOWN_WORD, "delta") in {
        (f.kind, f.rule, f.name) for f in found
    }


def test_gdscript_ready_convention_parameter_is_exempt_with_the_real_dictionary(tmp_path):
    _require_gdscript_parser()
    text = "func _ready(delta):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) == []


def test_gdscript_signal_parameter_with_unknown_word_blocks(tmp_path):
    _require_gdscript_parser()
    text = "signal value_changed(frob)\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.line, f.kind, f.rule, f.name) for f in found] == [
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob")
    ]


def test_gdscript_signal_parameter_with_known_word_passes(tmp_path):
    _require_gdscript_parser()
    text = "signal health_changed(health)\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) == []


def test_gdscript_signal_typed_parameter_is_checked(tmp_path):
    _require_gdscript_parser()
    text = "signal value_changed(frob: int)\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    found = vocabulary_check.check(repo, {"game/a.gd": {1}}, [])
    assert [(f.line, f.kind, f.rule, f.name) for f in found] == [
        (1, "parameter", vocabulary_check.RULE_UNKNOWN_WORD, "frob")
    ]


def test_gdscript_default_parameter_value_reference_is_not_scanned_as_a_parameter(tmp_path):
    _require_gdscript_parser()
    text = "func run(count = MAX_SPEED):\n\tpass\n"
    repo = _repo(tmp_path, OPTED_IN, {"game/a.gd": text, "sgconfig.yml": GDSCRIPT_SGCONFIG})
    assert vocabulary_check.check(repo, {"game/a.gd": {1}}, []) == []
