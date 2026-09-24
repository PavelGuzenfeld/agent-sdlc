"""Intent: dotfiles#60 — the isolated export must carry only the files it was
built from; run_isolated must not write its own prompt into the work dir it
hands to the isolated `claude` process."""

import subprocess as sp
from pathlib import Path

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
