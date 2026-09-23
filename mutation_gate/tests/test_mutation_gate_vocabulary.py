"""Intent: #104 (decisions 3, 4, 5, 7, 15, 23, 24, 25, 37 of #103) — the shipped
core plus a repo's .vocabulary.toml load as one dictionary, and
`mutation-gate vocabulary lookup <word>` answers with the canonical word.

Driven through cli.main. Only git root discovery is stubbed; the config load,
the packaged core, the domain file and the exit code are real."""

from pathlib import Path

import pytest

from mutation_gate import cli, vocabulary, vocabulary_check
from mutation_gate.repo import Config, GateError, Repo

DOMAIN = ".vocabulary.toml"
OPTED_IN = f'vocabulary = "{DOMAIN}"\n'

PARSE = '''
[[concept]]
word = "parse"
meaning = "turn text into a structure"
pos = ["verb"]
'''


def _repo(tmp_path: Path, monkeypatch, toml: str = "", domain: str | None = None) -> Path:
    (tmp_path / ".mutation-gate.toml").write_text(toml)
    if domain is not None:
        (tmp_path / DOMAIN).write_text(domain)
    monkeypatch.setattr(
        vocabulary, "discover",
        lambda cwd=None: Repo(root=tmp_path, origin="", remotes=(), config=Config.load(tmp_path)),
    )
    return tmp_path


def _lookup(word: str, capsys) -> tuple[int, str, str]:
    code = cli.main(["vocabulary", "lookup", word])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_domain_reject_of_loc_prints_the_core_canonical_position(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, OPTED_IN, '[reject]\nloc = "position"\n')
    code, out, _ = _lookup("loc", capsys)
    assert code == 0
    assert out == "position: noun\n  loc is a rejected synonym of position\n"


def test_parsed_resolves_to_parse_when_parse_opts_into_ed(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, OPTED_IN, PARSE + 'forms = ["-ed"]\n')
    code, out, _ = _lookup("parsed", capsys)
    assert code == 0
    assert out == "parse: verb\n  parsed is the -ed form of parse\n"


def test_parsed_is_unknown_when_parse_does_not_opt_into_ed(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, OPTED_IN, PARSE + 'forms = ["-ing"]\n')
    code, out, err = _lookup("parsed", capsys)
    assert code == 1
    assert out == ""
    assert "`parsed` is not in the dictionary" in err


def test_domain_making_vague_manager_canonical_fails_naming_file_and_word(
    tmp_path, monkeypatch, capsys
):
    _repo(tmp_path, monkeypatch, OPTED_IN,
          '[[concept]]\nword = "manager"\nmeaning = "runs things"\npos = ["noun"]\n')
    code, out, err = _lookup("position", capsys)
    assert code == 2
    assert out == ""
    assert str(tmp_path / DOMAIN) in err
    assert "`manager` (canonical) is already vague `manager`" in err


def test_domain_making_position_canonical_a_second_time_fails_naming_both_files(
    tmp_path, monkeypatch, capsys
):
    _repo(tmp_path, monkeypatch, OPTED_IN,
          '[[concept]]\nword = "position"\nmeaning = "where"\npos = ["noun"]\n')
    code, _, err = _lookup("position", capsys)
    assert code == 2
    assert f"{tmp_path / DOMAIN}: `position` is already canonical in {vocabulary.CORE_PATH}" in err


def test_lookup_answers_from_the_core_alone_when_the_key_is_unset(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, "", '[reject]\nloc = "position"\n')
    code, out, _ = _lookup("position", capsys)
    assert code == 0
    assert out.startswith("position: noun\n")
    assert _lookup("loc", capsys)[0] == 1


