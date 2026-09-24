"""Intent: dotfiles#61 — a lock held by a concurrent run must skip the Stop
hook (--worktree), not refuse it; --staged has no fallback and still refuses.
dotfiles#62 — a report a green pre-commit hook would swallow must still land
on disk. dotfiles#68 item 1 — the Stop hook's process cwd is the session's
launch directory, not wherever a Bash `cd` took the shell; --worktree must
read the real one from the hook's JSON payload on stdin, and --staged must
never touch stdin at all."""

import contextlib
import json
import sys
from pathlib import Path

import pytest

from mutation_gate import cli
from mutation_gate.repo import Config, GateError, Repo


def _repo(tmp_path: Path) -> Repo:
    return Repo(root=tmp_path, origin="", remotes=(), config=Config())


def _no_ast_grep_on_path(monkeypatch) -> None:
    monkeypatch.setattr(cli.mutants.shutil, "which", lambda name: None)


def _not_a_git_repo(*args, **kwargs):
    raise GateError("fatal: not a git repository")


def _locked(repo):
    raise GateError(f"another mutation-gate is running in {repo.root.name}")


def _discover_spy(tmp_path, seen):
    def _discover(cwd=None):
        seen["cwd"] = cwd
        return _repo(tmp_path)
    return _discover


def test_worktree_skips_instead_of_refusing_when_the_repo_is_locked(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", _locked)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert cli.main(["--worktree"]) == 0


def test_staged_still_refuses_when_the_repo_is_locked(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", _locked)
    assert cli.main(["--staged"]) == 2


def test_staged_refuses_cleanly_when_ast_grep_is_missing_from_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"foo.py": {1}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    _no_ast_grep_on_path(monkeypatch)
    assert cli.main(["--staged"]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "ast-grep" in err


def test_staged_skips_ast_grep_check_when_no_gated_file_changed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"README.md": {1}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    _no_ast_grep_on_path(monkeypatch)
    assert cli.main(["--staged"]) == 0
    assert "ast-grep" not in capsys.readouterr().err


def test_staged_says_the_adversary_did_not_run_on_a_test_only_change(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"tests/foo_test.sh": {1}})
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)

    def _must_not_run(*args, **kwargs):
        raise AssertionError("adversary must not run on a test-only change")

    monkeypatch.setattr(cli.adversary, "run", _must_not_run)
    _no_ast_grep_on_path(monkeypatch)
    assert cli.main(["--staged"]) == 0
    err = capsys.readouterr().err
    assert ("mutation-gate: no gated source files in this change — "
            "no mutants, so no adversary review") in err.splitlines()


def test_staged_still_requires_ast_grep_when_a_gated_file_is_mixed_with_a_docs_file(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "discover", lambda cwd=None: _repo(tmp_path))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(
        cli.mutants, "changed_lines", lambda root, staged: {"README.md": {1}, "foo.py": {1}}
    )
    monkeypatch.setattr(cli.model_vv, "git", _not_a_git_repo)
    _no_ast_grep_on_path(monkeypatch)
    assert cli.main(["--staged"]) == 2
    assert "ast-grep" in capsys.readouterr().err


def test_staged_refuses_cleanly_when_git_is_missing_from_path(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert cli.main(["--staged", "--dry-run"]) == 2
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "git" in err


def test_worktree_reads_cwd_from_the_hook_stdin_json(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "discover", _discover_spy(tmp_path, seen))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: "stop here")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdin, "read", lambda: json.dumps({"cwd": str(tmp_path / "sub")}))
    assert cli.main(["--worktree"]) == 0
    assert seen["cwd"] == Path(tmp_path / "sub")


def test_worktree_falls_back_to_process_cwd_when_stdin_is_a_tty(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "discover", _discover_spy(tmp_path, seen))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: "stop here")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert cli.main(["--worktree"]) == 0
    assert seen["cwd"] is None


def test_staged_never_reads_stdin_for_a_cwd(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "discover", _discover_spy(tmp_path, seen))
    monkeypatch.setattr(cli, "skip_reason", lambda repo: "stop here")

    def _boom():
        raise AssertionError("staged mode must not read stdin")

    monkeypatch.setattr(sys.stdin, "isatty", _boom)
    assert cli.main(["--staged"]) == 0
    assert seen["cwd"] is None


