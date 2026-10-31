"""Intent: #395 (decisions 3, 6-9 of #393) — host test and build commands run in
the repo's `test_image`, or are denied naming that key; a `docker run` that
bind-mounts the repo or a worktree without `--user` is denied with the fix."""

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mutation_gate import host_exec
from mutation_gate.host_exec import Denial, Rewrite, decide
from mutation_gate.repo import Config

USER = "--user $(id -u):$(id -g)"


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _fake_git(monkeypatch, toplevel: Path, worktrees: list[Path]) -> None:
    def git_lines(cwd: Path, *args: str) -> list[str] | None:
        if cwd != toplevel and toplevel not in cwd.parents:
            return None
        if args == ("rev-parse", "--show-toplevel"):
            return [str(toplevel)]
        assert args == ("worktree", "list", "--porcelain")
        return [line for tree in worktrees
                for line in (f"worktree {tree}", "HEAD 0123", "branch refs/heads/x", "")]
    monkeypatch.setattr(host_exec, "git_lines", git_lines)


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".mutation-gate.toml").write_text('test_image = "img:1"\n')
    _fake_git(monkeypatch, root, [root])
    return root


def _rewritten(command: str, image: str = "img:1") -> Rewrite:
    return Rewrite(f'docker run --rm {USER} -e HOME=/tmp -v "$PWD:/w" -w /w {image} sh -c {command}')


def test_test_image_defaults_to_empty_and_the_rewrite_to_on():
    assert Config().test_image == ""
    assert Config().is_test_image_used is True


def test_config_accepts_both_keys(tmp_path):
    (tmp_path / ".mutation-gate.toml").write_text('test_image = "x"\nis_test_image_used = false\n')
    loaded = Config.load(tmp_path)
    assert (loaded.test_image, loaded.is_test_image_used) == ("x", False)


@pytest.mark.parametrize("command", [
    "python3 -m pytest", "pytest -q", "make test", "cmake -B build", "colcon build",
    "pip install -e .",
])
def test_each_host_command_is_rewritten_into_the_image(repo, command):
    assert decide(command, repo, False) == _rewritten(f"'{command}'")


def test_the_whole_pipeline_runs_inside_the_image(repo):
    assert decide("pytest -q | tail -1", repo, False) == _rewritten("'pytest -q | tail -1'")


def test_image_with_shell_characters_is_quoted(repo):
    (repo / ".mutation-gate.toml").write_text('test_image = "img; rm -rf x"\n')
    assert decide("pytest", repo, False) == _rewritten("pytest", "'img; rm -rf x'")


@pytest.mark.parametrize("command", [
    "pip list", "pip3 install x", "git status", "ls pytest", "docker build . && pytest",
    'docker run --rm -u 1:1 -v "$PWD:/w" img pytest',
])
def test_other_commands_pass_through(repo, command):
    assert decide(command, repo, False) is None


def test_inside_a_container_host_commands_pass_through(repo):
    assert decide("pytest -q", repo, True) is None


def test_outside_a_git_repo_everything_passes(repo, tmp_path):
    assert decide("pytest -q", tmp_path, False) is None
    assert decide('docker run -v "$PWD:/w" img', tmp_path, False) is None


def test_unparseable_command_passes(repo):
    assert decide("pytest 'unterminated", repo, False) is None


def test_no_image_denies_naming_the_key(repo):
    (repo / ".mutation-gate.toml").write_text("")
    verdict = decide("make", repo, False)
    assert isinstance(verdict, Denial)
    assert 'test_image = "<image>"' in verdict.reason
    assert ".mutation-gate.toml" in verdict.reason
    assert "`make`" in verdict.reason


def test_rewrite_switched_off_passes_even_without_image(repo):
    (repo / ".mutation-gate.toml").write_text("is_test_image_used = false\n")
    assert decide("pytest", repo, False) is None