def test_core_concept_reject_list_resolves_to_its_concept(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    code, out, _ = _lookup("num", capsys)
    assert code == 0
    assert out == "count: noun, verb\n  num is a rejected synonym of count\n"


def test_canonical_lookup_lists_the_derived_forms(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, OPTED_IN, PARSE + 'forms = ["-s", "-ed", "-ing", "-er"]\n')
    code, out, _ = _lookup("parse", capsys)
    assert code == 0
    assert out == "parse: verb\n  forms: parses, parsed, parsing, parser\n"


def test_two_part_of_speech_concept_prints_both(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    code, out, _ = _lookup("count", capsys)
    assert code == 0
    assert out.startswith("count: noun, verb\n")


def test_symbol_lookup_prints_its_meaning(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    code, out, _ = _lookup("i", capsys)
    assert code == 0
    assert out == "i: symbol\n  loop index; locals and parameters only\n"


def test_vague_word_lookup_prints_its_hint(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    code, out, _ = _lookup("manager", capsys)
    assert code == 0
    assert out == "manager: vague\n  name what it does: scheduler, registry, pool, cache\n"


def test_preposition_lookup_names_its_function_word_kind(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    assert _lookup("into", capsys)[1] == "into: preposition\n"


def test_and_is_a_rejected_function_word_with_a_hint(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    code, out, _ = _lookup("and", capsys)
    assert code == 0
    assert out == ("and: rejected\n"
                   "  one action per name: split the function, or name the combined step\n")


def test_irregular_plural_listed_on_the_entry_overrides_the_rule(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    assert _lookup("indices", capsys)[1] == "index: noun\n  indices is the plural form of index\n"
    assert _lookup("indexes", capsys)[0] == 1


def test_missing_domain_file_refuses(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, OPTED_IN)
    code, _, err = _lookup("position", capsys)
    assert code == 2
    assert str(tmp_path / DOMAIN) in err


def test_lookup_falls_back_to_core_when_git_is_absent_from_path(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    code, out, _ = _lookup("position", capsys)
    assert code == 0
    assert out.startswith("position: noun\n")


def _domain(tmp_path: Path, text: str) -> vocabulary.Dictionary:
    (tmp_path / DOMAIN).write_text(text)
    return vocabulary.load(tmp_path, DOMAIN)


def _refusal(tmp_path: Path, text: str) -> str:
    with pytest.raises(GateError) as exc:
        _domain(tmp_path, text)
    return str(exc.value)


CONCEPT = '[[concept]]\nword = "frob"\npos = ["verb"]\n'


def test_concept_without_meaning_is_refused(tmp_path):
    assert "`frob` needs a non-empty `meaning`" in _refusal(tmp_path, CONCEPT)


def test_concept_with_empty_meaning_is_refused(tmp_path):
    assert "`frob` needs a non-empty `meaning`" in _refusal(tmp_path, CONCEPT + 'meaning = ""\n')


def test_concept_without_pos_is_refused(tmp_path):
    text = '[[concept]]\nword = "frob"\nmeaning = "x"\n'
    assert "`frob` needs a non-empty `pos`" in _refusal(tmp_path, text)


def test_concept_with_unknown_key_is_refused(tmp_path):
    text = CONCEPT + 'meaning = "x"\nrejects = ["frobnicate"]\n'
    assert "`frob` has unknown key(s) rejects" in _refusal(tmp_path, text)


def test_pos_outside_noun_verb_adjective_is_refused(tmp_path):
    text = '[[concept]]\nword = "frob"\nmeaning = "x"\npos = ["adverb"]\n'
    assert "`frob`: pos adverb is not one of noun, verb, adjective" in _refusal(tmp_path, text)


def test_form_outside_the_five_fixed_forms_is_refused(tmp_path):
    text = CONCEPT + 'meaning = "x"\nforms = ["-ly"]\n'
    assert "`frob`: form -ly is not one of plural, -s, -ed, -ing, -er" in _refusal(tmp_path, text)


def test_irregular_form_outside_the_five_fixed_forms_is_refused(tmp_path):
    text = CONCEPT + 'meaning = "x"\nirregular = { "-ly" = "frobly" }\n'
    assert "`frob`: form -ly is not one of plural, -s, -ed, -ing, -er" in _refusal(tmp_path, text)


def test_returns_outside_value_or_none_is_refused(tmp_path):
    text = CONCEPT + 'meaning = "x"\nreturns = "bool"\n'
    assert "`frob`: returns bool is not one of value, none" in _refusal(tmp_path, text)


def test_reject_pointing_at_a_word_that_is_not_canonical_is_refused(tmp_path):
    assert "[reject] loc = 'place': `place` is not canonical" in _refusal(
        tmp_path, '[reject]\nloc = "place"\n'
    )


def test_reject_spelling_that_is_canonical_elsewhere_is_refused(tmp_path):
    text = CONCEPT + 'meaning = "x"\nreject = ["frame"]\n'
    assert "`frame` (rejected) is already canonical `frame`" in _refusal(tmp_path, text)


def test_derived_form_colliding_with_another_concept_is_refused(tmp_path):
    text = ('[[concept]]\nword = "loader"\nmeaning = "x"\npos = ["noun"]\n'
            '[[concept]]\nword = "load"\nmeaning = "y"\npos = ["verb"]\nforms = ["-er"]\n')
    assert "`loader` (form) is already canonical `loader`" in _refusal(tmp_path, text)


def test_same_concept_may_spell_a_form_like_its_own_word(tmp_path):
    text = CONCEPT + 'meaning = "x"\nforms = ["-ed"]\nirregular = { "-ed" = "frob" }\n'
    match = _domain(tmp_path, text).resolve("frob")
    assert (match.word, match.kind, match.detail) == ("frob", "canonical", "forms: frob")


def test_distinct_pair_naming_a_non_canonical_word_is_refused(tmp_path):
    text = '[[distinct]]\npair = ["frame", "pos"]\n'
    assert "[[distinct]] ['frame', 'pos'] names a word that is not canonical" in _refusal(
        tmp_path, text
    )


def test_distinct_pair_of_canonical_words_loads(tmp_path):
    loaded = _domain(tmp_path, '[[distinct]]\npair = ["frame", "index"]\n')
    assert loaded.distinct == frozenset({frozenset({"frame", "index"})})


def test_distinct_entry_that_is_not_a_pair_is_refused(tmp_path):
    text = '[[distinct]]\npair = ["frame"]\n'
    assert "[[distinct]] ['frame'] is not a pair" in _refusal(tmp_path, text)


def test_domain_file_may_not_define_function_words(tmp_path):
    text = '[function_words]\npreposition = ["via"]\n'
    assert "unknown table(s) function_words" in _refusal(tmp_path, text)


def test_domain_may_add_vague_words_but_not_canonical_ones(tmp_path):
    loaded = _domain(tmp_path, '[[vague]]\nword = "thing"\nhint = "name it"\n')
    assert loaded.resolve("thing").detail == "name it"
    assert "`frame` (vague) is already canonical `frame`" in _refusal(
        tmp_path, '[[vague]]\nword = "frame"\nhint = "no"\n'
    )


def test_domain_collection_types_join_the_core_ones(tmp_path):
    loaded = _domain(tmp_path, '[collection]\ntypes = ["FrameList"]\n')
    assert {"list", "FrameList"} <= loaded.collections


def test_head_and_returns_are_carried_on_the_concept(tmp_path):
    loaded = _domain(tmp_path, CONCEPT + 'meaning = "x"\nreturns = "none"\nhead = true\n')
    assert loaded.concepts["count"].head is True
    assert loaded.concepts["frame"].head is False
    assert loaded.concepts["frob"].head is True
    assert loaded.concepts["frob"].returns == "none"
    assert loaded.concepts["count"].returns == ""


@pytest.mark.parametrize(("word", "form", "expected"), [
    ("position", "plural", "positions"),
    ("class", "plural", "classes"),
    ("index", "plural", "indexes"),
    ("buzz", "-s", "buzzes"),
    ("match", "-s", "matches"),
    ("push", "-s", "pushes"),
    ("query", "plural", "queries"),
    ("try", "plural", "tries"),
    ("key", "plural", "keys"),
    ("deploy", "-s", "deploys"),
    ("parse", "-ed", "parsed"),
    ("parse", "-ing", "parsing"),
    ("parse", "-er", "parser"),
    ("free", "-ed", "freed"),
    ("free", "-ing", "freeing"),
    ("copy", "-ed", "copied"),
    ("copy", "-ing", "copying"),
    ("copy", "-er", "copier"),
    ("stop", "-ed", "stopped"),
    ("stop", "-ing", "stopping"),
    ("run", "-er", "runner"),
    ("fix", "-ed", "fixed"),
    ("show", "-ed", "showed"),
    ("play", "-ed", "played"),
    ("open", "-ed", "opened"),
    ("need", "-ed", "needed"),
    ("add", "-ed", "added"),
    ("count", "-ing", "counting"),
    ("load", "-er", "loader"),
])
def test_fixed_rule_derives_the_form(word, form, expected):
    assert vocabulary.derive(word, form) == expected


LOC_FRAME_FILES = {
    "pkg/a.py": (
        "loc = 1\n"
        "def read(loc):\n"
        "    return loc\n"
        "class Frame:\n"
        "    loc = 1\n"
        "frame_count = 1\n"
    ),
}


def _audit_repo(tmp_path, monkeypatch, files: dict[str, str], toml: str = "",
                 domain: str | None = None) -> Repo:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (tmp_path / ".mutation-gate.toml").write_text(toml)
    if domain is not None:
        (tmp_path / DOMAIN).write_text(domain)
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config.load(tmp_path))
    monkeypatch.setattr(vocabulary, "discover", lambda cwd=None: repo)
    listing = "\0".join(sorted(files)) + "\0"
    monkeypatch.setattr(vocabulary_check, "git", lambda *a, cwd=None: listing)
    return repo


def _audit(argv: list[str], capsys) -> tuple[int, str, str]:
    code = cli.main(["vocabulary", "audit", *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_audit_lists_loc_at_frequency_three_with_a_sample_and_exits_zero_core_only(
    tmp_path, monkeypatch, capsys
):
    _audit_repo(tmp_path, monkeypatch, LOC_FRAME_FILES)
    code, out, _ = _audit([], capsys)
    assert code == 0
    assert out == (
        "unknown words:\n"
        "  loc (3) — pkg/a.py:1: variable `loc` — `loc` is not in the dictionary\n"
        "per-rule counts:\n"
        "  field: 1\n"
        "  parameter: 1\n"
        "  variable: 1\n"
    )


MIXED_UNKNOWN_FILES = {
    "pkg/a.py": (
        "class FrameManager:\n"
        "    pass\n"
        "loc = 1\n"
        "def read(loc):\n"
        "    return loc\n"
        "frob = 1\n"
    ),
}


def test_audit_ranks_unknown_words_by_frequency_past_a_non_unknown_finding(
    tmp_path, monkeypatch, capsys
):
    _audit_repo(tmp_path, monkeypatch, MIXED_UNKNOWN_FILES)
    code, out, _ = _audit([], capsys)
    assert code == 0
    assert out == (
        "unknown words:\n"
        "  loc (2) — pkg/a.py:3: variable `loc` — `loc` is not in the dictionary\n"
        "  frob (1) — pkg/a.py:6: variable `frob` — `frob` is not in the dictionary\n"
        "per-rule counts:\n"
        "  parameter: 1\n"
        "  type: 1\n"
        "  variable: 2\n"
    )


def test_audit_domain_reject_of_loc_removes_it_from_unknown_words(tmp_path, monkeypatch, capsys):
    _audit_repo(tmp_path, monkeypatch, LOC_FRAME_FILES, OPTED_IN, '[reject]\nloc = "position"\n')
    code, out, _ = _audit([], capsys)
    assert code == 0
    assert "loc (" not in out
    assert out.count("per-rule counts:\n") == 1


def test_audit_format_toml_stub_is_accepted_once_meaning_is_filled(tmp_path, monkeypatch, capsys):
    _audit_repo(tmp_path, monkeypatch, {"pkg/a.py": "loc = 1\n"})
    code, out, _ = _audit(["--format", "toml"], capsys)
    assert code == 0
    assert out == '[[concept]]\nword = "loc"\nmeaning = ""\npos = ["noun"]\n\n'
    filled = out.replace('meaning = ""', 'meaning = "where a thing is"')
    (tmp_path / DOMAIN).write_text(filled)
    match = vocabulary.load(tmp_path, DOMAIN).resolve("loc")
    assert match is not None
    assert (match.word, match.kind) == ("loc", "canonical")


def test_audit_format_toml_stub_with_blank_meaning_is_refused_by_the_loader(
    tmp_path, monkeypatch, capsys
):
    _audit_repo(tmp_path, monkeypatch, {"pkg/a.py": "loc = 1\n"})
    _, out, _ = _audit(["--format", "toml"], capsys)
    (tmp_path / DOMAIN).write_text(out)
    with pytest.raises(GateError, match="needs a non-empty `meaning`"):
        vocabulary.load(tmp_path, DOMAIN)


LEADING_UNDERSCORE_FILES = {
    "pkg/a.py": "def _parse_frame():\n    pass\n\n\ndef __repr__():\n    return ''\n",
    "src/_impl.py": "x = 1\n",
    "__init__.py": "",
}


def test_leading_underscore_lists_exactly_the_function_and_the_module_path(
    tmp_path, monkeypatch, capsys
):
    _audit_repo(tmp_path, monkeypatch, LEADING_UNDERSCORE_FILES)
    code = cli.main(["vocabulary", "audit", "--leading-underscore"])
    out = capsys.readouterr().out
    assert code == 0
    assert out == (
        "pkg/a.py:1 _parse_frame parse_frame_\n"
        "src/_impl.py:0 _impl.py impl_.py\n"
    )


def test_audit_refuses_when_not_a_git_repository(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vocabulary, "discover", lambda cwd=None: (_ for _ in ()).throw(
        GateError("not a git repository")))
    code = cli.main(["vocabulary", "audit"])
    assert code == 2
    assert "not a git repository" in capsys.readouterr().err


def test_audit_refuses_on_a_broken_domain_file(tmp_path, monkeypatch, capsys):
    _audit_repo(tmp_path, monkeypatch, {"pkg/a.py": "loc = 1\n"}, OPTED_IN,
                '[[concept]]\nword = "frob"\n')
    code = cli.main(["vocabulary", "audit"])
    assert code == 2
    assert "mutation-gate vocabulary refused" in capsys.readouterr().err
