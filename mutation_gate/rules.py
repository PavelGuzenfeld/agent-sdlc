"""`mutation-gate rules sync|check`: the packaged rules/*.md copied into a repo's
.claude/rules/ and held there byte-exact (#71 decisions 3 and 5)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .repo import GateError, Repo, discover

TARGET = Path(".claude") / "rules"
SCOPED_RULE = "model-vv.md"

AGENTS_PATH = Path("AGENTS.md")
AGENTS_BEGIN = "<!-- BEGIN mutation-gate rules -->"
AGENTS_END = "<!-- END mutation-gate rules -->"

_INSTALLED = Path(__file__).resolve().parent / "bundled_rules"
RULES_DIR = _INSTALLED if _INSTALLED.is_dir() else Path(__file__).resolve().parent.parent / "rules"


def _emit(line: str) -> None:
    print(line, file=sys.stderr)


def _glob(prefix: str) -> str:
    return prefix + "**" if prefix.endswith("/") else prefix


def frontmatter(model_paths: list[str]) -> bytes:
    lines = "".join(f'  - "{_glob(p)}"\n' for p in model_paths)
    return f"---\npaths:\n{lines}---\n".encode()


def expected(repo: Repo) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for path in sorted(RULES_DIR.glob("*.md")):
        if path.name == SCOPED_RULE:
            if not repo.config.model_paths:
                continue
            out[path.name] = frontmatter(repo.config.model_paths) + path.read_bytes()
        else:
            out[path.name] = path.read_bytes()
    return out


def _agents_block(repo: Repo) -> bytes:
    sections = [
        f"## {name.removesuffix('.md')}\n\n".encode() + content
        for name, content in expected(repo).items()
    ]
    body = b"\n".join(sections)
    return f"{AGENTS_BEGIN}\n".encode() + body + f"\n{AGENTS_END}".encode()


def _locate_agents_block(text: bytes) -> tuple[int, int] | None:
    """Returns (start, end) spanning BEGIN..END with no trailing newline, or
    None when neither marker is present. Raises on any other shape."""
    begin, end = AGENTS_BEGIN.encode(), AGENTS_END.encode()
    begin_count, end_count = text.count(begin), text.count(end)
    if begin_count == 0 and end_count == 0:
        return None
    if begin_count != 1 or end_count != 1:
        raise GateError(
            f"{AGENTS_PATH}: expected exactly one BEGIN/END marker pair, "
            f"found {begin_count} begin, {end_count} end"
        )
    start, stop = text.index(begin), text.index(end)
    if stop < start:
        raise GateError(f"{AGENTS_PATH}: END marker precedes BEGIN marker")
    return start, stop + len(end)


def agents_sync(repo: Repo) -> None:
    path = repo.root / AGENTS_PATH
    block = _agents_block(repo)
    existing = path.read_bytes() if path.exists() else b""
    located = _locate_agents_block(existing)
    if located is None:
        sep = b"" if not existing else (b"\n" if existing.endswith(b"\n") else b"\n\n")
        new = existing + sep + block
    else:
        start, stop = located
        new = existing[:start] + block + existing[stop:]
    if not new.endswith(b"\n"):
        new += b"\n"
    path.write_bytes(new)


def agents_check(repo: Repo) -> list[str]:
    path = repo.root / AGENTS_PATH
    if not path.exists():
        return [f"{AGENTS_PATH}: missing"]
    existing = path.read_bytes()
    located = _locate_agents_block(existing)
    if located is None:
        return [f"{AGENTS_PATH}: missing the mutation-gate rules block"]
    start, stop = located
    if existing[start:stop] != _agents_block(repo):
        return [f"{AGENTS_PATH}: rules block differs from the packaged rules"]
    return []


def sync(repo: Repo) -> None:
    target = repo.root / TARGET
    target.mkdir(parents=True, exist_ok=True)
    wanted = expected(repo)
    for name, content in wanted.items():
        (target / name).write_bytes(content)
    if SCOPED_RULE not in wanted:
        (target / SCOPED_RULE).unlink(missing_ok=True)
    agents_sync(repo)


def check(repo: Repo) -> list[str]:
    target = repo.root / TARGET
    wanted = expected(repo)
    drift = []
    for name, content in wanted.items():
        path = target / name
        if not path.exists():
            drift.append(f"{TARGET / name}: missing")
        elif path.read_bytes() != content:
            drift.append(f"{TARGET / name}: differs from the packaged rule")
    if SCOPED_RULE not in wanted and (target / SCOPED_RULE).exists():
        drift.append(f"{TARGET / SCOPED_RULE}: present but model_paths is empty")
    drift.extend(agents_check(repo))
    return drift


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mutation-gate rules")
    parser.add_argument("action", choices=["sync", "check"])
    args = parser.parse_args(argv)
    try:
        repo = discover()
        if args.action == "sync":
            sync(repo)
            return 0
        drift = check(repo)
    except GateError as exc:
        _emit(f"mutation-gate rules refused: {exc}")
        return 2
    for line in drift:
        _emit(f"rules check: {line}")
    if drift:
        _emit("run `mutation-gate rules sync` and commit the result")
        return 1
    return 0
