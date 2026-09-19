"""Intent: dotfiles#74 — a gated repo's docker test command runs as root, so
every run left root-owned __pycache__/.pytest_cache in the bind-mounted repo.
Those are directories: a host user cannot rm them without another container,
and they show up as untracked noise after every gated commit."""

import pytest

from mutation_gate import runner


def test_a_docker_test_command_cannot_write_root_owned_cache_dirs_into_the_repo():
    cmd, container = runner._prepare_docker_run('docker run --rm -v "$PWD":/repo img pytest')
    # After the image name docker hands these to pytest as argv, and the
    # container still runs as root with its default environment.
    assert cmd.startswith(
        f"docker run --name {container} -e PYTHONDONTWRITEBYTECODE=1"
        " -e PYTEST_ADDOPTS='-p no:cacheprovider' --rm"
    )


def test_a_command_that_names_its_own_container_keeps_that_name_and_gets_the_env():
    cmd, container = runner._prepare_docker_run("docker run --name mine img pytest")
    assert cmd.startswith(
        "docker run -e PYTHONDONTWRITEBYTECODE=1"
        " -e PYTEST_ADDOPTS='-p no:cacheprovider' --name mine"
    )
    assert container is None, "docker rm -f must not target a name the pack never passed"


def test_the_pack_named_container_is_returned_so_a_timeout_can_remove_it():
    cmd, container = runner._prepare_docker_run("docker run img pytest")
    assert container is not None and container.startswith("mutation-gate-")
    assert cmd.startswith(f"docker run --name {container} ")


def test_a_non_docker_test_command_is_handed_to_the_shell_unchanged():
    cmd, container = runner._prepare_docker_run("pytest -q tests")
    assert cmd == "pytest -q tests"
    assert container is None


@pytest.mark.parametrize(
    "command",
    ["docker run a && docker run b", "docker run --name mine a && docker run b"],
)
def test_a_chained_command_has_only_its_first_docker_run_rewritten(command):
    cmd, _ = runner._prepare_docker_run(command)
    assert cmd.count("PYTHONDONTWRITEBYTECODE") == 1
    assert cmd.endswith("&& docker run b")