def test_config_is_read_from_the_toplevel_not_the_subdirectory(repo):
    (repo / "sub").mkdir()
    assert decide("pytest", repo / "sub", False) == _rewritten("pytest")


def _denial(command: str, cwd: Path) -> Denial:
    verdict = decide(command, cwd, False)
    assert isinstance(verdict, Denial), verdict
    corrected = command.replace("docker run", f"docker run {USER}")
    assert verdict.reason.endswith(f"Run instead:\n  {corrected}")
    return verdict


def test_bind_mount_without_user_is_denied_with_the_corrected_command(repo):
    command = 'docker run --rm -v "$PWD:/w" -w /w img true && docker  run img'
    assert decide(command, repo, False) == Denial(
        "docker run bind-mounts $PWD inside the repo without --user, which leaves "
        f"root-owned files. Run instead:\n  docker run {USER} --rm -v \"$PWD:/w\" -w /w img "
        f"true && docker run {USER} img"
    )


@pytest.mark.parametrize("source", ["$PWD", "${PWD}", "$(pwd)", "`pwd`", ".", "./sub", "$PWD/sub"])
def test_every_spelling_of_the_working_directory_counts(repo, source):
    _denial(f"docker run -v {source}:/w img", repo)


def test_absolute_and_home_relative_paths_inside_the_repo_count(repo, monkeypatch):
    monkeypatch.setenv("HOME", str(repo.parent))
    _denial(f"docker run -v {repo}/sub:/w img", repo)
    _denial("docker run -v ~/repo:/w img", repo)


def test_path_into_another_worktree_counts(repo, tmp_path, monkeypatch):
    other = tmp_path / "other-worktree"
    _fake_git(monkeypatch, repo, [repo, other])
    _denial(f"docker run -v {other}/src:/w img", repo)


@needs_git
def test_real_git_finds_the_toplevel_and_every_worktree(tmp_path):
    root, other = tmp_path / "repo", tmp_path / "other-worktree"
    git = ["git", "-C", str(root), "-c", "user.email=t", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    subprocess.run([*git, "worktree", "add", "-q", str(other)], check=True)
    (root / "sub").mkdir()
    (root / ".mutation-gate.toml").write_text('test_image = "img:1"\n')
    assert decide("pytest", root / "sub", False) == _rewritten("pytest")
    _denial(f"docker run -v {other}:/w img", root)
    assert decide("pytest", tmp_path, False) is None


@pytest.mark.parametrize("source", ["..", "../repo2", "cache", "$UNSET_HOST_EXEC_VAR/x"])
def test_paths_outside_the_repo_and_named_volumes_pass(repo, source, monkeypatch):
    monkeypatch.delenv("UNSET_HOST_EXEC_VAR", raising=False)
    (repo.parent / "repo2").mkdir()
    assert decide(f"docker run -v {source}:/w img", repo, False) is None


def test_volume_without_a_host_side_passes(repo):
    assert decide(f"docker run -v {repo}/data img", repo, False) is None


@pytest.mark.parametrize("flags", [
    '--volume "$PWD:/w"', '--volume="$PWD:/w"', "--mount type=bind,source=.,target=/w",
    "--mount=type=bind,src=.,dst=/w",
])
def test_long_mount_forms_count(repo, flags):
    _denial(f"docker run {flags} img", repo)


def test_volume_type_mount_passes(repo):
    assert decide("docker run --mount type=volume,source=.,target=/w img", repo, False) is None


@pytest.mark.parametrize("user", ["-u 1:1", "--user 1:1", "--user=1:1", "-u=1:1", USER])
def test_any_user_flag_allows_the_mount(repo, user):
    assert decide(f'docker run --rm {user} -v "$PWD:/w" img', repo, False) is None


def test_flags_after_the_image_belong_to_the_command(repo):
    assert decide("docker run --rm img pytest -v .:/x", repo, False) is None


def test_docker_run_after_a_prefix_word_is_still_checked(repo):
    _denial("sudo docker run -v .:/w img", repo)


@pytest.mark.parametrize("flag", [
    "-e", "--env", "--env-file", "-w", "--workdir", "-p", "--publish", "--name",
    "--entrypoint", "--network", "--net", "-l", "--label", "--platform", "--gpus",
    "--shm-size", "--ipc", "--pid", "-m", "--memory", "--cpus", "--device", "--add-host",
    "--cap-add", "--cap-drop", "--security-opt", "--ulimit", "--tmpfs", "--runtime",
    "-h", "--hostname", "--restart", "--log-driver", "--log-opt", "--cidfile",
    "--group-add", "--expose", "--stop-signal", "--pull", "--userns",
])
def test_a_flag_value_is_not_mistaken_for_the_image(repo, flag):
    _denial(f"docker run {flag} value -v .:/w img", repo)


def test_a_flag_whose_value_starts_with_a_dash_still_ends_before_the_image(repo):
    _denial("docker run -v .:/w --entrypoint -x img", repo)


def test_separators_inside_quotes_do_not_split_the_command(repo):
    assert decide("pytest -k 'a;b'", repo, False) == _rewritten("'pytest -k '\"'\"'a;b'\"'\"''")


def test_a_hash_inside_a_word_is_not_a_comment(repo):
    _denial("docker run --name=a#b -v .:/w img", repo)


def _run_main(monkeypatch, payload: dict, marker: Path) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(host_exec, "CONTAINER_MARKER", marker)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", stderr)
    return host_exec.main(), stdout.getvalue(), stderr.getvalue()


def test_container_marker_is_the_docker_convention():
    assert host_exec.CONTAINER_MARKER == Path("/.dockerenv")


def test_hook_allows_the_rewrite_and_keeps_the_other_input_fields(repo, monkeypatch, tmp_path):
    payload = {"cwd": str(repo), "tool_input": {"command": "pytest", "timeout": 5}}
    code, out, err = _run_main(monkeypatch, payload, tmp_path / "absent")
    assert (code, err) == (0, "")
    assert json.loads(out) == {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": "host-exec: runs in test_image",
        "updatedInput": {"command": _rewritten("pytest").command, "timeout": 5},
    }}


