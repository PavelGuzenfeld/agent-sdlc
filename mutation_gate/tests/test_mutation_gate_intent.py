"""Intent: dotfiles#75 — the adversary reviewed a change against an unrelated
issue, because the intent chain mined an issue number out of a previous commit
and an explicitly passed --user-prompt never got reached. Nothing in the output
said which intent was used, so a mismatch read as a confident finding."""

import subprocess

import pytest

from mutation_gate import adversary, repo as repo_mod

STALE_SUBJECT = "tests only, fix deferred (#151)\n"


def _repo(root):
    return repo_mod.Repo(
        root=root,
        origin="https://github.com/PavelGuzenfeld/x.git",
        remotes=("origin",),
        config=repo_mod.Config(),
    )


def _linked_worktree(tmp_path, branch: str):
    main = tmp_path / "main"
    main.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.email", "t"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=main, check=True)
    (main / "f.txt").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=main, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=main, check=True)
    wt = tmp_path / "wt"
    subprocess.run(["git", "worktree", "add", "-q", "-b", branch, str(wt)], cwd=main, check=True)
    return _repo(wt)


@pytest.fixture
def on_branch(tmp_path, monkeypatch):
    """The #75 shape: everything a commit message can offer — COMMIT_EDITMSG and
    `git log -1` alike — names an issue the change under review is not about."""

    def _checkout(branch: str):
        git_dir = tmp_path / ".git"
        git_dir.mkdir(exist_ok=True)
        (git_dir / "COMMIT_EDITMSG").write_text(STALE_SUBJECT)

        def fake_git(*args, cwd=None):
            if args[0] == "rev-parse":
                return branch + "\n"
            return STALE_SUBJECT

        monkeypatch.setattr(adversary, "git", fake_git)
        return _repo(tmp_path)

    return _checkout


def test_an_explicit_user_prompt_is_the_intent_even_when_a_ticket_is_inferrable(
    on_branch, monkeypatch
):
    repo = on_branch("fix/153-the-deferred-fix")
    monkeypatch.setattr(adversary, "_issue_body", lambda *a: pytest.fail(
        "looked a ticket up instead of using the intent it was handed"))
    intent = adversary.resolve_intent(repo, "make overlap exclusive at the boundary")
    assert intent is not None
    assert intent.source == "user prompt"
    assert intent.text == "make overlap exclusive at the boundary"


def test_the_ticket_is_the_branchs_issue_not_the_previous_commits(on_branch, monkeypatch):
    repo = on_branch("fix/153-the-deferred-fix")
    monkeypatch.setattr(adversary, "_issue_body", lambda _r, n: f"body of {n}")
    intent = adversary.resolve_intent(repo, None)
    assert intent is not None
    assert intent.source == "issue #153"
    assert intent.text == "body of 153"


def test_no_prompt_and_no_branch_number_skips_rather_than_guessing(on_branch, monkeypatch):
    repo = on_branch("fix/utf-8-decode")
    monkeypatch.setattr(adversary, "_issue_body", lambda _r, n: pytest.fail(
        f"read a digit out of a branch that names no issue: #{n}"))
    assert adversary.resolve_intent(repo, None) is None


def test_an_issue_number_that_resolves_to_nothing_skips_rather_than_reviewing_blind(
    on_branch, monkeypatch
):
    repo = on_branch("fix/153-the-deferred-fix")
    monkeypatch.setattr(adversary, "_issue_body", lambda *a: "")
    assert adversary.resolve_intent(repo, None) is None


@pytest.mark.parametrize(
    "branch,expected",
    [
        ("fix/153-the-deferred-fix", "153"),
        ("153-the-deferred-fix", "153"),
        ("fix/utf-8-decode", ""),
        ("fix/v2-rewrite", ""),
        ("main", ""),
        ("backup/pre-scrub", ""),
    ],
)
def test_branch_issue_reads_only_a_leading_issue_number(on_branch, branch, expected):
    assert adversary._branch_issue(on_branch(branch)) == expected


def test_a_branch_the_git_call_cannot_resolve_yields_no_ticket(tmp_path, monkeypatch):
    def boom(*args, cwd=None):
        raise repo_mod.GateError("not a git repository")

    monkeypatch.setattr(adversary, "git", boom)
    assert adversary._branch_issue(_repo(tmp_path)) == ""


@pytest.mark.parametrize("source", ["issue #153", "user prompt"])
def test_findings_name_the_intent_they_were_reviewed_against(source, monkeypatch):
    monkeypatch.setattr(adversary, "run_isolated", lambda *a, **k: "no gaps found")
    out = adversary.run([], adversary.Intent(source, "body"), "")
    assert out == f"intent: {source}\n\nno gaps found"


def test_the_isolated_review_receives_the_intent_body_that_was_resolved(monkeypatch):
    exported = {}

    def fake_isolated(_name, _prompt, work):
        exported["intent"] = (work / "INTENT.md").read_text()
        return "no gaps found"

    monkeypatch.setattr(adversary, "run_isolated", fake_isolated)
    adversary.run([], adversary.Intent("issue #153", "the fix #151 deferred"), "")
    assert "the fix #151 deferred" in exported["intent"]
    assert "issue #153" in exported["intent"]


def test_a_skipped_adversary_says_so_instead_of_naming_an_intent():
    out = adversary.run([], None, "3 mutants, 0 survived")
    assert "intent:" not in out
    assert "adversary skipped" in out
    assert "3 mutants, 0 survived" in out


def test_a_gated_commit_on_its_ticket_branch_in_a_linked_worktree_resolves_intent(
    tmp_path, monkeypatch
):
    repo = _linked_worktree(tmp_path, "90-adversary-intent-subagent-branch")
    monkeypatch.setattr(adversary, "_issue_body", lambda _r, n: f"body of {n}")
    intent = adversary.resolve_intent(repo, None)
    assert intent is not None
    assert intent.source == "issue #90"
    assert adversary.run([], intent, "").startswith("intent: issue #90")


def test_a_gated_commit_on_the_harness_default_worktree_branch_skips_the_adversary(
    tmp_path, monkeypatch
):
    repo = _linked_worktree(tmp_path, "worktree-agent-a0cce6e8f54bb4467")
    monkeypatch.setattr(adversary, "_issue_body", lambda *a: pytest.fail(
        "read a digit out of a branch a subagent worktree actually uses"))
    intent = adversary.resolve_intent(repo, None)
    assert intent is None
    assert "adversary skipped" in adversary.run([], intent, "")
