"""Intent: #106 (decisions 6, 7, 8, 10, 14, 24, 25, 27, 28, 29, 32 of #103) — a name a
diff declares fits the mold of its declaration kind under some assignment of parts of
speech: 1 to 4 words with function words counted and test functions uncapped, a head
noun last in its noun phrase, `from_`/`to_`/`as_` for methods only, a type never ending
in -ing, an enum member allowed a lone -ing form, object-like macros as constants and
function-like macros as functions. A repo narrows the catalogue in config, never widens
it. `vocabulary lookup --kind <kind> <name>` reports pass or the first failing rule.

Driven through cli.main as the #105 slice is: discover and the diff are stubbed, the
config, the packaged core, the ast-grep scan and the exit code are real."""

from pathlib import Path

import pytest

from mutation_gate import cli, mutants, runner, token, vocabulary, vocabulary_check, vocabulary_molds
from mutation_gate.repo import Config, GateError, Repo

DOMAIN = ".vocabulary.toml"
OPTED_IN = f'vocabulary = "{DOMAIN}"\n'
FROM_BYTES = ("class Frame:\n    @classmethod\n    def from_bytes(cls, frame):\n        pass\n\n\n"
              "def from_bytes(frame):\n    pass\n")


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _repo(tmp_path: Path, files: dict[str, str], toml: str = OPTED_IN) -> Repo:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    _write(root, ".mutation-gate.toml", toml)
    _write(root, DOMAIN, "")
    for rel, text in files.items():
        _write(root, rel, text)
    return Repo(root=root, origin="", remotes=(), config=Config.load(root))


def _no_git(*args: str, cwd=None) -> str:
    raise GateError("git: not in the test image")


def _gate(monkeypatch, tmp_path: Path, files: dict[str, str], toml: str = OPTED_IN) -> int:
    repo = _repo(tmp_path, files, toml)
    added = {rel: set(range(1, text.count("\n") + 1)) for rel, text in files.items()}
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli.model_vv, "git", _no_git)
    monkeypatch.setattr(cli, "_gate_file", lambda *a, **k: (False, [], []))
    monkeypatch.setattr(mutants, "changed_lines", lambda root, staged: added)
    for mod in (cli, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")
    return cli.main(["--staged", "--no-adversary"])


def test_staged_variable_count_frame_blocks_suggesting_frame_count(tmp_path, monkeypatch, capsys):
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": "count_frame = 1\n"})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert "pkg/a.py:1: variable `count_frame` — `count` is a head noun" in err
    assert "try `frame_count`" in err


def test_staged_noun_phrases_with_a_tail_or_a_participle_pass(tmp_path, monkeypatch):
    text = "frame_count = 1\ncount_of_frames = 2\ndistance_to_target = 3\nbytes_read = 4\n"
    assert _gate(monkeypatch, tmp_path, {"pkg/a.py": text}) == 0


def test_staged_function_frame_read_blocks_suggesting_read_frame(tmp_path, monkeypatch, capsys):
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": "def frame_read():\n    pass\n"})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert "function `frame_read` — a function takes a verb first" in err
    assert "try `read_frame`" in err


@pytest.mark.parametrize("name, hint", [
    ("is_not_empty", "`not`: name the positive predicate and negate at the call site"),
    ("no_frames", "`no`: name the positive predicate and negate at the call site"),
    ("read_and_parse", "`and`: one action per name: split the function, or name the combined step"),
    ("read_or_parse", "`or`: name the outcome, not the alternatives"),
])
def test_staged_function_with_a_rejected_function_word_blocks(tmp_path, monkeypatch, capsys, name, hint):
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": f"def {name}():\n    pass\n"})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert f"function `{name}` — {hint}" in err


def test_staged_five_word_variable_blocks_on_the_cap(tmp_path, monkeypatch, capsys):
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": "distance_to_first_target_frame = 1\n"})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert "variable `distance_to_first_target_frame` — 5 words; a name has 1 to 4" in err


def test_staged_seven_word_test_function_passes(tmp_path, monkeypatch):
    text = "def test_circle_touching_corner_at_zero_heading_overlaps():\n    pass\n"
    assert _gate(monkeypatch, tmp_path, {"tests/test_a.py": text}) == 0


def test_staged_free_from_bytes_blocks_while_the_classmethod_passes(tmp_path, monkeypatch, capsys):
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": FROM_BYTES})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert ("pkg/a.py:7: function `from_bytes` — `from_` starts the conversion mold, "
            "not open to a function") in err


