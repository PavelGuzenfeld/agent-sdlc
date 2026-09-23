"""`mutation-gate diff-discipline` (#71 decision 9): over LINE_LIMIT added production
lines against the default branch's merge-base needs a `N-slug` branch or `#N` in a
branch commit message. V&V artefacts: model_test_paths, [[golden]], a file model_spec."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .commit_msg import _strip_editor_cruft
from .model_vv import _under
from .repo import Config, GateError, Repo, discover, git

LINE_LIMIT = 40
DEFAULT_BRANCH_CANDIDATES = ("origin/main", "origin/master", "main", "master")

_TICKET_BRANCH_RE = re.compile(r"^\d+-")
_TICKET_REF_RE = re.compile(r"#\d+")


@dataclass(frozen=True)
class Count:
    production: Counter[str]
    tests: int
    artefacts: int

    @property
    def total(self) -> int:
        return sum(self.production.values())


def default_branch(root: Path) -> str | None:
    try:
        return git("symbolic-ref", "-q", "refs/remotes/origin/HEAD", cwd=root).strip()
    except GateError:
        pass
    for candidate in DEFAULT_BRANCH_CANDIDATES:
        try:
            git("rev-parse", "--verify", "-q", candidate, cwd=root)
        except GateError:
            continue
        return candidate
    return None


def is_vv_artefact(config: Config, rel: str) -> bool:
    files = {g.source for g in config.golden} | {g.artifact for g in config.golden}
    if not config.model_spec.startswith("issue:"):
        files.add(config.model_spec)
    return rel in files or _under(rel, config.model_test_paths)


def added_lines(repo: Repo, *diff_args: str) -> Count:
    """Renames are not detected, so a renamed file counts as added in full."""
    production: Counter[str] = Counter()
    tests = artefacts = 0
    out = git("diff", "--numstat", "-z", "--no-renames", *diff_args, cwd=repo.root)
    for record in out.split("\0"):
        if not record:
            continue
        added, _, rel = record.split("\t", 2)
        if added == "-":
            continue
        if repo.is_test(rel):
            tests += int(added)
        elif is_vv_artefact(repo.config, rel):
            artefacts += int(added)
        else:
            production[rel] += int(added)
    return Count(production, tests, artefacts)


def _emit(line: str) -> None:
    print(line, file=sys.stderr)


def _report(branch: str, rev_range: str, count: Count) -> None:
    _emit(f"diff-discipline: BLOCKED — {count.total} added production line(s) on branch "
          f"{branch!r} over {rev_range}, limit {LINE_LIMIT} without a ticket reference.")
    for rel, n in sorted(count.production.items()):
        _emit(f"  {rel}: {n}")
    _emit(f"  excluded: {count.tests} under test_paths, {count.artefacts} in V&V artefacts; "
          "deletions never count")
    _emit("To pass: open a ticket, then name the branch N-slug or put #N in a commit message.")


def _check(repo: Repo, branch: str | None, rev_range: str, message: str, diff_args: tuple[str, ...]) -> int:
    branch = branch or git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo.root).strip()
    if _TICKET_BRANCH_RE.match(branch):
        return 0
    messages = git("log", "--format=%B", rev_range, cwd=repo.root) + message
    if _TICKET_REF_RE.search(messages):
        return 0
    count = added_lines(repo, *diff_args)
    if count.total <= LINE_LIMIT:
        return 0
    _report(branch, rev_range, count)
    return 1


def _merge_heads(root: Path) -> list[str]:
    """MERGE_HEAD holds the commit(s) a `git merge` in progress is bringing in —
    one per line, several for an octopus merge."""
    merge_head = root / git("rev-parse", "--git-path", "MERGE_HEAD", cwd=root).strip()
    if not merge_head.exists():
        return []
    return merge_head.read_text().split()


def _local_base(root: Path) -> str | None:
    branch = default_branch(root)
    if branch is None:
        _emit("diff-discipline skipped: no default branch (origin/HEAD, origin/main, origin/master, main, master)")
        return None
    try:
        return git("merge-base", branch, "HEAD", *_merge_heads(root), cwd=root).strip()
    except GateError:
        _emit(f"diff-discipline skipped: no merge-base between {branch} and HEAD")
        return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mutation-gate diff-discipline")
    parser.add_argument("msgfile", nargs="?")
    parser.add_argument("--range", dest="rev_range")
    parser.add_argument("--branch", help="branch name when HEAD is detached (CI)")
    args = parser.parse_args(argv)

    try:
        repo = discover()
        if args.rev_range:
            return _check(repo, args.branch, args.rev_range, "", (args.rev_range,))
        if not args.msgfile:
            _emit("mutation-gate diff-discipline refused: msgfile or --range required")
            return 2
        message = _strip_editor_cruft(Path(args.msgfile).read_text())
        base = _local_base(repo.root)
        if base is None:
            return 0
        return _check(repo, args.branch, f"{base}..HEAD", message, ("--cached", base))
    except (GateError, OSError) as exc:
        _emit(f"mutation-gate diff-discipline refused: {exc}")
        return 2
