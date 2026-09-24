"""Intent: #107 (decisions 9, 27, 28, 31 of #103) — a declared name is checked against
the type written beside it, and only then: T1 an `is_`/`has_`/`can_` name has type or
return `bool`; T2 a singular head noun never takes a collection type, skipped with a
prepositional tail, for enum members and for a type not in `[collection]`; T3 a verb
flagged `returns` matches the declared return, `from_` returns the enclosing type,
`to_`/`as_` return non-void. An unannotated Python name or a C++ `auto` is skipped. A
same-file C++ `using`/`typedef` of a known collection resolves one level.

Driven through cli.main as the #105 slice is: discover and the diff are stubbed, the
config, the packaged core, the domain file, the ast-grep scan and the exit code are real."""

from pathlib import Path

import pytest

from mutation_gate import cli, mutants, runner, token, vocabulary_check
from mutation_gate.repo import Config, GateError, Repo

DOMAIN = ".vocabulary.toml"
OPTED_IN = f'vocabulary = "{DOMAIN}"\n'
WORDS = (
    '[[concept]]\nword = "ready"\nmeaning = "prepared to act"\npos = ["adjective"]\n\n'
    '[[concept]]\nword = "reset"\nmeaning = "return to the initial state"\npos = ["verb"]\n'
    'returns = "none"\n\n'
    '[[concept]]\nword = "second"\nmeaning = "the SI unit of time"\npos = ["noun"]\n'
    'forms = ["plural"]\n\n'
    '[[concept]]\nword = "list"\nmeaning = "an ordered sequence"\npos = ["noun"]\nhead = true\n\n'
)
FRAME_LIST = WORDS + '[collection]\ntypes = ["FrameList"]\n'
FRAMES_ALIAS = "using Frames = std::vector<Frame>;\n"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _repo(tmp_path: Path, files: dict[str, str], domain: str = WORDS) -> Repo:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    _write(root, ".mutation-gate.toml", OPTED_IN)
    _write(root, DOMAIN, domain)
    for rel, text in files.items():
        _write(root, rel, text)
    return Repo(root=root, origin="", remotes=(), config=Config.load(root))


def _no_git(*args: str, cwd=None) -> str:
    raise GateError("git: not in the test image")


def _gate(monkeypatch, tmp_path: Path, files: dict[str, str], domain: str = WORDS) -> int:
    repo = _repo(tmp_path, files, domain)
    added = {rel: set(range(1, text.count("\n") + 1)) for rel, text in files.items()}
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli.model_vv, "git", _no_git)
    monkeypatch.setattr(cli, "_gate_file", lambda *a, **k: (False, [], []))
    monkeypatch.setattr(mutants, "changed_lines", lambda root, staged: added)
    for mod in (cli, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")
    return cli.main(["--staged", "--no-adversary"])


@pytest.mark.parametrize("name, prefix", [("is_ready", "is"), ("has_frames", "has"), ("can_read", "can")])
def test_staged_predicate_typed_int_blocks_naming_bool(tmp_path, monkeypatch, capsys, name, prefix):
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": f"{name}: int = 1\n"})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert (f"pkg/a.py:1: variable `{name}` — `{prefix}_` asks yes or no; "
            "its type is `int`, not `bool`") in err


def test_staged_plural_list_tail_bool_and_unannotated_names_pass(tmp_path, monkeypatch):
    text = ("frames: list[Frame] = []\nframes_per_second: float = 1.0\nis_ready: bool = True\n"
            "frame = []\nis_empty = 1\ndef read_frame():\n    x = compute()\n    return x\n")
    assert _gate(monkeypatch, tmp_path, {"pkg/a.py": text}) == 0


def test_staged_singular_frame_typed_list_blocks_suggesting_frames(tmp_path, monkeypatch, capsys):
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": "frame: list[Frame] = []\n"})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert "pkg/a.py:1: variable `frame` — `frame` is singular; `list[Frame]` is a collection" in err
    assert "try `frames`" in err


