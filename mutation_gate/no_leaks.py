"""`mutation-gate no-leaks` (#71 decision 12): the identity, RFC1918 and
home-path scan from scripts/no-leaks.sh, plus an optional `banned_names_file`
of `X → Y` lines, over the staged diff and commit message. Never echoes the matched text."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .commit_msg import _strip_editor_cruft, _word_pattern
from .repo import GateError, Repo, discover, git

_OCTET = r"[0-9]{1,3}"
_IDENTITY_RE = re.compile(
    r"(^|[^A-Za-z0-9._%+/-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*"
)
_RFC1918_RE = re.compile(
    rf"(^|[^0-9.])(10\.{_OCTET}|192\.168|172\.(1[6-9]|2[0-9]|3[01]))\.{_OCTET}\.{_OCTET}([^0-9]|$)"
)
_HOME_PATH_RE = re.compile(r"/home/[A-Za-z0-9._-]+/")

_GIT_SSH_CLONE_RE = re.compile(
    r"(^|[^A-Za-z0-9._%+/-])git@(github\.com|gitlab\.com|bitbucket\.org):"
)
_NPM_VERSION_RE = re.compile(
    r"(^|[^A-Za-z0-9._%+/-])[A-Za-z0-9._%+-]+@[0-9]+\.[0-9]+\.[0-9]+([^0-9.]|$)"
)

_BULLET_RE = re.compile(r"^\s*-\s*")
_ARROW = "→"


@dataclass(frozen=True)
class BannedName:
    token: str
    replacement: str


def _carve_out(line: str) -> str:
    line = _GIT_SSH_CLONE_RE.sub(r"\1public-git-ssh-clone-url", line)
    return _NPM_VERSION_RE.sub(r"\1npm-package-version\2", line)


def generic_hit(line: str) -> bool:
    line = _carve_out(line)
    return bool(_IDENTITY_RE.search(line) or _RFC1918_RE.search(line) or _HOME_PATH_RE.search(line))


def _clean(token: str) -> str:
    return token.strip().strip("`").strip()


def parse_banned_names(text: str) -> list[BannedName]:
    out: list[BannedName] = []
    for raw in text.splitlines():
        if _ARROW not in raw:
            continue
        left, _, right = _BULLET_RE.sub("", raw).partition(_ARROW)
        replacement = _clean(right)
        if not replacement:
            continue
        for token in left.split("/"):
            token = _clean(token)
            if token:
                out.append(BannedName(token=token, replacement=replacement))
    return out


def load_banned_names(path_str: str) -> list[BannedName]:
    if not path_str:
        return []
    path = Path(path_str).expanduser()
    if not path.is_file():
        return []
    try:
        return parse_banned_names(path.read_text())
    except OSError as exc:
        raise GateError(f"banned_names_file: {exc}") from exc


def _banned_hit(line: str, name: BannedName) -> bool:
    return bool(_word_pattern(name.token).search(line))


def _diff_added_lines(repo: Repo, *diff_args: str) -> list[tuple[str, int, str]]:
    out = git("diff", "-U0", "--no-color", "--no-renames", *diff_args, cwd=repo.root)
    hits: list[tuple[str, int, str]] = []
    current: str | None = None
    in_hunk = False
    next_line = 0
    for raw in out.splitlines():
        if raw.startswith("diff --git "):
            current, in_hunk = None, False
        elif not in_hunk and raw.startswith("+++ "):
            current = raw[6:] if raw.startswith("+++ b/") else None
        elif raw.startswith("@@"):
            in_hunk = True
            m = re.search(r"\+(\d+)", raw)
            next_line = int(m.group(1)) if m else next_line
        elif in_hunk and current is not None and raw.startswith("+"):
            hits.append((current, next_line, raw[1:]))
            next_line += 1
    return hits


def _range_messages(repo: Repo, rev_range: str) -> list[tuple[str, str]]:
    out = git("log", "-z", rev_range, "--pretty=format:%H%x1f%B", cwd=repo.root)
    result = []
    for record in out.split("\x00"):
        if not record:
            continue
        sha, _, msg = record.partition("\x1f")
        result.append((sha, msg))
    return result


def _scan(items: list[tuple[str, int, str]], banned: list[BannedName]) -> list[str]:
    findings = []
    for where, line_no, text in items:
        if generic_hit(text):
            findings.append(f"{where}:{line_no}")
        for name in banned:
            if _banned_hit(text, name):
                findings.append(f'{where}:{line_no}: banned name — use "{name.replacement}"')
    return findings


def _emit(line: str) -> None:
    print(line, file=sys.stderr)


def _report(findings: list[str]) -> None:
    _emit(f"no-leaks: BLOCKED — {len(findings)} finding(s).")
    for f in findings:
        _emit(f"  {f}")


def _check(banned: list[BannedName], items: list[tuple[str, int, str]]) -> int:
    findings = _scan(items, banned)
    if not findings:
        return 0
    _report(findings)
    return 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mutation-gate no-leaks")
    parser.add_argument("msgfile", nargs="?")
    parser.add_argument("--range", dest="rev_range")
    args = parser.parse_args(argv)

    try:
        repo = discover()
        banned = load_banned_names(repo.config.banned_names_file)
        if args.rev_range:
            items = _diff_added_lines(repo, args.rev_range)
            for sha, msg in _range_messages(repo, args.rev_range):
                items += [(sha[:12], i, t) for i, t in enumerate(msg.splitlines(), start=1)]
            return _check(banned, items)
        if not args.msgfile:
            _emit("mutation-gate no-leaks refused: msgfile or --range required")
            return 2
        message = _strip_editor_cruft(Path(args.msgfile).read_text())
        items = _diff_added_lines(repo, "--cached")
        items += [("commit-msg", i, t) for i, t in enumerate(message.splitlines(), start=1)]
        return _check(banned, items)
    except (GateError, OSError) as exc:
        _emit(f"mutation-gate no-leaks refused: {exc}")
        return 2
