"""`mutation-gate commit-msg`: reject a commit message that uses a banned word
from the bundled voice.md's `Never use:` line, an AI Co-Authored-By trailer, a
"Generated with" line or a Signed-off-by trailer (#71 decision 11).

A banned word matches whole-word, case-insensitive ("robustness" does not
trip "robust"); a quoted phrase such as "it's worth noting" matches as a
substring, since it is not one word.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .repo import GateError, git
from .rules import RULES_DIR

VOICE_RULE = "voice.md"

AI_MARKERS = (
    "claude",
    "anthropic",
    "copilot",
    "chatgpt",
    "openai",
    "gpt",
    "gemini",
    "bard",
    "cursor",
    "codex",
)

_SIGNED_OFF_RE = re.compile(r"^signed-off-by:", re.IGNORECASE)
_GENERATED_WITH_RE = re.compile(r"^\W*generated with\b", re.IGNORECASE)
_CO_AUTHORED_BY_RE = re.compile(r"^co-authored-by:\s*(.+)$", re.IGNORECASE)
_NEVER_USE_RE = re.compile(r"Never use:(.*?)(?:\n[ \t]*\n|\Z)", re.DOTALL)
_ITEM_RE = re.compile(r'"([^"]*)"|([^,]+)')
_AUTO_COMMENT_HINT_RE = re.compile(r"^(\S) with '\1' will be ignored,", re.MULTILINE)


@dataclass(frozen=True)
class Finding:
    line_no: int
    line: str
    reason: str


def banned_words(voice_text: str) -> list[str]:
    match = _NEVER_USE_RE.search(voice_text)
    if not match:
        raise GateError(f"{VOICE_RULE}: no 'Never use:' line found")
    body = " ".join(part.strip() for part in match.group(1).splitlines()).strip()
    body = body.rstrip(".")
    body = re.sub(r",\s+", ",", body)
    items = []
    for quoted, bare in _ITEM_RE.findall(body):
        item = quoted if quoted else bare.strip()
        if item:
            items.append(item.lower())
    if not items:
        raise GateError(f"{VOICE_RULE}: 'Never use:' line parsed to no words")
    return items


def _voice_text() -> str:
    return (RULES_DIR / VOICE_RULE).read_text()


@lru_cache(maxsize=None)
def _word_pattern(word: str) -> re.Pattern:
    if " " in word:
        return re.compile(re.escape(word), re.IGNORECASE)
    return re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)


def _ai_marker(trailer_value: str) -> str | None:
    lowered = trailer_value.lower()
    for marker in AI_MARKERS:
        if re.search(rf"\b{re.escape(marker)}\b", lowered):
            return marker
    return None


@lru_cache(maxsize=None)
def _comment_patterns(comment_char: str) -> tuple[re.Pattern, re.Pattern]:
    escaped = re.escape(comment_char)
    scissors = re.compile(rf"^{escaped} -+ >8 -+ *$.*\Z", re.MULTILINE | re.DOTALL)
    line = re.compile(rf"^{escaped}.*$", re.MULTILINE)
    return scissors, line


def _strip_editor_cruft(message: str, comment_char: str | None = "#") -> str:
    """A raw commit-msg hook file still carries the comment-char-prefixed status
    lines and, under `commit -v`, the scissors-delimited diff below them — git
    strips both only after the hook runs, so a diff line must not read as the message."""
    if comment_char is None:
        return message
    scissors_re, comment_line_re = _comment_patterns(comment_char)
    message = scissors_re.sub("", message)
    return comment_line_re.sub("", message)


def _configured_comment_char(cwd: Path | None = None) -> str:
    try:
        value = git("config", "--get", "core.commentChar", cwd=cwd).strip()
    except (GateError, OSError):
        return "#"
    return value or "#"


def _resolve_comment_char(message: str, cwd: Path | None = None) -> str | None:
    """`auto` is resolved by git only when it writes the status/help block; with
    no block (`commit.status=false`, `-m`), git's cleanup strips nothing, so an
    unmatched hint means "do not strip" rather than the default `#`."""
    configured = _configured_comment_char(cwd)
    if configured != "auto":
        return configured
    match = _AUTO_COMMENT_HINT_RE.search(message)
    return match.group(1) if match else None


def check_message(message: str, words: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(message.splitlines(), start=1):
        stripped = line.strip()
        if _SIGNED_OFF_RE.match(stripped):
            findings.append(Finding(i, line, "Signed-off-by trailer is not allowed"))
        if _GENERATED_WITH_RE.search(stripped):
            findings.append(Finding(i, line, '"Generated with" line is not allowed'))
        co = _CO_AUTHORED_BY_RE.match(stripped)
        if co:
            marker = _ai_marker(co.group(1))
            if marker:
                findings.append(Finding(i, line, f'Co-Authored-By names an AI ("{marker}")'))
        for word in words:
            if _word_pattern(word).search(line):
                findings.append(Finding(i, line, f'banned word "{word}" (voice.md: Never use)'))
    return findings


def _range_messages(rev_range: str) -> list[tuple[str, str]]:
    out = git("log", "-z", rev_range, "--pretty=format:%H%x1f%B")
    result = []
    for record in out.split("\x00"):
        if not record:
            continue
        sha, _, msg = record.partition("\x1f")
        result.append((sha, msg))
    return result


def _emit(line: str) -> None:
    print(line, file=sys.stderr)


def _report(findings: list[Finding]) -> None:
    for f in findings:
        _emit(f"  line {f.line_no}: {f.reason}")
        _emit(f"    {f.line}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mutation-gate commit-msg")
    parser.add_argument("msgfile", nargs="?")
    parser.add_argument("--range", dest="rev_range")
    args = parser.parse_args(argv)

    try:
        words = banned_words(_voice_text())
    except GateError as exc:
        _emit(f"mutation-gate commit-msg refused: {exc}")
        return 2

    if args.rev_range:
        try:
            records = _range_messages(args.rev_range)
        except GateError as exc:
            _emit(f"mutation-gate commit-msg refused: {exc}")
            return 2
        blocked = False
        for sha, msg in records:
            findings = check_message(msg, words)
            if findings:
                blocked = True
                _emit(f"commit-msg: {sha[:12]}")
                _report(findings)
        return 1 if blocked else 0

    if not args.msgfile:
        _emit("mutation-gate commit-msg refused: msgfile or --range required")
        return 2
    try:
        message = Path(args.msgfile).read_text()
    except OSError as exc:
        _emit(f"mutation-gate commit-msg refused: {exc}")
        return 2

    comment_char = _resolve_comment_char(message)
    findings = check_message(_strip_editor_cruft(message, comment_char), words)
    if findings:
        _emit(f"commit-msg: {args.msgfile}")
        _report(findings)
        return 1
    return 0