def test_hook_passes_silently_inside_a_container(repo, monkeypatch, tmp_path):
    marker = tmp_path / "marker"
    marker.touch()
    payload = {"cwd": str(repo), "tool_input": {"command": "pytest"}}
    assert _run_main(monkeypatch, payload, marker) == (0, "", "")


def test_hook_denies_with_exit_2_and_the_reason_on_stderr(repo, monkeypatch, tmp_path):
    (repo / ".mutation-gate.toml").write_text("")
    payload = {"cwd": str(repo), "tool_input": {"command": "pytest"}}
    code, out, err = _run_main(monkeypatch, payload, tmp_path / "absent")
    assert (code, out) == (2, "")
    assert err.startswith("host-exec: `pytest` would run on the host.")
    assert 'test_image = "<image>"' in err


def test_hook_without_cwd_uses_the_process_directory(repo, monkeypatch, tmp_path):
    monkeypatch.chdir(repo)
    code, out, _ = _run_main(monkeypatch, {"tool_input": {"command": "pytest"}}, tmp_path / "absent")
    assert code == 0
    assert json.loads(out)["hookSpecificOutput"]["updatedInput"]["command"] == _rewritten("pytest").command


def test_hook_without_a_command_passes(repo, monkeypatch, tmp_path):
    assert _run_main(monkeypatch, {"cwd": str(repo)}, tmp_path / "absent") == (0, "", "")


def test_hook_denies_a_bind_mount_without_user_with_the_corrected_command(repo, monkeypatch, tmp_path):
    payload = {"cwd": str(repo), "tool_input": {"command": "docker run -v .:/w img true"}}
    code, out, err = _run_main(monkeypatch, payload, tmp_path / "absent")
    assert (code, out) == (2, "")
    assert err.endswith(f"Run instead:\n  docker run {USER} -v .:/w img true\n")


