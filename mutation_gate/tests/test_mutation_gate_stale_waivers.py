"""Intent: dotfiles#88. A waiver is keyed on line and column, so an edit above one
moves its target out from under it. It then matches nothing and its mutant returns as
an unwaived survivor, with nothing in the output saying a recorded decision stopped
applying. These tests are about saying so.
"""

from mutation_gate.mutants import Mutant
from mutation_gate.waivers import Waiver, stale


def _mutant(line, column=1, old="0", new="1", file="a.py"):
    return Mutant(file=file, line=line, start=0, end=1, old=old, new=new, kind="literal",
                  column=column)


def _waiver(line, column=1, old="0", new="1", file="a.py", **kw):
    return Waiver(reason="r", file=file, line=line, column=column, old=old, new=new, **kw)


def test_a_waiver_whose_line_moved_is_reported():
    # The whole failure: the mutant is now at 20, the waiver still says 10.
    assert stale([_waiver(10)], "a.py", [_mutant(20)]) == [_waiver(10)]


def test_a_waiver_that_still_matches_is_not_reported():
    assert stale([_waiver(10)], "a.py", [_mutant(10)]) == []


def test_a_waiver_for_a_different_file_is_not_reported():
    # Only the file being gated is checked; every other waiver in the repo legitimately
    # matches nothing in this run.
    assert stale([_waiver(10, file="b.py")], "a.py", [_mutant(20)]) == []


def test_an_uncovered_waiver_names_no_site_so_cannot_drift():
    assert stale([Waiver(reason="r", file="a.py", uncovered=True)], "a.py", []) == []


def test_a_model_finding_waiver_is_not_a_mutant_waiver():
    assert stale([Waiver(reason="r", file="a.py", check="no-spec")], "a.py", []) == []


def test_a_waiver_with_no_line_is_not_reported():
    # Deleting `line` deliberately widens a waiver to the whole file, so it matching
    # no mutant on this run says nothing about whether it drifted.
    assert stale([Waiver(reason="r", file="a.py", old="x", new="y")], "a.py", []) == []


def test_a_waiver_whose_column_moved_is_reported():
    # Same line, different column: two mutants can share a line, and the waiver is
    # scoped to one of them on purpose.
    assert stale([_waiver(10, column=5)], "a.py", [_mutant(10, column=9)]) == [_waiver(10, column=5)]


def test_a_waiver_whose_text_no_longer_matches_is_reported():
    # The line survived an edit but the expression on it changed. Keying only on
    # position would silently waive a mutation nobody reasoned about.
    assert stale([_waiver(10, old="a + b", new="a - b")], "a.py",
                 [_mutant(10, old="a * b", new="a / b")]) == [_waiver(10, old="a + b", new="a - b")]


def test_every_drifted_waiver_is_reported_not_just_the_first():
    # One edit moves all of them, which is exactly the case that cost six gate rounds.
    drifted = stale([_waiver(10), _waiver(11)], "a.py", [_mutant(20), _mutant(21)])
    assert len(drifted) == 2


import pytest  # noqa: E402

from mutation_gate import cli, mutants as mutants_mod, repo as repo_mod  # noqa: E402


@pytest.fixture
def warn(tmp_path, monkeypatch, capsys):
    """Run the gate's warning against a real file and a chosen mutant set."""
    repo = repo_mod.Repo(root=tmp_path, origin="", remotes=(), config=repo_mod.Config())
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n")

    def _warn(waiver_list, every):
        def fake(*a, **k):
            if isinstance(every, Exception):
                raise every
            return every

        monkeypatch.setattr(mutants_mod, "generate", fake)
        cli._warn_stale_waivers(repo, "a.py", waiver_list)
        return capsys.readouterr().err

    return _warn


def test_a_drifted_waiver_is_named_in_the_output(warn):
    # The whole point of #88: without this the run says only that a mutant survived.
    out = warn([_waiver(1)], [_mutant(2)])
    assert "stale" in out and "line 1" in out


def test_a_waiver_that_still_matches_produces_no_noise(warn):
    assert warn([_waiver(1)], [_mutant(1)]) == ""


def test_a_file_with_no_site_waivers_is_not_scanned(warn):
    # The guard exists so the extra generator pass is skipped where it cannot help.
    assert warn([Waiver(reason="r", file="a.py", uncovered=True)], [_mutant(2)]) == ""


def test_a_waiver_on_the_last_line_of_the_file_is_still_checked(warn):
    # The scanned range must cover the whole file. One line short and a waiver at
    # the end is invisible to the check — silently, which is what it exists to stop.
    out = warn([_waiver(3, old="x", new="y")], [_mutant(3, old="p", new="q")])
    assert "line 3" in out


def test_a_broken_scan_stays_silent_rather_than_failing_the_run(warn):
    # A warning that can fail a gate run is worse than no warning.
    assert warn([_waiver(1)], OSError("no such file")) == ""


def test_the_scan_covers_every_line_of_the_file(tmp_path, monkeypatch):
    # The check compares against the whole file, not the diff, because the waiver
    # whose line drifted is exactly the one the changed-line set will not contain.
    # A range that skips the first or last line reintroduces that blind spot.
    repo = repo_mod.Repo(root=tmp_path, origin="", remotes=(), config=repo_mod.Config())
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n")
    seen = {}

    def capture(root, changed, language):
        seen.update(changed)
        return []

    monkeypatch.setattr(mutants_mod, "generate", capture)
    cli._warn_stale_waivers(repo, "a.py", [_waiver(1)])
    assert seen["a.py"] == {1, 2, 3}