def test_write_report_saves_to_cache_root_keyed_by_repo(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(cli, "CACHE_ROOT", cache)
    repo = _repo(tmp_path / "repo")
    path = cli._write_report(repo, "adversary", "findings text\n")
    assert path == cache / repo.key / "reports" / "adversary.md"
    assert path.read_text() == "findings text\n"


def _write_transcript(tmp_path: Path, prompt: str) -> Path:
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in [
        {"type": "user", "message": {"role": "user", "content": prompt}},
        {"type": "assistant", "message": {"role": "assistant",
                                           "content": [{"type": "text", "text": "on it"}]}},
        {"type": "user", "message": {"role": "user",
                                      "content": [{"type": "tool_result",
                                                   "tool_use_id": "t1", "content": "ok"}]}},
        {"type": "user", "message": {"role": "user",
                                      "content": [{"type": "text",
                                                   "text": "[Request interrupted by user]"}]}},
        {"type": "user", "message": {"role": "user", "content":
            "<task-notification>\n<task-id>abc</task-id>\n</task-notification>"}},
        {"type": "assistant", "message": {"role": "assistant",
                                           "content": [{"type": "text", "text": "done"}]}},
    ]) + "\n")
    return path


def _stub_gate_to_pass(monkeypatch, tmp_path, cands):
    monkeypatch.setattr(cli.runner, "guard_clean_start", lambda repo: None)
    monkeypatch.setattr(cli.waivers, "load", lambda repo: [])
    monkeypatch.setattr(cli.mutants, "changed_lines", lambda root, staged: {"src/x.py": {1}})
    monkeypatch.setattr(cli.model_vv, "check", lambda *a: [])
    monkeypatch.setattr(cli.model_vv, "model_changed", lambda *a: False)
    monkeypatch.setattr(cli.mutants, "language_of", lambda f: "python")
    monkeypatch.setattr(cli.mutants, "require_ast_grep", lambda: None)
    monkeypatch.setattr(cli.coverage_map, "candidates", lambda *a: cands)
    monkeypatch.setattr(cli.coverage_map, "blob_hashes", lambda *a: ["h"])
    monkeypatch.setattr(cli.token, "is_valid", lambda *a: True)
    monkeypatch.setattr(cli, "CACHE_ROOT", tmp_path / "cache")


def _run_worktree_with_hook_stdin(monkeypatch, tmp_path, branch, transcript):
    seen = {}
    repo = _repo(tmp_path)
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdin, "read", lambda: json.dumps(
        {"cwd": str(tmp_path), "transcript_path": str(transcript)}))
    monkeypatch.setattr(cli.adversary, "git", lambda *a, cwd=None: branch + "\n")

    def _capture_run(cands, intent, summary):
        seen["intent"] = intent
        return "no gaps found"

    monkeypatch.setattr(cli.adversary, "run", _capture_run)
    _stub_gate_to_pass(monkeypatch, tmp_path, [tmp_path / "t.py"])
    assert cli.main(["--worktree"]) == 0
    return seen["intent"]


def test_worktree_uses_the_transcripts_last_user_prompt_as_intent_on_a_non_ticket_branch(
    tmp_path, monkeypatch
):
    transcript = _write_transcript(tmp_path, "why is the decode failing at the boundary")
    intent = _run_worktree_with_hook_stdin(monkeypatch, tmp_path, "fix/utf-8-decode", transcript)
    assert intent is not None
    assert intent.source == "session prompt"
    assert intent.text == "why is the decode failing at the boundary"


def test_worktree_still_prefers_the_branchs_ticket_over_the_transcripts_prompt(
    tmp_path, monkeypatch
):
    transcript = _write_transcript(tmp_path, "unrelated chat text")
    monkeypatch.setattr(cli.adversary, "_issue_body", lambda _r, n: f"body of {n}")
    intent = _run_worktree_with_hook_stdin(monkeypatch, tmp_path, "153-the-deferred-fix", transcript)
    assert intent is not None
    assert intent.source == "issue #153"
    assert intent.text == "body of 153"


def test_worktree_user_prompt_flag_wins_over_ticket_and_session_prompt(tmp_path, monkeypatch):
    seen = {}
    repo = _repo(tmp_path)
    transcript = _write_transcript(tmp_path, "unrelated chat text")
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdin, "read", lambda: json.dumps(
        {"cwd": str(tmp_path), "transcript_path": str(transcript)}))
    monkeypatch.setattr(cli.adversary, "git", lambda *a, cwd=None: "153-the-deferred-fix\n")
    monkeypatch.setattr(cli.adversary, "_issue_body", lambda *a: pytest.fail(
        "looked up a ticket instead of using the explicit --user-prompt flag"))

    def _capture_run(cands, intent, summary):
        seen["intent"] = intent
        return "no gaps found"

    monkeypatch.setattr(cli.adversary, "run", _capture_run)
    _stub_gate_to_pass(monkeypatch, tmp_path, [tmp_path / "t.py"])
    assert cli.main(["--worktree", "--user-prompt", "explicit override"]) == 0
    assert seen["intent"].source == "user prompt"
    assert seen["intent"].text == "explicit override"


