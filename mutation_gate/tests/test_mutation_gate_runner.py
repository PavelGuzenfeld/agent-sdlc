"""Intent: dotfiles#74 — a gated repo's docker test command runs as root, so
every run left root-owned __pycache__/.pytest_cache in the bind-mounted repo.
Those are directories: a host user cannot rm them without another container,
and they show up as untracked noise after every gated commit."""

import pytest

from mutation_gate import repo as repo_mod, runner


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


def _repo(tmp_path):
    return repo_mod.Repo(root=tmp_path, origin="", remotes=(), config=repo_mod.Config())


@pytest.mark.parametrize(
    ("returncode", "output"),
    [
        (2, b""),
        (1, b"ERROR collecting tests/test_x.py\n"),
        (1, b"!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!\n"),
    ],
)
def test_a_baseline_that_could_not_import_its_tests_is_a_collection_failure(returncode, output):
    assert runner._looks_like_collection_failure(returncode, output)


def test_a_baseline_that_ran_and_lost_is_not_a_collection_failure():
    assert not runner._looks_like_collection_failure(1, b"1 failed, 3 passed\n")


def test_a_summary_that_merely_mentions_a_test_named_during_collection_is_not_a_false_positive():
    assert not runner._looks_like_collection_failure(
        1, b"FAILED tests/test_during_collection_ordering.py::test_x - assert False\n"
    )


def test_a_baseline_that_fails_to_collect_names_the_stale_image_not_the_suite(tmp_path):
    command = "sh -c 'printf \"1 error during collection\\n\"; exit 2'"
    with pytest.raises(runner.GateError, match="failed to collect") as excinfo:
        runner.baseline_green(_repo(tmp_path), [], command)
    assert "rebuild" in str(excinfo.value)


def test_a_baseline_that_fails_its_assertions_keeps_the_existing_refusal(tmp_path):
    command = "sh -c 'printf \"1 failed, 3 passed\\n\"; exit 1'"
    with pytest.raises(
        runner.GateError,
        match=r"baseline suite failed unmutated; every mutant would report KILLED",
    ) as excinfo:
        runner.baseline_green(_repo(tmp_path), [], command)
    assert "collect" not in str(excinfo.value)


def test_the_collection_and_assertion_refusals_read_differently(tmp_path):
    collection_command = "sh -c 'printf \"1 error during collection\\n\"; exit 2'"
    assertion_command = "sh -c 'printf \"1 failed, 3 passed\\n\"; exit 1'"
    with pytest.raises(runner.GateError) as collection_err:
        runner.baseline_green(_repo(tmp_path), [], collection_command)
    with pytest.raises(runner.GateError) as assertion_err:
        runner.baseline_green(_repo(tmp_path), [], assertion_command)
    assert str(collection_err.value) != str(assertion_err.value)


def test_a_collection_error_is_caught_by_its_marker_even_at_a_non_collection_exit_code(tmp_path):
    command = "sh -c 'printf \"ERROR collecting tests/test_x.py\\n\"; exit 1'"
    with pytest.raises(runner.GateError, match="failed to collect"):
        runner.baseline_green(_repo(tmp_path), [], command)


def test_a_baseline_matching_its_pass_pattern_is_green(tmp_path):
    repo = repo_mod.Repo(
        root=tmp_path, origin="", remotes=(), config=repo_mod.Config(pass_pattern="ok")
    )
    command = "sh -c 'printf \"ok\\n\"'"
    assert runner.baseline_green(repo, [], command) >= 0.0


def test_a_baseline_that_exits_clean_without_its_pass_pattern_is_refused(tmp_path):
    repo = repo_mod.Repo(
        root=tmp_path, origin="", remotes=(), config=repo_mod.Config(pass_pattern="ok")
    )
    command = "sh -c 'printf \"nope\\n\"'"
    with pytest.raises(runner.GateError, match="printed no pass_pattern"):
        runner.baseline_green(repo, [], command)
