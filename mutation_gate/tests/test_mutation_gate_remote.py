"""Intent: #458 — with MUTATION_GATE_REMOTE set, every test run goes over ssh to
a synced copy of the working tree, so a suite that needs another machine's
hardware can be gated. A transport failure blocks; it is never a kill."""

import hashlib
import json
import os
import socket
import shutil
import stat

import pytest

from mutation_gate import repo as repo_mod, runner
from mutation_gate.mutants import Mutant

MUTANT = Mutant(file="src/x.py", line=1, start=0, end=1, old="a", new="b", kind="op")

SSH_SHIM = """#!/usr/bin/env python3
import json, os, subprocess, sys
open(os.environ["FAKE_REMOTE_HOME"] + ".ssh-argv", "a").write(json.dumps(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_SSH_EXIT"):
    sys.exit(int(os.environ["FAKE_SSH_EXIT"]))
env = dict(os.environ, HOME=os.environ["FAKE_REMOTE_HOME"])
sys.exit(subprocess.run(["sh", "-c", sys.argv[2]], env=env).returncode)
"""

RSYNC_SHIM = """#!/usr/bin/env python3
import json, os, shutil, sys
open(os.environ["FAKE_REMOTE_HOME"] + ".rsync-argv", "a").write(json.dumps(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_RSYNC_EXIT"):
    sys.exit(int(os.environ["FAKE_RSYNC_EXIT"]))
dest = os.path.join(os.environ["FAKE_REMOTE_HOME"], sys.argv[-1].split(":", 1)[1])
os.execv(os.environ["FAKE_REAL_RSYNC"], [os.environ["FAKE_REAL_RSYNC"], *sys.argv[1:-1], dest])
"""

REMOTE = "remote-box"

REAL_RSYNC = shutil.which("rsync")

pytestmark = pytest.mark.skipif(REAL_RSYNC is None, reason="the sync tests drive real rsync")

RECORD_COMMAND = (
    "sh -c 'cp src/x.py \"$HOME/seen\"; pwd > \"$HOME/where\"; echo {tests} > /dev/null'"
)


