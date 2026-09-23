"""`mutation-gate rules sync|check`: the packaged rules/*.md copied into a repo's
.claude/rules/ and held there byte-exact (#71 decisions 3 and 5)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .repo import GateError, Repo, discover

TARGET = Path(".claude") / "rules"
SCOPED_RULE = "model-vv.md"

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


def sync(repo: Repo) -> None:
    target = repo.root / TARGET
    target.mkdir(parents=True, exist_ok=True)
    wanted = expected(repo)
    for name, content in wanted.items():
        (target / name).write_bytes(content)
    if SCOPED_RULE not in wanted:
        (target / SCOPED_RULE).unlink(missing_ok=True)


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
    return drift


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mutation-gate rules")
    parser.add_argument("action", choices=["sync", "check"])
    args = parser.parse_args(argv)
    try:
        repo = discover()
    except GateError as exc:
        _emit(f"mutation-gate rules refused: {exc}")
        return 2
    if args.action == "sync":
        sync(repo)
        return 0
    drift = check(repo)
    for line in drift:
        _emit(f"rules check: {line}")
    if drift:
        _emit("run `mutation-gate rules sync` and commit the result")
        return 1
    return 0
