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
