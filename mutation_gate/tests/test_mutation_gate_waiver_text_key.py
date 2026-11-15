"""Intent: #388. A waiver that records its source line's text keeps covering its
mutant when lines above it move; ambiguity stays a stale warning."""

import contextlib

import pytest

from mutation_gate import cli, waivers
from mutation_gate.mutants import Mutant
from mutation_gate.repo import Config, GateError, Repo
from mutation_gate.waivers import Waiver, line_text, stale, suggest, waived

SITE = "total = base + extra"
TEXT_WAIVER = 'text = """total = base + extra"""\n'


def _waiver_file(line, text=TEXT_WAIVER):
    return (
        "[[waiver]]\n"
        'file = "a.py"\n'
        f"line = {line}\n"
        'old = """base + extra"""\n'
        'new = """base - extra"""\n'
        f"{text}"
        'reason = "r"\n'
    )


def _dry_run_err(tmp_path, monkeypatch, capsys, source, waiver_toml):
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    (tmp_path / "a.py").write_text(source)
    (tmp_path / ".mutation-gate-waivers.toml").write_text(waiver_toml)
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.model_vv, "git", lambda *a, **k: (_ for _ in ()).throw(GateError("no git")))
    assert cli.main(["--file", "a.py", "--dry-run"]) == 0
    return capsys.readouterr().err


def test_text_keyed_waiver_survives_lines_inserted_above_it(tmp_path, monkeypatch, capsys):
    source = "x = 1\ny = 2\ntotal = base + extra\n"
    err = _dry_run_err(tmp_path, monkeypatch, capsys, source, _waiver_file(line=1))
    assert "stale" not in err


def test_line_only_waiver_still_goes_stale_when_lines_move(tmp_path, monkeypatch, capsys):
    source = "x = 1\ny = 2\ntotal = base + extra\n"
    err = _dry_run_err(tmp_path, monkeypatch, capsys, source, _waiver_file(line=1, text=""))
    assert "waiver at line 1" in err and "stale" in err


def test_text_keyed_waiver_with_identical_twins_and_moved_line_is_stale(tmp_path, monkeypatch, capsys):
    source = "x = 1\ny = 2\ntotal = base + extra\ntotal = base + extra\n"
    err = _dry_run_err(tmp_path, monkeypatch, capsys, source, _waiver_file(line=1))
    assert "waiver at line 1" in err and "stale" in err


def test_text_keyed_waiver_with_identical_twins_uses_line_as_tiebreak(tmp_path, monkeypatch, capsys):
    source = "x = 1\ny = 2\ntotal = base + extra\ntotal = base + extra\n"
    err = _dry_run_err(tmp_path, monkeypatch, capsys, source, _waiver_file(line=4))
    assert "stale" not in err


def _mutant(line, column=0):
    return Mutant(file="a.py", line=line, start=0, end=1, old="base + extra", new="base - extra", kind="operator",
                  column=column)


def _waiver(line, column=0):
    return Waiver(reason="r", file="a.py", line=line, column=column, old="base + extra", new="base - extra", text=SITE)


def test_twin_at_the_recorded_line_is_covered_and_the_other_is_not():
    lines = ["x = 1", "y = 2", SITE, SITE]
    every = [_mutant(3), _mutant(4)]
    assert waived([_waiver(4)], every[1], every, lines) is not None
    assert waived([_waiver(4)], every[0], every, lines) is None


def test_mutant_on_a_different_line_text_is_not_covered_even_at_the_recorded_line():
    lines = ["total = base + other"]
    mutant = _mutant(1)
    assert waived([_waiver(1)], mutant, [mutant], lines) is None


def test_moved_site_is_not_stale_when_its_line_text_is_found_elsewhere():
    lines = ["x = 1", "y = 2", SITE]
    assert stale([_waiver(1)], "a.py", [_mutant(3)], lines) == []


def test_suggested_waiver_records_the_line_text_and_loads_back(tmp_path):
    text = suggest(_mutant(7), SITE)
    assert f'text = """{SITE}"""' in text
    (tmp_path / ".mutation-gate-waivers.toml").write_text(text.replace("REPLACE ME", "because"))
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    assert waivers.load(repo)[0].text == SITE


def test_suggested_waiver_without_text_has_no_text_key():
    assert "text = " not in suggest(_mutant(7))


