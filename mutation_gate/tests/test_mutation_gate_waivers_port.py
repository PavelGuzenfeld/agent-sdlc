"""Issue #60: the waivers ported from dotfiles#9 must still match this repo's tree."""

from pathlib import Path

from mutation_gate import mutants as mutants_mod
from mutation_gate.repo import Config, Repo
from mutation_gate.waivers import load, stale

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PORTED_PATH_PREFIXES = ("mutation_gate/", "skills/sol-budget/scripts/")


def _repo() -> Repo:
    return Repo(root=REPO_ROOT, origin="", remotes=(), config=Config.load(REPO_ROOT))


def test_the_ported_waivers_file_exists_and_covers_both_moved_paths():
    waivers = load(_repo())
    files = {w.file for w in waivers}
    assert files, ".mutation-gate-waivers.toml is missing or empty"
    assert any(f.startswith("mutation_gate/") for f in files)
    assert any(f.startswith("skills/sol-budget/scripts/") for f in files)
    assert all(f.startswith(PORTED_PATH_PREFIXES) for f in files)


def test_no_ported_waiver_has_drifted_off_its_current_mutant():
    waivers = load(_repo())
    site_scoped = [w for w in waivers if w.line and not w.uncovered and not w.check]
    files = sorted({w.file for w in site_scoped})
    assert files, "no line-scoped waivers to check"
    for rel in files:
        path = REPO_ROOT / rel
        n_lines = len(path.read_bytes().splitlines())
        every_mutant = mutants_mod.generate(REPO_ROOT, {rel: set(range(1, n_lines + 1))}, "python")
        drifted = stale(waivers, rel, every_mutant)
        assert drifted == [], f"{rel}: waiver(s) no longer match a mutant: {drifted}"
