"""Intent: dotfiles#60 — the isolated export must carry only the files it was
built from; run_isolated must not write its own prompt into the work dir it
hands to the isolated `claude` process."""

import os
import re
import subprocess as sp
from pathlib import Path

import pytest

from mutation_gate import adversary, repo as repo_mod


def test_run_isolated_does_not_write_prompt_into_the_work_dir(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["cwd_contents"] = sorted(p.name for p in Path(kwargs["cwd"]).rglob("*"))
        return sp.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    (tmp_path / "INTENT.md").write_text("intent\n")
    monkeypatch.setattr(adversary.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(adversary.subprocess, "run", fake_run)
    assert adversary.run_isolated("adversary", "the prompt", tmp_path) == "ok"
    assert "PROMPT.md" not in seen["cwd_contents"]


def test_the_prompt_sends_the_adversary_to_the_export_files_in_its_cwd(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return sp.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(adversary.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(adversary.subprocess, "run", fake_run)
    adversary.run_isolated("adversary", adversary.PROMPT, tmp_path)
    prompt = seen["argv"][2]
    assert "INTENT.md" in prompt
    assert "tests/" in prompt


def test_run_exports_the_real_intent_and_test_content_before_reviewing(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        work = Path(kwargs["cwd"])
        seen["intent_md"] = (work / "INTENT.md").read_text()
        seen["test_file"] = (work / "tests" / "test_thing.py").read_text()
        return sp.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    test_file = tmp_path / "test_thing.py"
    test_file.write_text("def test_thing():\n    assert True\n")
    intent = adversary.Intent("issue #268", "the stated intent body")
    monkeypatch.setattr(adversary.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(adversary.subprocess, "run", fake_run)
    adversary.run([test_file], intent, "")
    assert "the stated intent body" in seen["intent_md"]
    assert seen["test_file"] == test_file.read_text()


def test_the_adversary_run_leaves_no_claude_session_behind(tmp_path, fake_claude):
    adversary.run([], adversary.Intent("issue #394", "intent body"), "")
    assert "--no-session-persistence" in fake_claude()


def _repo(root):
    return repo_mod.Repo(
        root=root,
        origin="https://github.com/PavelGuzenfeld/x.git",
        remotes=("origin",),
        config=repo_mod.Config(),
    )


def _on_branch(tmp_path, monkeypatch, branch, labels):
    seen = {}

    def fake_git(*args, cwd=None):
        assert args[0] == "rev-parse"
        return branch + "\n"

    def fake_run(argv, **kwargs):
        if argv[0] == "gh":
            stdout = f'{{"title": "t", "body": "b", "labels": {labels}}}\n'
            return sp.CompletedProcess(argv, 0, stdout=stdout, stderr="")
        seen["claude_argv"] = argv
        return sp.CompletedProcess(argv, 0, stdout="no gaps found\n", stderr="")

    monkeypatch.setattr(adversary, "git", fake_git)
    monkeypatch.setattr(adversary.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(adversary.subprocess, "run", fake_run)
    return _repo(tmp_path), seen


def test_the_adversary_runs_on_the_tickets_model_label(tmp_path, monkeypatch):
    labels = '[{"name": "ready"}, {"name": "model:sonnet"}]'
    repo, seen = _on_branch(tmp_path, monkeypatch, "263-kata-overhead", labels)
    intent = adversary.resolve_intent(repo, None)
    adversary.run([], intent, "")
    assert seen["claude_argv"][-2:] == ["--model", "sonnet"]


def test_the_adversary_gets_no_model_flag_without_a_model_label(tmp_path, monkeypatch):
    labels = '[{"name": "ready"}]'
    repo, seen = _on_branch(tmp_path, monkeypatch, "263-kata-overhead", labels)
    intent = adversary.resolve_intent(repo, None)
    adversary.run([], intent, "")
    assert "--model" not in seen["claude_argv"]


def test_a_gh_failure_leaves_the_ticket_unresolved(tmp_path, monkeypatch):
    def fake_run(argv, **kwargs):
        return sp.CompletedProcess(argv, 1, stdout="", stderr="not found")

    monkeypatch.setattr(adversary, "git", lambda *a, cwd=None: "263-kata-overhead\n")
    monkeypatch.setattr(adversary.subprocess, "run", fake_run)
    assert adversary.resolve_intent(_repo(tmp_path), None) is None


def test_the_tickets_title_and_body_join_with_a_blank_line(tmp_path, monkeypatch):
    def fake_run(argv, **kwargs):
        return sp.CompletedProcess(
            argv, 0, stdout='{"title": "t", "body": "b\\n", "labels": []}\n', stderr=""
        )

    monkeypatch.setattr(adversary, "git", lambda *a, cwd=None: "263-kata-overhead\n")
    monkeypatch.setattr(adversary.subprocess, "run", fake_run)
    intent = adversary.resolve_intent(_repo(tmp_path), None)
    assert intent.text == "t\n\nb"


def _projects_folder(config: Path, work: Path) -> Path:
    return config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(work.resolve()))


def test_the_run_leaves_no_empty_projects_folder_for_its_cwd(tmp_path, fake_claude):
    work = tmp_path / "gate work"
    work.mkdir()
    adversary.run_isolated("adversary", "the prompt", work)
    config = Path(os.environ["CLAUDE_CONFIG_DIR"])
    assert not _projects_folder(config, work).exists()


def test_a_projects_folder_holding_a_file_is_left_alone_including_its_empty_subfolders(
    tmp_path, fake_claude
):
    work = tmp_path / "gate-work"
    work.mkdir()
    config = Path(os.environ["CLAUDE_CONFIG_DIR"])
    folder = _projects_folder(config, work)
    held = folder / "notes.md"
    folder.mkdir(parents=True)
    held.write_text("kept\n")
    adversary.run_isolated("adversary", "the prompt", work)
    assert held.read_text() == "kept\n"
    assert (folder / "memory").is_dir()


def test_an_isolated_run_is_capped_at_ten_minutes(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        return sp.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(adversary.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(adversary.subprocess, "run", fake_run)
    adversary.run_isolated("adversary", "the prompt", tmp_path)
    assert seen["timeout"] == 600


def test_a_timed_out_run_still_leaves_no_empty_projects_folder(tmp_path, monkeypatch):
    work = tmp_path / "gate-work"
    work.mkdir()
    config = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.setattr(adversary.shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(argv, **kwargs):
        (_projects_folder(config, work) / "memory").mkdir(parents=True)
        raise sp.TimeoutExpired(argv, 600)

    monkeypatch.setattr(adversary.subprocess, "run", fake_run)
    with pytest.raises(sp.TimeoutExpired):
        adversary.run_isolated("adversary", "the prompt", work)
    assert not _projects_folder(config, work).exists()


def test_without_claude_config_dir_the_folder_is_cleared_under_home(tmp_path, monkeypatch):
    work = tmp_path / "gate-work"
    work.mkdir()
    home = tmp_path / "home"
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(adversary.shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(argv, **kwargs):
        (_projects_folder(home / ".claude", work) / "memory").mkdir(parents=True)
        return sp.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(adversary.subprocess, "run", fake_run)
    adversary.run_isolated("adversary", "the prompt", work)
    assert not _projects_folder(home / ".claude", work).exists()