def _install(directory, name, body):
    path = directory / name
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def remote(tmp_path, monkeypatch):
    shims = tmp_path / "shims"
    shims.mkdir()
    _install(shims, "ssh", SSH_SHIM)
    _install(shims, "rsync", RSYNC_SHIM)
    remote_home = tmp_path / "remote-home"
    remote_home.mkdir()
    (tmp_path / "local-home").mkdir()
    work = tmp_path / "work"
    (work / "src").mkdir(parents=True)
    (work / "src" / "x.py").write_text("a")
    os.system(f"git -C {work} init -q")
    monkeypatch.setenv("PATH", f"{shims}:{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "local-home"))
    monkeypatch.setenv("FAKE_REMOTE_HOME", str(remote_home))
    monkeypatch.setenv("FAKE_REAL_RSYNC", REAL_RSYNC or "")
    monkeypatch.setenv("MUTATION_GATE_REMOTE", REMOTE)
    monkeypatch.setattr(runner, "CACHE_ROOT", tmp_path / "cache")
    repo = repo_mod.Repo(root=work, origin="", remotes=(), config=repo_mod.Config())
    repo.shims, repo.remote_home = shims, remote_home
    return repo


def test_a_quoted_test_command_runs_in_the_synced_directory_with_the_mutant_present(remote):
    runner.classify(remote, MUTANT, ["t.py"], RECORD_COMMAND, 30.0)
    assert (remote.remote_home / "seen").read_text() == "b"
    assert (remote.remote_home / "where").read_text().startswith(
        f"{remote.remote_home}/.cache/mutation-gate/"
    )


def test_the_remote_verdict_matches_the_local_one(remote, monkeypatch):
    command = "sh -c 'grep -q a src/x.py; echo {tests} > /dev/null; grep -q a src/x.py'"
    over_ssh = runner.classify(remote, MUTANT, ["t.py"], command, 30.0).verdict
    monkeypatch.delenv("MUTATION_GATE_REMOTE")
    assert over_ssh == runner.classify(remote, MUTANT, ["t.py"], command, 30.0).verdict
    assert over_ssh == runner.KILLED


def test_the_baseline_runs_on_the_remote_copy_too(remote):
    runner.baseline_green(remote, ["t.py"], RECORD_COMMAND)
    assert (remote.remote_home / "seen").read_text() == "a"


def test_the_restore_pass_syncs_the_unmutated_tree(remote):
    runner.classify(remote, MUTANT, ["t.py"], RECORD_COMMAND, 30.0)
    runner.rerun_unmutated(remote, ["t.py"], RECORD_COMMAND)
    assert (remote.remote_home / "seen").read_text() == "a"


def test_a_mutant_run_whose_ssh_exits_255_blocks_instead_of_counting_as_killed(
    remote, monkeypatch
):
    monkeypatch.setenv("FAKE_SSH_EXIT", "255")
    with pytest.raises(repo_mod.GateError, match="exit 255"):
        runner.classify(remote, MUTANT, ["t.py"], RECORD_COMMAND, 30.0)


def test_a_baseline_whose_ssh_exits_255_blocks(remote, monkeypatch):
    monkeypatch.setenv("FAKE_SSH_EXIT", "255")
    with pytest.raises(repo_mod.GateError, match="exit 255"):
        runner.baseline_green(remote, ["t.py"], RECORD_COMMAND)


def test_a_failed_rsync_blocks(remote, monkeypatch):
    monkeypatch.setenv("FAKE_RSYNC_EXIT", "23")
    with pytest.raises(repo_mod.GateError, match="rsync"):
        runner.classify(remote, MUTANT, ["t.py"], RECORD_COMMAND, 30.0)


def test_a_missing_rsync_blocks(remote, monkeypatch):
    (remote.shims / "rsync").unlink()
    only_git = remote.shims.parent / "only-git"
    only_git.mkdir()
    (only_git / "git").symlink_to(shutil.which("git"))
    monkeypatch.setenv("PATH", str(only_git))
    with pytest.raises(repo_mod.GateError, match="rsync"):
        runner.classify(remote, MUTANT, ["t.py"], RECORD_COMMAND, 30.0)


def test_a_mutant_is_restored_locally_after_a_transport_failure(remote, monkeypatch):
    monkeypatch.setenv("FAKE_SSH_EXIT", "255")
    with pytest.raises(repo_mod.GateError):
        runner.classify(remote, MUTANT, ["t.py"], RECORD_COMMAND, 30.0)
    assert (remote.root / "src" / "x.py").read_text() == "a"


def _argv_calls(remote, tool):
    log = remote.remote_home.parent / f"remote-home.{tool}-argv"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_rsync_is_given_archive_and_delete_and_the_hashed_directory(remote):
    runner.classify(remote, MUTANT, ["t.py"], RECORD_COMMAND, 30.0)
    digest = hashlib.sha256(f"{socket.gethostname()}:{remote.root}".encode()).hexdigest()[:16]
    (call,) = _argv_calls(remote, "rsync")
    assert {"-a", "--delete"} <= set(call)
    assert call[-1] == f"{REMOTE}:.cache/mutation-gate/{digest}/"


def test_ssh_is_given_the_remote_as_its_target(remote):
    runner.classify(remote, MUTANT, ["t.py"], RECORD_COMMAND, 30.0)
    (call,) = _argv_calls(remote, "ssh")
    assert call[0] == REMOTE


def test_tracked_files_are_synced_and_ignored_files_are_not(remote):
    (remote.root / ".gitignore").write_text("junk\n")
    (remote.root / "junk").write_text("x")
    (remote.root / "tracked").write_text("x")
    os.system(f"git -C {remote.root} add tracked")
    (remote.root / "tracked").write_text("changed")
    command = "sh -c 'cp tracked \"$HOME/tracked\"; ls > \"$HOME/listing\"; echo {tests} > /dev/null'"
    runner.classify(remote, MUTANT, ["t.py"], command, 30.0)
    assert (remote.remote_home / "tracked").read_text() == "changed"
    assert "junk" not in (remote.remote_home / "listing").read_text().split()


def test_a_remote_run_that_passes_survives(remote):
    assert runner.classify(remote, MUTANT, ["t.py"], "sh -c 'echo {tests}'", 30.0).verdict == (
        runner.SURVIVED
    )


def test_a_remote_run_without_the_pass_marker_is_killed(remote):
    remote.config = repo_mod.Config(pass_pattern="PASS-MARKER")
    assert runner.classify(remote, MUTANT, ["t.py"], "sh -c 'echo {tests}'", 30.0).verdict == (
        runner.KILLED
    )


def test_a_remote_run_with_the_pass_marker_survives(remote):
    remote.config = repo_mod.Config(pass_pattern="PASS-MARKER")
    command = "sh -c 'echo PASS-MARKER {tests}'"
    assert runner.classify(remote, MUTANT, ["t.py"], command, 30.0).verdict == runner.SURVIVED


def test_without_the_variable_neither_ssh_nor_rsync_runs(remote, monkeypatch):
    monkeypatch.delenv("MUTATION_GATE_REMOTE")
    runner.classify(remote, MUTANT, ["t.py"], "sh -c 'echo {tests}'", 30.0)
    assert _argv_calls(remote, "ssh") == _argv_calls(remote, "rsync") == []


def test_a_failed_rsync_stops_ssh_from_running(remote, monkeypatch):
    monkeypatch.setenv("FAKE_RSYNC_EXIT", "23")
    with pytest.raises(repo_mod.GateError):
        runner.classify(remote, MUTANT, ["t.py"], RECORD_COMMAND, 30.0)
    assert _argv_calls(remote, "ssh") == []


def _sync_listing(remote, monkeypatch=None):
    command = "sh -c 'find . -type f | sort > \"$HOME/listing\"; echo {tests} > /dev/null'"
    runner.classify(remote, MUTANT, ["t.py"], command, 30.0)
    return (remote.remote_home / "listing").read_text().split()


def test_a_file_in_the_remote_copy_but_not_in_the_local_list_is_gone_after_a_sync(remote):
    (remote.root / "sub").mkdir()
    (remote.root / "sub" / "b.py").write_text("b")
    (remote.root / "stale.py").write_text("s")
    (remote.root / "sub" / "stale2.py").write_text("s")
    _sync_listing(remote)
    (remote.root / "stale.py").unlink()
    (remote.root / "sub" / "stale2.py").unlink()
    assert _sync_listing(remote) == ["./src/x.py", "./sub/b.py"]


def test_a_filename_containing_glob_metacharacters_is_synced_only_as_itself(remote):
    (remote.root / "[a].py").write_text("x")
    (remote.root / "a.py").write_text("x")
    (remote.root / "star*.py").write_text("x")
    (remote.root / "starry.py").write_text("x")
    os.system(f"git -C {remote.root} add -f 'star*.py' starry.py a.py '[a].py'")
    os.system(f"git -C {remote.root} rm -q --cached starry.py a.py")
    (remote.root / "starry.py").unlink()
    (remote.root / "a.py").unlink()
    assert _sync_listing(remote) == ["./[a].py", "./src/x.py", "./star*.py"]


def test_a_tracked_file_deleted_from_the_tree_does_not_fail_the_sync(remote):
    (remote.root / "gone.py").write_text("x")
    os.system(f"git -C {remote.root} add gone.py")
    (remote.root / "gone.py").unlink()
    assert _sync_listing(remote) == ["./src/x.py"]


DOCKER_SHIM = """#!/bin/sh
case "$1" in
run) exec sleep 30 ;;
rm) echo "$@" >> "$HOME/docker-calls" ;;
esac
"""

HANGING_DOCKER_COMMAND = "docker run --rm img {tests}"


def _docker_calls(home):
    log = home / "docker-calls"
    return log.read_text().splitlines() if log.exists() else []


def test_a_hung_remote_container_is_removed_through_ssh_and_never_locally(remote, tmp_path):
    _install(remote.shims, "docker", DOCKER_SHIM)
    verdict = runner.classify(remote, MUTANT, ["t.py"], HANGING_DOCKER_COMMAND, 1.0).verdict
    *_, removal = _argv_calls(remote, "ssh")
    assert verdict == runner.KILLED_TIMEOUT
    assert removal[0] == REMOTE
    assert removal[1].startswith("docker rm -f mutation-gate-")
    assert _docker_calls(remote.remote_home) == [removal[1].removeprefix("docker ")]
    assert _docker_calls(tmp_path / "local-home") == []


def test_the_remote_command_runs_under_timeout_with_the_kill_grace_inside_the_cd(remote):
    runner.classify(remote, MUTANT, ["t.py"], RECORD_COMMAND, 30.0)
    (call,) = _argv_calls(remote, "ssh")
    assert f" && timeout --kill-after=15 30 sh -c " in call[1]


def test_a_remote_run_without_a_timeout_has_no_timeout_wrapper(remote):
    runner.run_capped(remote, "sh -c 'true'")
    (call,) = _argv_calls(remote, "ssh")
    assert "timeout" not in call[1]