def test_staged_enum_member_running_passes_and_class_parsing_blocks(tmp_path, monkeypatch, capsys):
    text = "from enum import Enum\n\n\nclass Frame(Enum):\n    Running = 1\n\n\nclass Parsing:\n    pass\n"
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": text})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert ("pkg/a.py:8: type `Parsing` — a type takes a noun phrase ending in a noun, "
            "never an -ing form") in err


def test_staged_config_narrowed_to_no_conversion_blocks_the_classmethod(tmp_path, monkeypatch, capsys):
    toml = OPTED_IN + '[vocabulary_molds]\nmethod = ["function", "predicate", "test", "handler"]\n'
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": FROM_BYTES}, toml)
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 2 finding(s)." in err
    assert "pkg/a.py:3: method `from_bytes` — `from_` starts the conversion mold" in err


@pytest.mark.parametrize("narrowing, refusal", [
    ('function = ["function", "conversion"]\n',
     "vocabulary_molds.function = ['function', 'conversion']: a repo narrows function, "
     "predicate, test, handler, never widens"),
    ('frob = ["variable"]\n', "vocabulary_molds.frob: not a declaration kind; one of function, "),
    ("function = []\n", "vocabulary_molds.function = []: a repo narrows"),
])
def test_staged_widened_or_unknown_mold_config_refuses_with_exit_2(
    tmp_path, monkeypatch, capsys, narrowing, refusal
):
    toml = OPTED_IN + "[vocabulary_molds]\n" + narrowing
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": "frame = 1\n"}, toml)
    err = capsys.readouterr().err
    assert code == 2
    assert f"mutation-gate refused: .mutation-gate.toml: {refusal}" in err


def _lookup(monkeypatch, root: Path, toml: str, kind: str, name: str, capsys) -> tuple[int, str, str]:
    (root / ".mutation-gate.toml").write_text(toml)
    (root / DOMAIN).write_text("")
    monkeypatch.setattr(vocabulary, "discover", lambda cwd=None: Repo(
        root=root, origin="", remotes=(), config=Config.load(root)))
    code = cli.main(["vocabulary", "lookup", "--kind", kind, name])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize("kind, name", [
    ("variable", "frame_count"),
    ("variable", "count_of_frames_read"),
    ("variable", "first_frame"),
    ("variable", "is_running"),
    ("field", "frames_of_count"),
    ("constant", "FRAME_COUNT"),
    ("local", "x_i"),
    ("property", "frame_count"),
    ("property", "is_empty"),
    ("function", "read"),
    ("function", "read_out_frames"),
    ("function", "is_empty"),
    ("function", "has_frames"),
    ("function", "can_read_frame"),
    ("function", "on_frame_read"),
    ("function", "test_frame_count_of_target_overlaps"),
    ("method", "from_bytes"),
    ("method", "to_frame"),
    ("method", "as_bytes"),
    ("bool", "is_read"),
    ("type", "FrameCount"),
    ("type", "Parser"),
    ("namespace", "frame_count"),
    ("enumerator", "Running"),
    ("enumerator", "empty"),
    ("enumerator", "first_frame"),
    ("event", "frame_read"),
])
def test_lookup_kind_reports_a_fit(tmp_path, monkeypatch, capsys, kind, name):
    code, out, _ = _lookup(monkeypatch, tmp_path, OPTED_IN, kind, name, capsys)
    assert code == 0
    assert out == f"{name}: fits the {kind} mold\n"