def test_worktree_skips_the_adversary_cleanly_with_no_transcript_and_no_ticket(
    tmp_path, monkeypatch, capsys
):
    repo = _repo(tmp_path)
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(cli, "skip_reason", lambda repo: None)
    monkeypatch.setattr(cli.runner, "repo_lock", lambda repo: contextlib.nullcontext())
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdin, "read", lambda: json.dumps({"cwd": str(tmp_path)}))
    monkeypatch.setattr(cli.adversary, "git", lambda *a, cwd=None: "fix/utf-8-decode\n")
    _stub_gate_to_pass(monkeypatch, tmp_path, [tmp_path / "t.py"])
    assert cli.main(["--worktree"]) == 0
    assert "adversary skipped" in capsys.readouterr().err


def test_session_prompt_skips_tool_results_and_returns_the_real_user_text(tmp_path):
    transcript = _write_transcript(tmp_path, "the actual prompt")
    assert cli._session_prompt(str(transcript)) == "the actual prompt"


def test_session_prompt_is_none_without_a_transcript_path():
    assert cli._session_prompt(None) is None


def test_session_prompt_is_none_when_the_file_is_missing(tmp_path):
    assert cli._session_prompt(str(tmp_path / "missing.jsonl")) is None


def test_session_prompt_skips_a_bad_json_line_and_keeps_reading(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "earlier prompt"}})
        + "\n{not json\n"
    )
    assert cli._session_prompt(str(path)) == "earlier prompt"


def test_session_prompt_is_none_when_every_user_entry_is_meta_or_a_tool_result(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in [
        {"type": "user", "isMeta": True, "message": {"role": "user", "content": "Caveat: background summary"}},
        {"type": "user", "message": {"role": "user",
                                      "content": [{"type": "tool_result", "content": "ok"}]}},
    ]) + "\n")
    assert cli._session_prompt(str(path)) is None


def test_session_prompt_uses_the_later_of_two_real_prompts(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in [
        {"type": "user", "message": {"role": "user", "content": "first prompt"}},
        {"type": "user", "message": {"role": "user", "content": "second prompt"}},
    ]) + "\n")
    assert cli._session_prompt(str(path)) == "second prompt"


def test_session_prompt_joins_multiple_text_blocks_in_one_turn(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "text", "text": "line one"}, {"type": "text", "text": "line two"},
    ]}}) + "\n")
    assert cli._session_prompt(str(path)) == "line one\nline two"


def test_session_prompt_skips_a_transcript_line_that_is_not_a_json_object(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join([
        json.dumps(["not", "a", "dict"]),
        json.dumps({"type": "user", "message": {"role": "user", "content": "earlier prompt"}}),
    ]) + "\n")
    assert cli._session_prompt(str(path)) == "earlier prompt"


def test_stop_hook_payload_ignores_a_non_dict_json_body(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdin, "read", lambda: "[]")
    assert cli._stop_hook_payload() == {}


@pytest.mark.parametrize("wrapper", [
    "<system-reminder>x</system-reminder>",
    "<command-name>/exit</command-name>",
    "<command-message>cleanup</command-message>",
    "<local-command-stdout>Goodbye!</local-command-stdout>",
    "<local-command-caveat>Caveat: earlier messages were generated by a slash command",
    "<task-notification>\n<task-id>abc</task-id>\n</task-notification>",
    "[Request interrupted by user]",
    "This session is being continued from a previous conversation that ran out of context.",
])
def test_session_prompt_skips_every_known_harness_wrapper(tmp_path, wrapper):
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in [
        {"type": "user", "message": {"role": "user", "content": "the real prompt"}},
        {"type": "user", "message": {"role": "user", "content": wrapper}},
    ]) + "\n")
    assert cli._session_prompt(str(path)) == "the real prompt"


def test_session_prompt_at_the_cap_is_kept_whole(tmp_path):
    prompt = "a" * 4000
    path = tmp_path / "transcript.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
    assert cli._session_prompt(str(path)) == prompt


def test_session_prompt_one_over_the_cap_is_truncated(tmp_path):
    prompt = "a" * 4001
    path = tmp_path / "transcript.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
    assert cli._session_prompt(str(path)) == "a" * 4000


def test_session_prompt_ignores_a_non_text_block_even_if_it_carries_a_text_field(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_use", "text": "should not leak"},
        {"type": "text", "text": "the real block"},
    ]}}) + "\n")
    assert cli._session_prompt(str(path)) == "the real block"