def test_waiver_column_picks_between_twins_on_one_line():
    lines = ["x = 1", SITE]
    every = [_mutant(2, column=3), _mutant(2, column=9)]
    assert waived([_waiver(2, column=9)], every[1], every, lines) is not None
    assert waived([_waiver(2, column=9)], every[0], every, lines) is None


@pytest.mark.parametrize("line", [0, -1, 3])
def test_line_text_outside_the_file_is_empty(line):
    assert line_text(["a", "b"], line) == ""


def test_line_text_is_the_stripped_line():
    assert line_text(["a", "  b = 1  "], 2) == "b = 1"


def _gate_one_file(tmp_path, monkeypatch, wvs, generated, source):
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    (tmp_path / "a.py").write_text(source)
    whole_file_scans = []

    def fake_generate(root, files, language):
        if files["a.py"] == set(range(1, len(source.splitlines()) + 1)):
            whole_file_scans.append(1)
        return generated

    monkeypatch.setattr(cli.mutants, "generate", fake_generate)
    monkeypatch.setattr(cli.coverage_map, "candidates", lambda repo, rel: [tmp_path / "t.py"])
    monkeypatch.setattr(cli.coverage_map, "blob_hashes", lambda repo, paths: ["h"])
    monkeypatch.setattr(cli.coverage_map, "covering_tests", lambda *a: {})
    monkeypatch.setattr(cli.token, "is_valid", lambda *a: False)
    monkeypatch.setattr(cli.token, "write", lambda *a: None)
    monkeypatch.setattr(cli.runner, "baseline_green", lambda *a: 1.0)
    monkeypatch.setattr(cli.runner, "rerun_unmutated", lambda *a: None)
    monkeypatch.setattr(cli.runner, "classify", lambda repo, m, *a: cli.runner.Result(m, cli.runner.SURVIVED, []))
    _, survivors, _ = cli._gate_file(repo, "a.py", {1, 2, 3, 4}, wvs, on_demand=True)
    return survivors, whole_file_scans


def test_gate_waives_only_the_twin_at_the_recorded_line(tmp_path, monkeypatch):
    source = f"x = 1\ny = 2\n{SITE}\n{SITE}\n"
    generated = [_mutant(3), _mutant(4)]
    survivors, _ = _gate_one_file(tmp_path, monkeypatch, [_waiver(4)], generated, source)
    assert survivors == [generated[0]]


def test_gate_skips_the_whole_file_scan_when_no_waiver_for_the_file_has_text(tmp_path, monkeypatch):
    other = Waiver(reason="r", file="b.py", old="base + extra", new="base - extra", text=SITE)
    _, scans = _gate_one_file(tmp_path, monkeypatch, [other], [_mutant(3)], f"x = 1\ny = 2\n{SITE}\n")
    assert scans == []


def test_blocked_run_suggests_the_first_survivor_with_its_line_text(tmp_path, monkeypatch, capsys):
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    (tmp_path / "a.py").write_text(f"first = 1\n{SITE}\n")
    first, second = _mutant(1), _mutant(2)
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "require_ast_grep", lambda: None)
    monkeypatch.setattr(cli.model_vv, "git", lambda *a, **k: (_ for _ in ()).throw(GateError("no git")))
    monkeypatch.setattr(cli, "_gate_file", lambda *a, **kw: (True, [first, second], []))
    assert cli.main(["--file", "a.py"]) == 1
    suggestion = capsys.readouterr().err.partition("[[waiver]]")[2]
    assert "line = 1\n" in suggestion
    assert 'text = """first = 1"""' in suggestion


def test_waiver_covers_its_mutant_after_the_site_moves_down_two_lines():
    lines = ["x = 1", "y = 2", SITE]
    mutant = _mutant(3)
    assert waived([_waiver(1)], mutant, [mutant], lines) is not None


def test_waiver_with_identical_twins_and_a_moved_line_covers_neither():
    lines = ["x = 1", "y = 2", SITE, SITE]
    every = [_mutant(3), _mutant(4)]
    assert [waived([_waiver(1)], m, every, lines) for m in every] == [None, None]


def test_matching_line_text_does_not_cover_a_different_mutation_of_the_line():
    lines = [SITE]
    other = Mutant(file="a.py", line=1, start=0, end=1, old="base + extra", new="base * extra",
                   kind="operator", column=0)
    assert waived([_waiver(1)], other, [other], lines) is None


def test_matching_line_text_does_not_cover_the_same_mutation_in_another_file():
    other = Mutant(file="b.py", line=1, start=0, end=1, old="base + extra", new="base - extra",
                   kind="operator", column=0)
    assert waived([_waiver(1)], other, [other], [SITE]) is None