@pytest.mark.parametrize("kind, name, rule", [
    ("variable", "count_frame",
     "`count` is a head noun: last in its noun phrase, or last before a prepositional tail — try `frame_count`"),
    ("variable", "frames_of_count_target",
     "`count` is a head noun: last in its noun phrase, or last before a prepositional tail — try `frames_of_target_count`"),
    ("local", "countFrame",
     "`count` is a head noun: last in its noun phrase, or last before a prepositional tail — try `frameCount`"),
    ("type", "CountFrame",
     "`Count` is a head noun: last in its noun phrase, or last before a prepositional tail — try `FrameCount`"),
    ("variable", "frame_first", "a variable takes a noun phrase, with at most one prepositional tail — try `first_frame`"),
    ("variable", "frames_out", "a variable takes a noun phrase, with at most one prepositional tail"),
    ("variable", "distance_to_first_target_frame", "5 words; a name has 1 to 4"),
    ("variable", "count_frame_of_first_target", "5 words; a name has 1 to 4"),
    ("variable", "on_frame_read", "`on_` starts the handler mold, not open to a variable"),
    ("variable", "on_count_frame", "`on_` starts the handler mold, not open to a variable"),
    ("property", "read_frame",
     "a property takes a noun phrase, with at most one prepositional tail — try `frame_read`"),
    ("function", "to_frame", "`to_` starts the conversion mold, not open to a function"),
    ("function", "as_bytes", "`as_` starts the conversion mold, not open to a function"),
    ("variable", "frob_count", "`frob` is not in the dictionary"),
    ("function", "frame_read", "a function takes a verb first, then what it acts on — try `read_frame`"),
    ("function", "frame_target_read",
     "a function takes a verb first, then what it acts on — try `read_frame_target`"),
    ("function", "from_bytes", "`from_` starts the conversion mold, not open to a function"),
    ("function", "on_frame", "a function takes `on_`, then the event: nouns, then a past participle"),
    ("function", "is_index_frame",
     "`index` is a head noun: last in its noun phrase, or last before a prepositional tail — try `is_frame_index`"),
    ("function", "test_read_frame",
     "a function takes `test_`, then subject, optional condition, outcome — try `test_frame_read`"),
    ("function", "test_read_frame_count_of_first_target",
     "a function takes `test_`, then subject, optional condition, outcome"
     " — try `test_count_read_frame_of_first_target`"),
    ("method", "from_bytes_of_frame",
     "a method takes `from_`, `to_` or `as_`, then a noun phrase with no prepositional tail"),
    ("bool", "running", "a bool takes `is_`, `has_` or `can_`, then what is asked"),
    ("type", "Parsing", "a type takes a noun phrase ending in a noun, never an -ing form"),
    ("type", "FrameRead", "a type takes a noun phrase ending in a noun, never an -ing form"),
    ("namespace", "empty_frame", "a namespace takes nouns only"),
    ("event", "read_frame", "an event takes nouns, then a past participle — try `frame_read`"),
])
def test_lookup_kind_names_the_first_failing_rule(tmp_path, monkeypatch, capsys, kind, name, rule):
    code, out, err = _lookup(monkeypatch, tmp_path, OPTED_IN, kind, name, capsys)
    assert code == 1
    assert out == ""
    assert err == f"vocabulary lookup: `{name}` as a {kind}: {rule}\n"


def test_lookup_kind_narrowed_config_drops_the_variant(tmp_path, monkeypatch, capsys):
    toml = OPTED_IN + '[vocabulary_molds]\nfunction = ["function"]\n'
    code, out, err = _lookup(monkeypatch, tmp_path, toml, "function", "is_empty", capsys)
    assert code == 1
    assert out == ""
    assert err == ("vocabulary lookup: `is_empty` as a function: `is_` starts the predicate mold, "
                   "not open to a function\n")


def test_lookup_kind_config_restating_the_core_catalogue_is_accepted(tmp_path, monkeypatch, capsys):
    toml = OPTED_IN + '[vocabulary_molds]\nvariable = ["variable", "predicate"]\n'
    assert _lookup(monkeypatch, tmp_path, toml, "variable", "is_running", capsys)[0] == 0


def test_lookup_kind_widened_config_refuses_naming_the_extra_variant(tmp_path, monkeypatch, capsys):
    toml = OPTED_IN + '[vocabulary_molds]\ntype = ["type", "variable"]\n'
    code, _, err = _lookup(monkeypatch, tmp_path, toml, "type", "Frame", capsys)
    assert code == 2
    assert err == ("mutation-gate vocabulary refused: .mutation-gate.toml: vocabulary_molds.type = "
                   "['type', 'variable']: a repo narrows type, never widens\n")


