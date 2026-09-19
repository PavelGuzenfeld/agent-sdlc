"""Apply, test, classify, restore (decision 18).

Mutation is in place with a byte-level backup, never `git checkout` — the gate
always runs against a dirty tree, which is exactly what mutate.sh refuses.
A leftover backup means a previous run died; it is restored and the run refuses.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import signal
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .mutants import Mutant
from .repo import CACHE_ROOT, GateError, Repo

KILLED, SURVIVED, NO_TESTS = "KILLED", "SURVIVED", "NO-TESTS"
# Still killed — a mutant that hangs the suite is a mutant the suite noticed, and
# a gate that blocks on it is worse than a wrong verdict. Named apart because a
# merely slow build times out identically, and that is a kill nobody earned (#78).
KILLED_TIMEOUT = "KILLED-TIMEOUT"

PASSED, FAILED, TIMED_OUT = "passed", "failed", "timed out"
# Exit 0 with no pass marker: a runner that never loaded the code still exits 0,
# and the gate would read that as every mutant surviving.
NO_PASS_MARKER = "exited 0 without reporting a pass"

# Seconds a SIGTERMed test command gets to stop its container before SIGKILL.
TERM_GRACE_SECONDS = 15.0

DOCKER_RUN_RE = re.compile(r"\bdocker\s+run\b")

# Root in the container writes these into the bind-mounted repo as directories a
# host user then cannot rm without starting another container (#74).
NO_ROOT_CACHE = "-e PYTHONDONTWRITEBYTECODE=1 -e PYTEST_ADDOPTS='-p no:cacheprovider'"

GIT_REPO_SCOPED = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE")


def _test_env() -> dict[str, str]:
    """The environment a repo's own command runs in. Git exports these into every
    hook and they override `-C`, so a suite that builds a temp repo stages into
    the commit being gated instead (flowdiff#83)."""
    return {k: v for k, v in os.environ.items() if k not in GIT_REPO_SCOPED}


@dataclass
class Result:
    mutant: Mutant
    verdict: str
    tests: list[str]


def _backup_dir(repo: Repo) -> Path:
    return CACHE_ROOT / repo.key / "backup"


def recover(repo: Repo) -> list[str]:
    """Restore anything a killed run left mutated. Returns what was restored."""
    bdir = _backup_dir(repo)
    if not bdir.exists():
        return []
    restored = []
    for saved in sorted(bdir.rglob("*")):
        if not saved.is_file():
            continue
        rel = saved.relative_to(bdir)
        target = repo.root / rel
        shutil.copyfile(saved, target)
        saved.unlink()
        restored.append(str(rel))
    return restored


@contextmanager
def mutated(repo: Repo, mutant: Mutant):
    target = repo.root / mutant.file
    backup = _backup_dir(repo) / mutant.file
    backup.parent.mkdir(parents=True, exist_ok=True)
    original = target.read_bytes()
    backup.write_bytes(original)

    def restore(*_):
        target.write_bytes(original)
        backup.unlink(missing_ok=True)

    previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous:
        signal.signal(sig, lambda *_: (restore(), exit(130)))
    try:
        target.write_bytes(
            original[: mutant.start] + mutant.new.encode() + original[mutant.end :]
        )
        yield
    finally:
        restore()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _prepare_docker_run(cmd: str) -> tuple[str, str | None]:
    """A `docker run` gets NO_ROOT_CACHE, and a unique --name when the command
    names none. The returned name is what `_terminate` may `docker rm -f`, so it
    is None whenever the pack did not choose it.

    A hung container cannot be signalled away. `docker run` proxies SIGTERM to
    PID 1, but a PID 1 with no installed handler — pytest, sleep — ignores it by
    kernel rule, and SIGKILL reaches only the local client. `docker rm -f` is the
    only thing that reliably stops it. Measured: the container outlived a
    process-group SIGTERM by 20s+ and died instantly to `docker rm -f`.
    """
    if not DOCKER_RUN_RE.search(cmd):
        return cmd, None
    if "--name" in cmd:
        return DOCKER_RUN_RE.sub(f"docker run {NO_ROOT_CACHE}", cmd, count=1), None
    name = f"mutation-gate-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    return DOCKER_RUN_RE.sub(f"docker run --name {name} {NO_ROOT_CACHE}", cmd, count=1), name


def _terminate(proc: subprocess.Popen, container: str | None) -> None:
    """Remove the container first, then reap the process group it was attached to."""
    if container:
        subprocess.run(
            ["docker", "rm", "-f", container],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pgid, signal.SIGTERM)
    try:
        proc.wait(timeout=TERM_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=TERM_GRACE_SECONDS)


def run_capped(repo: Repo, command: str, timeout: float | None = None) -> str:
    """One of the verdicts above, within `timeout`, with any container the
    command started removed if it overruns. Every subprocess the gate starts
    goes through here, or a hang wedges the run and leaks what it was holding."""
    cmd, container = _prepare_docker_run(command)
    pattern = repo.config.pass_pattern
    capture = subprocess.PIPE if pattern else subprocess.DEVNULL
    proc = subprocess.Popen(
        cmd, shell=True, cwd=repo.root,
        stdout=capture, stderr=subprocess.STDOUT if pattern else capture,
        start_new_session=True, env=_test_env(),
    )
    try:
        # communicate, not wait: a filled pipe deadlocks a process we also time out.
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate(proc, container)
        return TIMED_OUT
    if proc.returncode != 0:
        return FAILED
    if pattern and not re.search(pattern, (out or b"").decode(errors="ignore")):
        return NO_PASS_MARKER
    return PASSED


def _run_tests(
    repo: Repo, tests: list[str], test_command: str, timeout: float | None = None
) -> str:
    """Verdict within `timeout`. Timing out is not-green: a mutant can make the
    suite hang — `break` to `continue`, or a divide that never settles — and a
    hung gate is worse than a wrong verdict."""
    return run_capped(repo, test_command.format(tests=" ".join(tests)), timeout)


def baseline_green(repo: Repo, tests: list[str], test_command: str) -> float:
    """Seconds the unmutated suite takes. Refuses rather than reporting, because
    a baseline that is not green makes every later verdict a fabrication."""
    start = time.monotonic()
    verdict = _run_tests(repo, tests, test_command, repo.config.baseline_timeout)
    if verdict == NO_PASS_MARKER:
        raise GateError(
            f"baseline exited 0 but printed no pass_pattern "
            f"({repo.config.pass_pattern!r}). The suite did not report a pass, so "
            "every mutant would report SURVIVED. Check the test command, not the "
            "tests — a runner that cannot load the code still exits 0."
        )
    if verdict != PASSED:
        raise GateError(
            f"baseline suite {verdict} unmutated; every mutant would report "
            "KILLED for the wrong reason"
        )
    return time.monotonic() - start


def classify(
    repo: Repo,
    mutant: Mutant,
    tests: list[str],
    test_command: str,
    timeout: float | None = None,
) -> Result:
    if not tests:
        return Result(mutant, NO_TESTS, [])
    with mutated(repo, mutant):
        verdict = _run_tests(repo, tests, test_command, timeout)
    if verdict == PASSED:
        return Result(mutant, SURVIVED, tests)
    return Result(mutant, KILLED_TIMEOUT if verdict == TIMED_OUT else KILLED, tests)


@contextmanager
def repo_lock(repo: Repo):
    """One gate per repo. A second instance would see the first's backup, restore
    it mid-mutant, and hand both runs a false SURVIVED."""
    path = CACHE_ROOT / repo.key / "lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = _claim(path, repo)
    try:
        os.write(fd, str(os.getpid()).encode())
    finally:
        os.close(fd)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def _claim(path: Path, repo: Repo) -> int:
    """The lock, or GateError. Creation is O_EXCL and never exists()-then-write:
    two gates starting inside the gap between the check and the write both pass
    the check, and each then restores the other's backup mid-mutant (#79)."""
    for cleaned_stale in (False, True):
        try:
            return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            holder = _holder(path)
            if holder or cleaned_stale:
                raise GateError(
                    f"another mutation-gate (pid {holder or 'unknown'}) is running in "
                    f"{repo.root.name}; concurrent runs corrupt each other"
                ) from None
            path.unlink(missing_ok=True)
    raise AssertionError("unreachable")


def _holder(path: Path) -> str:
    """The live pid holding `path`, or "" if the holder died without releasing."""
    try:
        pid = path.read_text().strip()
    except OSError:
        return ""
    return pid if pid.isdigit() and Path(f"/proc/{pid}").exists() else ""


def guard_clean_start(repo: Repo) -> None:
    restored = recover(repo)
    if restored:
        raise GateError(
            "a previous run left mutated files; restored "
            + ", ".join(restored)
            + " — verify the tree and re-run"
        )