def test_staged_singular_frame_typed_undeclared_frame_list_passes(tmp_path, monkeypatch):
    assert _gate(monkeypatch, tmp_path, {"pkg/a.py": "frame: FrameList = FrameList()\n"}) == 0


def test_staged_singular_frame_typed_declared_frame_list_blocks(tmp_path, monkeypatch, capsys):
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": "frame: FrameList = FrameList()\n"}, FRAME_LIST)
    err = capsys.readouterr().err
    assert code == 1
    assert "pkg/a.py:1: variable `frame` — `frame` is singular; `FrameList` is a collection" in err


@pytest.mark.parametrize("domain", [WORDS, FRAME_LIST])
def test_staged_plural_frames_typed_frame_list_passes_before_and_after_declaring_it(
    tmp_path, monkeypatch, domain
):
    assert _gate(monkeypatch, tmp_path, {"pkg/a.py": "frames: FrameList = FrameList()\n"},
                 domain) == 0


@pytest.mark.parametrize("alias", [FRAMES_ALIAS, "typedef std::vector<Frame> Frames;\n"])
def test_staged_cpp_singular_frame_of_aliased_vector_blocks(tmp_path, monkeypatch, capsys, alias):
    code = _gate(monkeypatch, tmp_path, {"src/k.hpp": alias + "Frames frame;\n"})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert "src/k.hpp:2: variable `frame` — `frame` is singular; `std::vector<Frame>` is a collection" in err


def test_staged_cpp_alias_resolves_one_level_only(tmp_path, monkeypatch):
    text = FRAMES_ALIAS + "using FrameList = Frames;\nFrameList frame;\n"
    assert _gate(monkeypatch, tmp_path, {"src/k.hpp": text}) == 0


def test_staged_cpp_reference_parameter_resolves_through_the_reference(tmp_path, monkeypatch, capsys):
    code = _gate(monkeypatch, tmp_path, {"src/k.hpp": "void reset(const std::vector<Frame>& frame);\n"})
    err = capsys.readouterr().err
    assert code == 1
    assert "src/k.hpp:1: parameter `frame` — `frame` is singular" in err


def test_staged_cpp_auto_and_pointer_types_are_unwritten(tmp_path, monkeypatch):
    text = "auto is_ready = 1;\nstd::vector<Frame>* frame = nullptr;\n"
    assert _gate(monkeypatch, tmp_path, {"src/k.cpp": text}) == 0


def test_staged_reset_flagged_none_returning_int_blocks(tmp_path, monkeypatch, capsys):
    text = "class Frame:\n    def reset(self) -> int:\n        pass\n"
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": text})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert ("pkg/a.py:2: method `reset` — `reset` is flagged `returns = \"none\"`; "
            "it is declared to return `int`") in err


def test_staged_read_flagged_value_returning_none_blocks(tmp_path, monkeypatch, capsys):
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": "def read_frame() -> None:\n    pass\n"})
    err = capsys.readouterr().err
    assert code == 1
    assert ("pkg/a.py:1: function `read_frame` — `read` is flagged `returns = \"value\"`; "
            "it is declared to return `None`") in err


def test_staged_flagged_verbs_with_matching_or_unwritten_returns_pass(tmp_path, monkeypatch):
    text = ("def reset_frame() -> None:\n    pass\n\n\ndef read_frame() -> bytes:\n    pass\n\n\n"
            "def reset_frames():\n    pass\n")
    assert _gate(monkeypatch, tmp_path, {"pkg/a.py": text}) == 0


def test_staged_cpp_reset_flagged_none_returning_void_passes_and_int_blocks(
    tmp_path, monkeypatch, capsys
):
    text = "void reset_frame();\nint reset_frames();\n"
    code = _gate(monkeypatch, tmp_path, {"src/k.hpp": text})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert ("src/k.hpp:2: function `reset_frames` — `reset` is flagged `returns = \"none\"`; "
            "it is declared to return `int`") in err


def test_staged_from_bytes_returning_bytes_blocks_naming_the_class(tmp_path, monkeypatch, capsys):
    text = "class Frame:\n    @classmethod\n    def from_bytes(cls, frame: bytes) -> bytes:\n        pass\n"
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": text})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert ("pkg/a.py:3: method `from_bytes` — `from_` returns the enclosing type `Frame`; "
            "it is declared to return `bytes`") in err


