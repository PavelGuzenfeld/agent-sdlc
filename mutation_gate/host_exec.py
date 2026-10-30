"""PreToolUse Bash hook: host test and build commands run in the repo's `test_image`,
and a `docker run` that bind-mounts the repo must pass `--user` (#395)."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .repo import CONFIG_NAME, Config

CONTAINER_MARKER = Path("/.dockerenv")
HOST_COMMANDS = frozenset({"python3", "pytest", "make", "cmake", "colcon"})
USER_FLAG = "--user $(id -u):$(id -g)"
SEPARATORS = ";&|"
PWD_PREFIX = re.compile(r"^(\$\{PWD\}|\$PWD|\$\(pwd\)|`pwd`)")
USER_FLAGS = frozenset({"-u", "--user"})
VOLUME_FLAGS = frozenset({"-v", "--volume"})
VALUE_FLAGS = USER_FLAGS | VOLUME_FLAGS | frozenset({
    "--mount", "-e", "--env", "--env-file", "-w", "--workdir", "-p", "--publish", "--name",
    "--entrypoint", "--network", "--net", "-l", "--label", "--platform", "--gpus",
    "--shm-size", "--ipc", "--pid", "-m", "--memory", "--cpus", "--device", "--add-host",
    "--cap-add", "--cap-drop", "--security-opt", "--ulimit", "--tmpfs", "--runtime",
    "-h", "--hostname", "--restart", "--log-driver", "--log-opt", "--cidfile",
    "--group-add", "--expose", "--stop-signal", "--pull", "--userns",
})


@dataclass(frozen=True)
class Denial:
    reason: str


@dataclass(frozen=True)
class Rewrite:
    command: str


@dataclass
class DockerRun:
    sources: list[str] = field(default_factory=list)
    has_user: bool = False


def segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=SEPARATORS)
    lexer.whitespace_split = True
    lexer.commenters = ""
    parts: list[list[str]] = [[]]
    for token in lexer:
        if not token.strip(SEPARATORS):
            parts.append([])
        else:
            parts[-1].append(token)
    return [part for part in parts if part]


def parse_docker_run(args: list[str]) -> DockerRun:
    run = DockerRun()
    tokens = iter(args)
    for token in tokens:
        if not token.startswith("-"):
            break
        flag, has_value, value = token.partition("=")
        if not has_value and flag in VALUE_FLAGS:
            value = next(tokens, "")
        if flag in USER_FLAGS:
            run.has_user = True
        elif flag in VOLUME_FLAGS and ":" in value:
            run.sources.append(value.partition(":")[0])
        elif flag == "--mount":
            options = dict(part.partition("=")[::2] for part in value.split(","))
            if options.get("type") == "bind":
                run.sources.append(options.get("source") or options.get("src", ""))
    return run


def host_path(source: str, cwd: Path) -> Path | None:
    source = os.path.expanduser(os.path.expandvars(PWD_PREFIX.sub(lambda _: str(cwd), source)))
    if "$" in source or not source.startswith(("/", ".")):
        return None
    return (cwd / source).resolve()


def git_lines(cwd: Path, *args: str) -> list[str] | None:
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    return result.stdout.splitlines() if result.returncode == 0 else None


def is_inside(path: Path | None, roots: list[Path]) -> bool:
    return path is not None and any(path == root or root in path.parents for root in roots)


def with_user(command: str) -> str:
    return re.sub(r"\bdocker\s+run\b", lambda _: f"docker run {USER_FLAG}", command)


def is_host_command(tokens: list[str]) -> bool:
    return tokens[0] in HOST_COMMANDS or tokens[:2] == ["pip", "install"]


def decide(command: str, cwd: Path, is_in_container: bool) -> Denial | Rewrite | None:
    toplevel = git_lines(cwd, "rev-parse", "--show-toplevel")
    if toplevel is None:
        return None
    try:
        parts = segments(command)
    except ValueError:
        return None
    roots = [Path(line.removeprefix("worktree ")).resolve()
             for line in git_lines(cwd, "worktree", "list", "--porcelain") or []
             if line.startswith("worktree ")]
    for part in parts:
        for start in range(len(part)):
            if part[start:start + 2] == ["docker", "run"]:
                run = parse_docker_run(part[start + 2:])
                inside = [s for s in run.sources if is_inside(host_path(s, cwd), roots)]
                if inside and not run.has_user:
                    return Denial(
                        f"docker run bind-mounts {inside[0]} inside the repo without --user, "
                        f"which leaves root-owned files. Run instead:\n  {with_user(command)}"
                    )
    if is_in_container or not parts or not is_host_command(parts[0]):
        return None
    config = Config.load(Path(toplevel[0]))
    if not config.is_test_image_used:
        return None
    if not config.test_image:
        return Denial(
            f"`{parts[0][0]}` would run on the host. Set test_image = \"<image>\" in "
            f"{CONFIG_NAME} to run it in that image, or is_test_image_used = false to keep it on the host."
        )
    return Rewrite(
        f'docker run --rm {USER_FLAG} -v "$PWD:/w" -w /w '
        f"{shlex.quote(config.test_image)} sh -c {shlex.quote(command)}"
    )


def main() -> int:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    verdict = decide(tool_input.get("command") or "", cwd, CONTAINER_MARKER.exists())
    if isinstance(verdict, Denial):
        print(f"host-exec: {verdict.reason}", file=sys.stderr)
        return 2
    if isinstance(verdict, Rewrite):
        json.dump({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "host-exec: runs in test_image",
            "updatedInput": {**tool_input, "command": verdict.command},
        }}, sys.stdout)
    return 0
