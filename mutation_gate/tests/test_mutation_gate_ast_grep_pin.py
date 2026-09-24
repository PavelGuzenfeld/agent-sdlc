"""Issue #244: the mutant catalogue depends on the installed ast-grep version,
so every install path must resolve the same one CI's waivers were pinned
against."""

import re
from pathlib import Path

import pytest

from mutation_gate.mutants import PINNED_AST_GREP_VERSION

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PIN_RE = re.compile(r"ast-grep-cli(==[^\s\"'\]]*)?")

PIN_SITES = (
    "pyproject.toml",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    ".mutation-gate.toml",
    "install.sh",
)


@pytest.mark.parametrize("rel", PIN_SITES)
def test_every_ast_grep_cli_reference_is_pinned_to_the_pinned_version(rel):
    text = (REPO_ROOT / rel).read_text()
    pins = PIN_RE.findall(text)
    assert pins, f"{rel}: no ast-grep-cli reference found"
    assert pins == [f"=={PINNED_AST_GREP_VERSION}"] * len(pins)