def test_staged_from_bytes_returning_the_quoted_class_or_self_passes(tmp_path, monkeypatch):
    text = ("class Frame:\n"
            "    @classmethod\n    def from_bytes(cls, frame: bytes) -> \"Frame\":\n        pass\n\n"
            "    @classmethod\n    def from_frame(cls, frame) -> Self:\n        pass\n")
    assert _gate(monkeypatch, tmp_path, {"pkg/a.py": text}) == 0


def test_staged_to_bytes_returning_none_blocks(tmp_path, monkeypatch, capsys):
    text = "class Frame:\n    def to_bytes(self) -> None:\n        pass\n"
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": text})
    err = capsys.readouterr().err
    assert code == 1
    assert "pkg/a.py:2: method `to_bytes` — `to_` returns a value; it is declared to return `None`" in err


def test_staged_cpp_from_bytes_returning_the_class_passes_and_as_bytes_void_blocks(
    tmp_path, monkeypatch, capsys
):
    text = "class Frame {\n  static Frame from_bytes(int count);\n  void as_bytes() const;\n};\n"
    code = _gate(monkeypatch, tmp_path, {"src/k.hpp": text})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert "src/k.hpp:3: method `as_bytes` — `as_` returns a value; it is declared to return `void`" in err


def test_staged_property_is_ready_returning_int_blocks(tmp_path, monkeypatch, capsys):
    text = "class Frame:\n    @property\n    def is_ready(self) -> int:\n        return 1\n"
    code = _gate(monkeypatch, tmp_path, {"pkg/a.py": text})
    err = capsys.readouterr().err
    assert code == 1
    assert "pkg/a.py:3: property `is_ready` — `is_` asks yes or no; its type is `int`, not `bool`" in err


def test_staged_cpp_is_ready_method_bool_passes_and_int_field_blocks(tmp_path, monkeypatch, capsys):
    text = "class Frame {\n  bool is_ready() const;\n  int has_frames;\n};\n"
    code = _gate(monkeypatch, tmp_path, {"src/k.hpp": text})
    err = capsys.readouterr().err
    assert code == 1
    assert "BLOCKED: vocabulary — 1 finding(s)." in err
    assert "src/k.hpp:3: field `has_frames` — `has_` asks yes or no; its type is `int`, not `bool`" in err


def _findings(tmp_path, rel: str, text: str, domain: str = WORDS) -> list[str]:
    repo = _repo(tmp_path, {rel: text}, domain)
    lines = set(range(1, text.count("\n") + 1))
    found = vocabulary_check.check(repo, {rel: lines}, [])
    return [f"{f.line}:{f.kind}:{f.name}:{f.rule}:{f.detail}:{f.suggestion}" for f in found]


def test_enum_member_typed_as_a_collection_is_not_a_t2_finding(tmp_path):
    text = "class Frame(Enum):\n    frame: list[int] = [1]\n"
    assert _findings(tmp_path, "pkg/a.py", text) == []


def test_class_body_field_typed_as_a_collection_is_a_t2_finding(tmp_path):
    text = "class Frame:\n    frame: list[int] = [1]\n"
    assert [f.split(":")[:4] for f in _findings(tmp_path, "pkg/a.py", text)] == [
        ["2", "field", "frame", "type_collection"]
    ]


def test_function_is_ready_returning_int_is_a_t1_finding(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "def is_ready() -> int:\n    pass\n")
    assert [f.split(":")[:4] for f in found] == [["1", "function", "is_ready", "type_bool"]]


def test_cpp_from_bytes_returning_another_type_blocks_naming_the_class(tmp_path):
    text = "class Frame {\n  static int from_bytes(int count);\n};\n"
    assert _findings(tmp_path, "src/k.hpp", text) == [
        "2:method:from_bytes:type_return:`from_` returns the enclosing type `Frame`; "
        "it is declared to return `int`:"
    ]


