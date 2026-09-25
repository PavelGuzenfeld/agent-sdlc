"""Intent: #290. gcc and clang predefine the same macros at -O2 and -O3 (`cpp -dM`
diffs empty), so the guard can only demand a level the build line names; this pins
that line, since the gate's container has no compiler."""

import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SKILL = Path(__file__).resolve().parent.parent / "SKILL.md"
GUARDED_BENCHES = ["unit_bench.cpp", "sched_bench.cpp", "load_gen.cpp"]
REQUIRED_DEFINE = "BENCH_OPTIMIZATION_LEVEL"


def _guard(bench):
    text = (SCRIPTS / bench).read_text()
    start = text.index("#if")
    return text[start:text.index("#endif", start) + len("#endif")]


def _build_comment(bench):
    return next(line for line in (SCRIPTS / bench).read_text().splitlines()
                if line.startswith("// Build:"))


def _skill_build_line(bench):
    return next(line for line in SKILL.read_text().splitlines()
                if bench in line and "g++" in line)


@pytest.mark.parametrize("bench", GUARDED_BENCHES)
def test_an_unoptimised_build_is_still_refused(bench):
    assert "__OPTIMIZE__" in _guard(bench)


@pytest.mark.parametrize("bench", GUARDED_BENCHES)
def test_the_guard_requires_a_level_the_build_line_must_name(bench):
    assert REQUIRED_DEFINE in _guard(bench)


@pytest.mark.parametrize("bench", GUARDED_BENCHES)
def test_the_required_level_is_three_not_two(bench):
    assert re.search(rf"{REQUIRED_DEFINE}\s*<\s*3", _guard(bench))


@pytest.mark.parametrize("bench", GUARDED_BENCHES)
def test_the_skill_prescribed_build_line_passes_o3_and_the_level_together(bench):
    assert f"-O3 -D{REQUIRED_DEFINE}=3" in _skill_build_line(bench)


@pytest.mark.parametrize("bench", GUARDED_BENCHES)
def test_the_header_build_comment_matches_the_skill_prescribed_line(bench):
    assert f"-O3 -D{REQUIRED_DEFINE}=3" in _build_comment(bench)
