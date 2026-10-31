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

from .repo import CONFIG_NAME, Config, GateError

CONTAINER_MARKER = Path("/.dockerenv")
HOST_COMMANDS = frozenset({"python3", "pytest", "make", "cmake", "colcon"})
USER_FLAG = "--user $(id -u):$(id -g)"
SEPARATORS = ";&|"
LIST_SEPARATORS = ("&&", "||", ";", "\n")
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


@dataclass(frozen=True)
class Notice:
    reason: str


@dataclass(frozen=True)
class Mount:
    source: str
    target: str


@dataclass
class DockerRun:
    mounts: list[Mount] = field(default_factory=list)
    has_user: bool = False
    command: list[str] = field(default_factory=list)

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
            run.command = list(tokens)
            break
        flag, has_value, value = token.partition("=")
        if not has_value and flag in VALUE_FLAGS:
            value = next(tokens, "")
        if flag in USER_FLAGS:
            run.has_user = True
        elif flag in VOLUME_FLAGS and ":" in value:
            source, _, rest = value.partition(":")
            run.mounts.append(Mount(source, rest.partition(":")[0]))
        elif flag == "--mount":
            options = dict(part.partition("=")[::2] for part in value.split(","))
            if options.get("type") == "bind":
                run.mounts.append(Mount(
                    options.get("source") or options.get("src", ""),
                    options.get("target") or options.get("dst") or options.get("destination", ""),
                ))
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


def is_ownership_handback(command: list[str], targets: list[str]) -> bool:
    owners = ("$(id -u):$(id -g)", f"{os.getuid()}:{os.getgid()}")
    return " ".join(command) in {f"chown -R {owner} {target}" for owner in owners for target in targets}


def with_user(command: str) -> str:
    return re.sub(r"\bdocker\s+run\b", lambda _: f"docker run {USER_FLAG}", command)


def is_host_command(tokens: list[str]) -> bool:
    return tokens[0] in HOST_COMMANDS or tokens[:2] == ["pip", "install"]


def split_list(command: str) -> list[str]:
    pieces: list[str] = []
    start = depth = index = 0
    quote = ""
    while index < len(command):
        char = command[index]
        if quote:
            index += char == "\\" and quote == '"'
            quote = "" if char == quote else quote
        elif char == "\\":
            index += 1
        elif char in "'\"":
            quote = char
        elif char in "()":
            depth = max(depth + (1 if char == "(" else -1), 0)
        elif depth == 0:
            separator = next((s for s in LIST_SEPARATORS if command.startswith(s, index)), None)
            if separator:
                pieces += [command[start:index], separator]
                index += len(separator)
                start = index
                continue
        index += 1
    return pieces + [command[start:]]


def in_image(command: str, image: str) -> str:
    return (f'docker run --rm {USER_FLAG} -e HOME=/tmp -v "$PWD:/w" -w /w '
            f"{shlex.quote(image)} sh -c {shlex.quote(command)}")


def rewrite_host_elements(command: str, image: str) -> str:
    pieces = split_list(command)
    for index in range(0, len(pieces), 2):
        padded = pieces[index]
        element = padded.strip()
        parts = segments(element)
        if parts and parts[0][0] != "docker" and any(is_host_command(part) for part in parts):
            pieces[index] = padded.replace(element, in_image(element, image), 1)
    return "".join(pieces)


def host_command_piped_from_docker(command: str) -> str | None:
    for element in split_list(command)[::2]:
        parts = segments(element)
        if parts and parts[0][0] == "docker":
            host = next((part[0] for part in parts[1:] if is_host_command(part)), None)
            if host:
                return host
    return None


def decide(command: str, cwd: Path, is_in_container: bool) -> Denial | Rewrite | Notice | None:
    toplevel = git_lines(cwd, "rev-parse", "--show-toplevel")
    if toplevel is None or not (Path(toplevel[0]) / CONFIG_NAME).exists():
        return None
    try:
        config = Config.load(Path(toplevel[0]))
    except (GateError, ValueError):
        return Notice(f"cannot read {Path(toplevel[0]) / CONFIG_NAME}, passing through")
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
                inside = [m for m in run.mounts if is_inside(host_path(m.source, cwd), roots)]
                if (inside and not run.has_user
                        and not is_ownership_handback(run.command, [m.target for m in inside])):
                    return Denial(
                        f"docker run bind-mounts {inside[0].source} inside the repo without --user, "
                        f"which leaves root-owned files. Run instead:\n  {with_user(command)}"
                    )
    host = next((part[0] for part in parts if is_host_command(part)), None)
    if host is None or is_in_container or not config.is_test_image_used:
        return None
    if not config.test_image:
        return Denial(
            f"`{host}` would run on the host. Set test_image = \"<image>\" in "
            f"{CONFIG_NAME} to run it in that image, or is_test_image_used = false to keep it on the host."
        )
    piped = host_command_piped_from_docker(command)
    if piped:
        return Denial(
            f"`{piped}` is piped from a docker command and would run on the host. Split the "
            f"line so `{piped}` is its own command and runs in {config.test_image}."
        )
    if any(part[0] == "docker" for part in parts):
        return Rewrite(rewrite_host_elements(command, config.test_image))
    return Rewrite(in_image(command, config.test_image))


def main() -> int:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    verdict = decide(tool_input.get("command") or "", cwd, CONTAINER_MARKER.exists())
    if isinstance(verdict, (Denial, Notice)):
        print(f"host-exec: {verdict.reason}", file=sys.stderr)
    if isinstance(verdict, Denial):
        return 2
    if isinstance(verdict, Rewrite):
        json.dump({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "host-exec: runs in test_image",
            "updatedInput": {**tool_input, "command": verdict.command},
        }}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
