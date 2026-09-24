"""`mutation-gate no-new-docs` (#71 decision 10): a newly added `.md` file must
match the built-in allowlist, a `.md` under `test_paths`, or a repo's own
`doc_allow = [{glob, reason}]`. Edits to an existing `.md` file are not new."""

from __future__ import annotations

import argparse
import fnmatch
import sys
from collections.abc import Iterable, Sequence

from .repo import GateError, Repo, discover, git
from .rules import AGENTS_PATH, TARGET as SYNCED_RULES

DEFAULT_ALLOW = (
    "**/README*",
    "**/LICENSE*",
    "**/CONTRIBUTING*",
    "**/CODE_OF_CONDUCT*",
    "**/SECURITY*",
    "**/NOTICE*",
    "**/CHANGELOG*",
    ".github/**/*",
    str(AGENTS_PATH),
    f"{SYNCED_RULES}/**/*",
)


def added_md_files(repo: Repo, *diff_args: str) -> list[str]:
    out = git("diff", "--name-only", "-z", "--no-renames", "--diff-filter=A",
              *diff_args, cwd=repo.root)
    return sorted(p for p in out.split("\0") if p.endswith(".md"))


def _matches_parts(parts: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    if not pattern:
        return not parts
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        return any(_matches_parts(parts[i:], rest) for i in range(len(parts)))
    return bool(parts) and fnmatch.fnmatchcase(parts[0], head) and _matches_parts(parts[1:], rest)


def _matches(rel: str, pattern: str) -> bool:
    """fnmatch per path segment, never fnmatch's whole-string form — same
    reasoning as Repo._expand. A trailing bare `**` matches only directories,
    so it never matches a file, matching Path.glob + is_file()."""
    return _matches_parts(tuple(rel.split("/")), tuple(pattern.split("/")))


def _allowed(added: Iterable[str], patterns: Sequence[str]) -> set[str]:
    return {rel for rel in added if any(_matches(rel, pat) for pat in patterns)}


def _emit(line: str) -> None:
    print(line, file=sys.stderr)


def _report(blocked: list[str]) -> None:
    _emit(f"no-new-docs: BLOCKED — {len(blocked)} new .md file(s) outside the allowlist.")
    for rel in blocked:
        _emit(f"  {rel}")
    _emit("To pass: add a [[doc_allow]] entry with `glob` and a `reason` to .mutation-gate.toml, "
          "or move the file under test_paths.")


def _check(repo: Repo, *diff_args: str) -> int:
    added = added_md_files(repo, *diff_args)
    if not added:
        return 0
    patterns = list(DEFAULT_ALLOW) + [a.glob for a in repo.config.doc_allow]
    allowed = _allowed(added, patterns)
    blocked = [rel for rel in added if rel not in allowed and not repo.is_test(rel)]
    if not blocked:
        return 0
    _report(blocked)
    return 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mutation-gate no-new-docs")
    parser.add_argument("--range", dest="rev_range")
    args = parser.parse_args(argv)

    try:
        repo = discover()
        diff_args = (args.rev_range,) if args.rev_range else ("--cached",)
        return _check(repo, *diff_args)
    except (GateError, OSError) as exc:
        _emit(f"mutation-gate no-new-docs refused: {exc}")
        return 2