def test_cpp_alias_in_another_file_is_not_resolved(tmp_path):
    repo = _repo(tmp_path, {"src/a.hpp": FRAMES_ALIAS, "src/k.hpp": "Frames frame;\n"})
    assert vocabulary_check.check(repo, {"src/a.hpp": {1}, "src/k.hpp": {1}}, []) == []


def test_singular_self_attribute_typed_list_is_a_field_finding(tmp_path):
    text = "class Frame:\n    def __init__(self):\n        self.frame: list[Frame] = []\n"
    assert _findings(tmp_path, "pkg/a.py", text) == [
        "3:field:frame:type_collection:`frame` is singular; `list[Frame]` is a collection type:frames"
    ]


def test_singular_camel_case_local_typed_list_suggests_the_plural_in_style(tmp_path):
    text = "def read():\n    targetFrame: list[Frame] = []\n    return targetFrame\n"
    assert _findings(tmp_path, "pkg/a.py", text) == [
        "2:local:targetFrame:type_collection:`targetFrame` is singular; `list[Frame]` is a collection type:targetFrames"
    ]


def test_agent_noun_er_form_typed_list_is_singular(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "frame_reader: list[Frame] = []\n")
    assert found == [
        "1:variable:frame_reader:type_collection:`frame_reader` is singular; `list[Frame]` is a collection type:"
    ]


def test_participle_tail_typed_list_is_not_a_singular_noun(tmp_path):
    assert _findings(tmp_path, "pkg/a.py", "bytes_read: list[int] = []\n") == []


def test_unknown_head_word_typed_list_has_only_the_dictionary_finding(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "frob: list[Frame] = []\n")
    assert found == ["1:variable:frob:unknown_word:`frob` is not in the dictionary:"]


def test_to_bytes_returning_bytes_passes(tmp_path):
    text = "class Frame:\n    def to_bytes(self) -> bytes:\n        pass\n"
    assert _findings(tmp_path, "pkg/a.py", text) == []


def test_singular_head_before_a_tail_typed_list_is_skipped(tmp_path):
    assert _findings(tmp_path, "pkg/a.py", "count_of_frames: list[Frame] = []\n") == []


def test_plural_head_noun_of_a_collection_type_passes_in_cpp(tmp_path):
    assert _findings(tmp_path, "src/k.cpp", "std::vector<Frame> frames;\n") == []


def test_cpp_alias_of_an_unknown_type_leaves_the_name_unchecked(tmp_path):
    text = "using Frames = Sequence<Frame>;\nFrames frame;\n"
    assert _findings(tmp_path, "src/k.hpp", text) == []


def test_type_faults_are_reported_beside_word_faults_on_one_name(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "is_frob: int = 1\n")
    assert found == [
        "1:variable:is_frob:unknown_word:`frob` is not in the dictionary:",
        "1:variable:is_frob:type_bool:`is_` asks yes or no; its type is `int`, not `bool`:",
    ]


def test_return_fault_carries_the_type_return_rule_id(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "def reset_frame() -> int:\n    pass\n")
    assert [f.split(":")[3] for f in found] == ["type_return"]


def test_free_from_bytes_returning_bytes_has_only_the_mold_finding(tmp_path):
    found = _findings(tmp_path, "pkg/a.py", "def from_bytes(frame: bytes) -> bytes:\n    pass\n")
    assert len(found) == 1
    assert "`from_` starts the conversion mold, not open to a function" in found[0]


def test_declarations_carry_the_written_type_and_the_enclosing_class(tmp_path):
    text = ("class Frame:\n    def reset(self) -> int:\n        count: int = 1\n"
            "        return count\n\n\ndef read(frame: Frame, n=1):\n    pass\n")
    (tmp_path / "a.py").write_text(text)
    assert vocabulary_check.declarations(tmp_path / "a.py", "python") == [
        (1, "type", "Frame", "", ""),
        (2, "method", "reset", "int", "Frame"),
        (2, "parameter", "self", "", ""),
        (3, "local", "count", "int", ""),
        (7, "function", "read", "", ""),
        (7, "parameter", "frame", "Frame", ""),
        (7, "parameter", "n", "", ""),
    ]