def test_switch_off_passes_through_even_with_an_image_set(repo):
    (repo / ".mutation-gate.toml").write_text('test_image = "img:1"\nis_test_image_used = false\n')
    assert decide("pytest", repo, False) is None


def test_switch_off_keeps_the_bind_mount_check(repo):
    (repo / ".mutation-gate.toml").write_text("is_test_image_used = false\n")
    _denial("docker run -v .:/w img", repo)


def test_repo_without_the_config_file_is_left_alone(repo):
    (repo / ".mutation-gate.toml").unlink()
    assert decide("pytest -q", repo, False) is None
    assert decide("docker run -v .:/w img", repo, False) is None


@pytest.mark.parametrize("toml", ['test_image = "unterminated\n', "no_such_key = 1\n"])
def test_unreadable_config_passes_with_one_line_naming_the_file(repo, monkeypatch, tmp_path, toml):
    (repo / ".mutation-gate.toml").write_text(toml)
    payload = {"cwd": str(repo), "tool_input": {"command": "docker run -v .:/w img"}}
    code, out, err = _run_main(monkeypatch, payload, tmp_path / "absent")
    assert (code, out) == (0, "")
    assert err == f"host-exec: cannot read {repo / '.mutation-gate.toml'}, passing through\n"


@pytest.mark.parametrize("command", ["cd sub && pytest -q", "git status; make", "true || colcon build",
                                     "ls | pip install -r /dev/stdin"])
def test_a_host_command_in_any_segment_moves_the_whole_line_into_the_image(repo, command):
    assert decide(command, repo, False) == _rewritten(f"'{command}'")


def test_no_image_denial_names_the_first_host_command_in_the_line(repo):
    (repo / ".mutation-gate.toml").write_text("")
    assert decide("cd sub && cmake -B b && make", repo, False).reason.startswith("`cmake` would run")


@pytest.mark.parametrize("owner", ["$(id -u):$(id -g)", '"$(id -u):$(id -g)"', "{uid}:{gid}"])
@pytest.mark.parametrize("mount", ["-v .:/w", "--mount type=bind,source=.,target=/w",
                                   "--mount type=bind,src=.,dst=/w",
                                   "--mount type=bind,source=.,destination=/w"])
def test_handing_the_tree_back_to_the_user_needs_no_user_flag(repo, owner, mount):
    owner = owner.format(uid=os.getuid(), gid=os.getgid())
    command = f"docker run --rm {mount} alpine:3.20 chown -R {owner} /w"
    assert decide(command, repo, False) is None


@pytest.mark.parametrize("tail", ["chown -R 0:0 /w", "chown -R $(id -u):$(id -g) /x",
                                  "chown -R $(id -u):$(id -g) /w /etc", "chown $(id -u):$(id -g) /w",
                                  "sh -c 'chown -R $(id -u):$(id -g) /w'"])
def test_any_other_root_command_on_the_mount_is_still_denied(repo, tail):
    _denial(f"docker run --rm -v .:/w alpine:3.20 {tail}", repo)


def test_handback_to_a_mount_outside_the_repo_does_not_excuse_an_inside_one(repo):
    _denial("docker run -v .:/w -v /tmp:/t alpine:3.20 chown -R $(id -u):$(id -g) /t", repo)


@needs_git
def test_module_entry_point_runs_the_hook(tmp_path):
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    (root / ".mutation-gate.toml").write_text("")
    payload = json.dumps({"cwd": str(root), "tool_input": {"command": "docker run -v .:/w img"}})
    result = subprocess.run(
        [sys.executable, "-P", "-m", "mutation_gate.host_exec"], input=payload, capture_output=True,
        text=True, cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(Path(host_exec.__file__).parents[1])},
    )
    assert result.returncode == 2
    assert result.stderr.endswith(f"Run instead:\n  docker run {USER} -v .:/w img\n")
