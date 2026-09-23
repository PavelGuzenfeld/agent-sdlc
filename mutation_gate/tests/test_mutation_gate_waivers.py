"""Issue #67: what a waiver must and must not cover, straight from the intent
lines in waivers.py itself — a waiver-matching decision must be a decision, not
an accident of an unset field.
"""

from mutation_gate.mutants import Mutant
from mutation_gate.waivers import Waiver, suggest_finding, uncovered_waived


def _mutant(line, column=1, old="0", new="1", file="a.py"):
    return Mutant(file=file, line=line, start=0, end=1, old=old, new=new, kind="literal",
                  column=column)


def test_waiver_without_column_covers_mutant_at_any_column():
    waiver = Waiver(reason="r", file="a.py", line=10, old="0", new="1")
    assert waiver.covers(_mutant(10, column=7, old="0", new="1"))


def test_waiver_with_check_set_never_covers_a_mutant():
    waiver = Waiver(reason="r", file="a.py", check="no-spec", old="0", new="1")
    assert waiver.covers(_mutant(10, old="0", new="1")) is False


def test_uncovered_waiver_covers_mutant_with_different_old_new():
    waiver = Waiver(reason="r", file="a.py", uncovered=True)
    assert waiver.covers(_mutant(10, old="x", new="y"))


def test_waiver_with_different_new_text_does_not_cover_mutant():
    waiver = Waiver(reason="r", file="a.py", old="a == b", new="a != b")
    mutant = _mutant(10, old="a == b", new="a <= b")
    assert waiver.covers(mutant) is False


def test_finding_waiver_with_different_check_name_does_not_cover():
    waiver = Waiver(reason="r", check="no-spec", file="a.py")
    assert waiver.covers_finding("dangling", "a.py", "", 0, 0) is False


def test_finding_waiver_with_different_file_does_not_cover():
    waiver = Waiver(reason="r", check="no-spec", file="a.py")
    assert waiver.covers_finding("no-spec", "b.py", "", 0, 0) is False


def test_finding_waiver_without_ms_covers_finding_at_any_ms():
    waiver = Waiver(reason="r", check="no-spec", file="a.py")
    assert waiver.covers_finding("no-spec", "a.py", "", 7, 0) is True


def test_finding_waiver_with_ms_does_not_cover_a_different_ms():
    waiver = Waiver(reason="r", check="no-spec", file="a.py", ms=5)
    assert waiver.covers_finding("no-spec", "a.py", "", 6, 0) is False


def test_uncovered_waived_ignores_a_line_scoped_waiver_for_the_same_file():
    waiver = Waiver(reason="r", file="a.py", line=10, old="0", new="1")
    assert uncovered_waived([waiver], "a.py") is None


def test_uncovered_waived_ignores_a_different_files_uncovered_waiver():
    waiver = Waiver(reason="r", file="b.py", uncovered=True)
    assert uncovered_waived([waiver], "a.py") is None


def test_suggest_finding_omits_ms_line_when_ms_not_given():
    assert suggest_finding("no-spec", "a.py") == (
        '[[waiver]]\n'
        'check = "no-spec"\n'
        'file = "a.py"\n'
        'reason = "REPLACE ME — why no spec line can or should back this"\n'
    )
