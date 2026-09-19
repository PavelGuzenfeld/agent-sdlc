"""Decision 5 of #93 as a hook (dotfiles#100): a comment line the diff added blocks.

Opt-in per repo (`no_comments = true`), off by default so work repos and forks
keep their comments. Diff-scoped in content, not just in line number: a comment
is new only when the diff raised the count of comments with its text, so editing
`x = 1  # one` into `x = 2  # one` adds nothing and moving a comment adds
nothing. Runs before any mutant and runs no tests.
"""

from __future__ import annotations

import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import mutants, waivers
from .repo import GateError, Repo, git

CHECK = "no-comments"
LANGUAGES = ("python", "cpp")
# Directives a tool reads, not prose a human reads.
PRAGMA_RE = re.compile(r"^(?:#|//)\s*(?:pyright:|noqa|type:|ruff:|NOLINT|clang-format)")
LICENSE_RE = re.compile(r"SPDX-|copyright|licen[cs]e", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    text: str


def exempt(text: str) -> bool:
    return text.startswith("#!") or bool(PRAGMA_RE.match(text)) or bool(LICENSE_RE.search(text))


def comments(path: Path, lang: str) -> list[tuple[int, int, str]]:
    """(first line, last line, text), 1-based — the same `comment` kind the
    catalogue masks literals under, so both agree on what a comment is."""
    return [
        (h["range"]["start"]["line"] + 1, h["range"]["end"]["line"] + 1, h["text"])
        for h in mutants.kind_hits(path, lang, "comment")
    ]


def _pre_image_comments(repo: Repo, rel: str, lang: str, staged: bool) -> Counter[str]:
    """--staged gates the index against HEAD; --worktree gates the tree against the index."""
    try:
        text = git("show", f"{'HEAD' if staged else ''}:{rel}", cwd=repo.root)
    except GateError:
        return Counter()
    with tempfile.TemporaryDirectory(prefix="mutation-gate-pre-") as tmp:
        copy = Path(tmp) / Path(rel).name
        copy.write_text(text)
        return Counter(t for _, _, t in comments(copy, lang))


def _excluded(repo: Repo, rel: str) -> bool:
    return any(rel.startswith(p) for p in repo.config.exclude_paths)


def check(repo: Repo, changed: dict[str, set[int]], wvs, staged: bool) -> list[Finding]:
    out: list[Finding] = []
    for rel, lines in sorted(changed.items()):
        lang = mutants.language_of(rel)
        if lang not in LANGUAGES or _excluded(repo, rel) or not (repo.root / rel).exists():
            continue
        touched: list[tuple[int, str]] = []
        untouched: list[str] = []
        for first, last, text in comments(repo.root / rel, lang):
            added = lines & set(range(first, last + 1))
            if added:
                touched.append((min(added), text))
            else:
                untouched.append(text)
        # Untouched comments claim the pre-image's copies first, so a comment that
        # stayed where it was cannot excuse a new one with the same text.
        budget = _pre_image_comments(repo, rel, lang, staged)
        budget.subtract(untouched)
        for line, text in touched:
            if budget[text] > 0:
                budget[text] -= 1
                continue
            if exempt(text):
                continue
            if waivers.finding_waived(wvs, CHECK, rel, line=line):
                continue
            out.append(Finding(rel, line, text.splitlines()[0]))
    return out


def suggest(repo: Repo, f: Finding) -> str:
    return (
        "Delete the comment — a name, a type or a test holds what it says — or record a "
        f"waiver in {waivers.path(repo)}:\n"
        "[[waiver]]\n"
        f'check = "{CHECK}"\n'
        f'file = "{f.file}"\n'
        f"line = {f.line}\n"
        'reason = "REPLACE ME — why this comment carries what the code cannot"\n'
    )