@pytest.mark.parametrize("word, expected", [
    ("read", "PV"),
    ("counts", "HV"),
    ("count", "HV"),
    ("parser", "H"),
    ("Running", "G"),
    ("frames", "N"),
    ("zero", "AN"),
    ("empty", "A"),
    ("to", "p"),
    ("all", "d"),
    ("first", "o"),
    ("out", "t"),
    ("Q", "N"),
    ("and", ""),
    ("frob", ""),
])
def test_tags_carry_every_part_of_speech_a_spelling_allows(tmp_path, word, expected):
    domain = tmp_path / DOMAIN
    domain.write_text('[[symbol]]\nword = "Q"\nmeaning = "process noise covariance"\n')
    dictionary = vocabulary.load(tmp_path, DOMAIN)
    assert vocabulary_molds.tags(dictionary, word) == expected


def _kinds(tmp_path, rel: str, text: str) -> list[tuple[int, str, str]]:
    _write(tmp_path, rel, text)
    lang = mutants.language_of(rel)
    return vocabulary_check.declarations(tmp_path / rel, lang)


def test_python_property_is_its_own_kind_and_its_setter_is_not_declared(tmp_path):
    text = ("class Frame:\n"
            "    @property\n    def frame_count(self):\n        return 1\n\n"
            "    @frame_count.setter\n    def frames_first(self, count):\n        pass\n\n"
            "    @functools.cached_property\n    def size(self):\n        return 1\n")
    assert _kinds(tmp_path, "a.py", text) == [
        (1, "type", "Frame"), (3, "parameter", "self"), (3, "property", "frame_count"),
        (7, "parameter", "count"), (7, "parameter", "self"),
        (11, "parameter", "self"), (11, "property", "size"),
    ]


def test_python_method_free_function_and_nested_function_are_told_apart(tmp_path):
    text = ("class Frame:\n"
            "    @staticmethod\n    def read():\n        def inner():\n            pass\n\n"
            "def free():\n    pass\n")
    assert _kinds(tmp_path, "a.py", text) == [
        (1, "type", "Frame"), (3, "method", "read"), (4, "function", "inner"), (7, "function", "free"),
    ]


def test_python_enum_class_body_assignment_is_an_enumerator_not_a_field(tmp_path):
    text = "class Frame(enum.IntEnum):\n    Running = 1\n\nclass Target:\n    count = 1\n"
    assert _kinds(tmp_path, "a.py", text) == [
        (1, "type", "Frame"), (2, "enumerator", "Running"), (4, "type", "Target"), (5, "field", "count"),
    ]


def test_cpp_macros_are_constants_or_functions_and_the_include_guard_is_skipped(tmp_path):
    text = ("#ifndef FROB_H\n#define FROB_H\n#define FRAME_COUNT 4\n#define NDEBUG\n"
            "#define READ_FRAME(x) (x)\n#endif\n#define LOOSE\n#ifdef X\n#define Y 1\n#endif\n")
    assert _kinds(tmp_path, "k.hpp", text) == [
        (3, "constant", "FRAME_COUNT"), (4, "constant", "NDEBUG"), (5, "function", "READ_FRAME"),
        (7, "constant", "LOOSE"), (9, "constant", "Y"),
    ]


def test_cpp_object_macro_takes_the_constant_mold_and_function_macro_the_function_mold(tmp_path):
    text = "#define COUNT_FRAME 4\n#define FRAME_READ(x) (x)\n#define FRAME_COUNT 4\n"
    repo = _repo(tmp_path, {"src/k.hpp": text})
    found = vocabulary_check.check(repo, {"src/k.hpp": {1, 2, 3}}, [])
    assert [(f.line, f.kind, f.name, f.suggestion) for f in found] == [
        (1, "constant", "COUNT_FRAME", "FRAME_COUNT"), (2, "function", "FRAME_READ", "READ_FRAME"),
    ]


def test_cpp_enumerator_takes_a_lone_ing_form_and_the_type_does_not(tmp_path):
    repo = _repo(tmp_path, {"src/k.hpp": "enum class Parsing { Running };\n"})
    found = vocabulary_check.check(repo, {"src/k.hpp": {1}}, [])
    assert [(f.kind, f.name) for f in found] == [("type", "Parsing")]