INDENTED_SOURCE = "def f():\n    total = base + extra\n"
INDENTED_TEXT = '    total = base + extra'


def test_waiver_text_keeping_the_source_indentation_waives_its_mutant(tmp_path):
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    (tmp_path / ".mutation-gate-waivers.toml").write_text(
        _waiver_file(line=2, text=f'text = """{INDENTED_TEXT}"""\n')
    )
    mutant = _mutant(2)
    lines = INDENTED_SOURCE.splitlines()
    assert waived(waivers.load(repo), mutant, [mutant], lines) is not None


def test_text_mismatch_warning_names_text_with_both_values(tmp_path, monkeypatch, capsys):
    waiver_toml = _waiver_file(line=2, text='text = """total = other"""\n')
    err = _dry_run_err(tmp_path, monkeypatch, capsys, INDENTED_SOURCE, waiver_toml)
    assert (
        "a.py: waiver at line 2 column 0 matches on every field but text: "
        "waiver 'total = other' vs source 'total = base + extra'\n"
    ) in err
    assert "edit above" not in err


def test_text_mismatch_warning_is_given_for_every_stale_waiver(tmp_path, monkeypatch, capsys):
    two_waivers = _waiver_file(line=2, text='text = """first"""\n') + _waiver_file(
        line=2, text='text = """second"""\n'
    )
    err = _dry_run_err(tmp_path, monkeypatch, capsys, INDENTED_SOURCE, two_waivers)
    assert "waiver 'first' vs source" in err and "waiver 'second' vs source" in err


def test_text_mismatch_warning_names_text_when_the_waiver_column_matches(tmp_path, monkeypatch, capsys):
    waiver_toml = _waiver_file(line=2, text='text = """total = other"""\n').replace(
        "line = 2\n", "line = 2\ncolumn = 12\n"
    )
    err = _dry_run_err(tmp_path, monkeypatch, capsys, INDENTED_SOURCE, waiver_toml)
    assert "waiver at line 2 column 12 matches on every field but text" in err


def test_waiver_without_text_has_no_text_error():
    mutant = _mutant(2)
    lines = INDENTED_SOURCE.splitlines()
    textless = Waiver(reason="r", file="a.py", line=2, old="base + extra", new="base - extra")
    assert waivers.find_text_error(textless, [mutant], lines) is None


def _load_text(tmp_path, text_line):
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    (tmp_path / ".mutation-gate-waivers.toml").write_text(_waiver_file(line=2, text=text_line))
    return waivers.load(repo)[0]


def test_loaded_waiver_text_drops_tab_indentation(tmp_path):
    assert _load_text(tmp_path, f'text = """\t{SITE}"""\n').text == SITE


def test_loaded_waiver_text_drops_trailing_whitespace(tmp_path):
    assert _load_text(tmp_path, f'text = """{SITE}  \t"""\n').text == SITE


def test_indented_waiver_text_returns_the_loaded_waiver_at_a_nonzero_column(tmp_path):
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    toml = _waiver_file(line=2, text=f'text = """{INDENTED_TEXT}"""\n').replace("line = 2\n", "line = 2\ncolumn = 12\n")
    (tmp_path / ".mutation-gate-waivers.toml").write_text(toml)
    loaded = waivers.load(repo)
    mutant = _mutant(2, column=12)
    assert waived(loaded, mutant, [mutant], INDENTED_SOURCE.splitlines()) is loaded[0]
    assert loaded[0].column == 12


def test_real_line_shift_gets_the_stale_after_an_edit_hint(tmp_path, monkeypatch, capsys):
    source = "x = 1\ny = 2\ntotal = base + extra\n"
    err = _dry_run_err(tmp_path, monkeypatch, capsys, source, _waiver_file(line=1, text=""))
    assert (
        "  a.py: waiver at line 1 column 0 matches no mutant "
        "— stale after an edit above it? ('base + extra' => 'base - extra')\n"
    ) in err


def test_indentation_only_text_difference_gives_no_warning(tmp_path, monkeypatch, capsys):
    waiver_toml = _waiver_file(line=2, text=f'text = """{INDENTED_TEXT}"""\n')
    err = _dry_run_err(tmp_path, monkeypatch, capsys, INDENTED_SOURCE, waiver_toml)
    assert "waiver at line" not in err
