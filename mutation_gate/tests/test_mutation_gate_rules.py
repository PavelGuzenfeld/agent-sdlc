"""Intent: #73 (decisions 3, 5 and 8 of #71) — the rules live in each opted-in
repo as .claude/rules/*.md, written from the installed package by
`mutation-gate rules sync` and held byte-exact there by `rules check`.
Only git root discovery is stubbed (the test image has no git); the config
load, the packaged files and the CLI entry point are real."""

import re
from pathlib import Path

import pytest

from mutation_gate import cli, rules, vocabulary
from mutation_gate.repo import Config, GateError, Repo

SCOPED = "filters/"
PACKAGED = sorted(p.name for p in rules.RULES_DIR.glob("*.md"))
UNSCOPED = [name for name in PACKAGED if name != rules.SCOPED_RULE]

AGENTS_BEGIN = "<!-- BEGIN mutation-gate rules -->"
AGENTS_END = "<!-- END mutation-gate rules -->"


def _expected_block(items: dict[str, bytes]) -> bytes:
    sections = [f"## {name[:-3]}\n\n".encode() + content for name, content in items.items()]
    return f"{AGENTS_BEGIN}\n".encode() + b"\n".join(sections) + f"\n{AGENTS_END}".encode()


def _unscoped_bytes() -> dict[str, bytes]:
    return {name: (rules.RULES_DIR / name).read_bytes() for name in UNSCOPED}


def _fresh_repo(tmp_path: Path, monkeypatch, toml: str) -> Path:
    if "model_paths" in toml and "model_spec" not in toml:
        toml += 'model_spec = "issue:1"\n'
    (tmp_path / ".mutation-gate.toml").write_text(toml)
    monkeypatch.setattr(
        rules, "discover",
        lambda cwd=None: Repo(root=tmp_path, origin="", remotes=(), config=Config.load(tmp_path)),
    )
    return tmp_path / ".claude" / "rules"


def _named(capsys) -> str:
    return capsys.readouterr().err


def test_every_rule_at_the_repo_root_is_packaged():
    at_root = sorted(p.name for p in (Path(__file__).parents[2] / "rules").glob("*.md"))
    assert PACKAGED == at_root
    assert rules.SCOPED_RULE in PACKAGED


@pytest.mark.parametrize("name", PACKAGED)
def test_every_packaged_rule_has_a_snippet_in_docs_rules_md(name):
    docs_rules = (Path(__file__).parents[2] / "docs" / "rules.md").read_text()
    assert f'--8<-- "rules/{name}"' in docs_rules


def test_sync_then_check_passes_with_model_paths_set(tmp_path, monkeypatch):
    synced = _fresh_repo(tmp_path, monkeypatch, f'model_paths = ["{SCOPED}"]\n')
    assert cli.main(["rules", "sync"]) == 0
    assert sorted(p.name for p in synced.iterdir()) == PACKAGED
    assert cli.main(["rules", "check"]) == 0


def test_unscoped_rule_is_written_as_the_packaged_bytes(tmp_path, monkeypatch):
    synced = _fresh_repo(tmp_path, monkeypatch, f'model_paths = ["{SCOPED}"]\n')
    cli.main(["rules", "sync"])
    for name in UNSCOPED:
        assert (synced / name).read_bytes() == (rules.RULES_DIR / name).read_bytes()


def test_model_vv_leads_with_paths_frontmatter_built_from_model_paths(tmp_path, monkeypatch):
    synced = _fresh_repo(
        tmp_path, monkeypatch, 'model_paths = ["filters/", "gst/common/kalman_box.cpp"]\n'
    )
    cli.main(["rules", "sync"])
    body = (rules.RULES_DIR / rules.SCOPED_RULE).read_bytes()
    frontmatter = (
        b'---\npaths:\n  - "filters/**"\n'
        b'  - "gst/common/kalman_box.cpp"\n  - "gst/common/kalman_box.cpp/**"\n---\n'
    )
    assert (synced / rules.SCOPED_RULE).read_bytes() == frontmatter + body


@pytest.mark.parametrize("entry", ["filters", "gst/common"])
def test_slashless_directory_entry_renders_as_both_the_entry_and_its_glob_in_model_vv_and_agents(
    tmp_path, monkeypatch, entry
):
    root = _fresh_repo(tmp_path, monkeypatch, f'model_paths = ["{entry}"]\n').parents[1]
    assert cli.main(["rules", "sync"]) == 0
    expected = f'---\npaths:\n  - "{entry}"\n  - "{entry}/**"\n---\n'.encode()
    model_vv = (root / ".claude" / "rules" / rules.SCOPED_RULE).read_bytes()
    assert model_vv.startswith(expected)
    agents = (root / "AGENTS.md").read_bytes()
    assert b"## model-vv\n\n" + expected in agents


@pytest.mark.parametrize("entry", ["src/*.py", "src/?.py", "src/[ab].py", "src/**"])
def test_glob_entry_stays_verbatim_as_a_single_line(tmp_path, monkeypatch, entry):
    synced = _fresh_repo(tmp_path, monkeypatch, f'model_paths = ["{entry}"]\n')
    cli.main(["rules", "sync"])
    body = (synced / rules.SCOPED_RULE).read_bytes()
    assert body.startswith(f'---\npaths:\n  - "{entry}"\n---\n'.encode())


def _flip_byte(path: Path, index: int) -> None:
    original = path.read_bytes()
    path.write_bytes(original[:index] + bytes([original[index] ^ 1]) + original[index + 1:])


@pytest.mark.parametrize("name", PACKAGED)
def test_one_byte_body_edit_fails_check_naming_only_that_file(tmp_path, monkeypatch, capsys, name):
    synced = _fresh_repo(tmp_path, monkeypatch, f'model_paths = ["{SCOPED}"]\n')
    cli.main(["rules", "sync"])
    _flip_byte(synced / name, -1)
    capsys.readouterr()
    assert cli.main(["rules", "check"]) == 1
    err = _named(capsys)
    assert f".claude/rules/{name}" in err
    assert all(other not in err for other in PACKAGED if other != name)


def test_hand_edited_frontmatter_fails_check_with_config_unchanged(tmp_path, monkeypatch, capsys):
    synced = _fresh_repo(tmp_path, monkeypatch, f'model_paths = ["{SCOPED}"]\n')
    cli.main(["rules", "sync"])
    _flip_byte(synced / rules.SCOPED_RULE, len(b"---\npaths:\n  - \"filters/"))
    capsys.readouterr()
    assert cli.main(["rules", "check"]) == 1
    assert f".claude/rules/{rules.SCOPED_RULE}" in _named(capsys)


def test_changing_model_paths_without_resync_fails_check_naming_model_vv(tmp_path, monkeypatch, capsys):
    root = _fresh_repo(tmp_path, monkeypatch, f'model_paths = ["{SCOPED}"]\n').parents[1]
    cli.main(["rules", "sync"])
    (root / ".mutation-gate.toml").write_text('model_paths = ["other/"]\nmodel_spec = "issue:1"\n')
    capsys.readouterr()
    assert cli.main(["rules", "check"]) == 1
    err = _named(capsys)
    assert f".claude/rules/{rules.SCOPED_RULE}" in err
    assert all(other not in err for other in UNSCOPED)


@pytest.mark.parametrize("toml", ["", "model_paths = []\n"])
def test_repo_without_model_paths_gets_no_model_vv(tmp_path, monkeypatch, toml):
    synced = _fresh_repo(tmp_path, monkeypatch, toml)
    assert cli.main(["rules", "sync"]) == 0
    assert sorted(p.name for p in synced.iterdir()) == UNSCOPED
    assert cli.main(["rules", "check"]) == 0


def test_emptying_model_paths_after_sync_fails_check_until_resync_removes_model_vv(
    tmp_path, monkeypatch, capsys
):
    synced = _fresh_repo(tmp_path, monkeypatch, f'model_paths = ["{SCOPED}"]\n')
    cli.main(["rules", "sync"])
    (synced.parents[1] / ".mutation-gate.toml").write_text("")
    capsys.readouterr()
    assert cli.main(["rules", "check"]) == 1
    assert f".claude/rules/{rules.SCOPED_RULE}" in _named(capsys)
    assert cli.main(["rules", "sync"]) == 0
    assert not (synced / rules.SCOPED_RULE).exists()
    assert cli.main(["rules", "check"]) == 0


def test_deleted_synced_rule_fails_check_naming_it(tmp_path, monkeypatch, capsys):
    synced = _fresh_repo(tmp_path, monkeypatch, "")
    cli.main(["rules", "sync"])
    (synced / UNSCOPED[-1]).unlink()
    capsys.readouterr()
    assert cli.main(["rules", "check"]) == 1
    assert f".claude/rules/{UNSCOPED[-1]}" in _named(capsys)


def test_naming_rule_syncs_appears_in_agents_md_and_drift_fails_check(
    tmp_path, monkeypatch, capsys
):
    synced = _fresh_repo(tmp_path, monkeypatch, "")
    root = synced.parents[1]
    assert cli.main(["rules", "sync"]) == 0
    body = (rules.RULES_DIR / "naming.md").read_bytes()
    assert (synced / "naming.md").read_bytes() == body
    assert b"## naming\n\n" + body in (root / "AGENTS.md").read_bytes()
    assert cli.main(["rules", "check"]) == 0
    _flip_byte(synced / "naming.md", -1)
    capsys.readouterr()
    assert cli.main(["rules", "check"]) == 1
    assert ".claude/rules/naming.md" in _named(capsys)


def test_tickets_rule_names_the_follow_up_convention():
    content = (Path(__file__).parents[2] / "rules" / "tickets.md").read_text()
    for token in ("correctness", "clarity", "security", "performance", "scope", "size:tiny"):
        assert f"`{token}`" in content
    assert "never born with a `model:<name>` label" in content


def test_no_rule_command_or_doc_names_the_ready_label():
    root = Path(__file__).parents[2]
    pattern = re.compile(r"`ready`")
    offenders = [
        str(path.relative_to(root))
        for base in ("rules", "commands", "docs")
        for path in sorted((root / base).rglob("*.md"))
        if pattern.search(path.read_text())
    ]
    assert offenders == []


def test_kata_names_the_model_labels_as_the_queue():
    content = (Path(__file__).parents[2] / "commands" / "kata.md").read_text()
    normalized = " ".join(content.split())
    assert "`model:haiku`, `model:sonnet`, `model:opus` or `model:fable`" in normalized
    assert "asks which model; that answer is the triage" in normalized
    assert "dispatches only the first, on haiku" in normalized


@pytest.mark.parametrize("path", ["commands/done.md", "commands/kata.md", "commands/debrief-agent.md"])
def test_follow_up_filers_point_to_the_tickets_rule_instead_of_naming_labels(path):
    content = (Path(__file__).parents[2] / path).read_text()
    for token in ("follow-up", "correctness", "clarity", "security", "performance", "scope", "size:tiny"):
        assert f"`{token}`" not in content
    assert "rules/tickets.md" in content


def test_kata_narrows_pins_and_routes_the_222_leftover_decisions():
    """Intent: #280 (decisions 6, 7 and 8 of #222)."""
    content = (Path(__file__).parents[2] / "commands" / "kata.md").read_text()
    normalized = " ".join(content.split())
    assert "saw fail or deferred out loud this session" in normalized
    assert '"None" is the normal answer' in normalized
    assert "noticed but not acted on" not in normalized
    assert "works the queue as it stood when it started" in normalized
    assert "its step 5 files the agent's candidates" in normalized
    assert "Then file the agent's follow-up candidates" not in normalized

    done_content = (Path(__file__).parents[2] / "commands" / "done.md").read_text()
    done_normalized = " ".join(done_content.split())
    assert "saw fail or deferred out loud this session" in done_normalized
    assert '"None" the normal answer' in done_normalized
    assert "noticed but not acted on" not in done_normalized


def test_kata_batches_confirmed_tiny_tickets_onto_one_batch_branch():
    content = (Path(__file__).parents[2] / "commands" / "kata.md").read_text()
    normalized = " ".join(content.split())
    assert "never batch tickets onto a shared branch" not in normalized
    assert "size:tiny" in normalized
    assert "batches of at most five" in normalized
    assert "oldest ticket" in normalized
    assert "never adds an unlabelled ticket" in normalized
    assert "reverts that ticket's changes off the branch" in normalized
    assert "returns to the queue as a single run" in normalized
    assert "`/kata <N>`" in normalized
    assert "alone, even when it carries size:tiny" in normalized
    assert "opens two PRs" in normalized


def test_kata_queue_and_dispatch_require_an_assignee():
    content = (Path(__file__).parents[2] / "commands" / "kata.md").read_text()
    normalized = " ".join(content.split())
    assert "`model:opus` or `model:fable`, assigned to `@me`" in normalized
    assert "one not assigned to `@me`, was never in the queue" in normalized
    assert "nor a ticket not assigned to `@me`" in normalized
    assert "asks whether to take it; that answer is the triage" in normalized
    assert "stops, names the assignee, and never reassigns" in normalized
    assert "opens one PR with `--assignee @me`" in normalized
    assert "assigned to someone else dispatches only the first" in normalized


def test_tickets_rule_names_the_assignee_convention():
    content = (Path(__file__).parents[2] / "rules" / "tickets.md").read_text()
    normalized = " ".join(content.split())
    assert "name one responsible person as assignee" in normalized
    assert "An agent works only tickets assigned to the `gh` user it runs as, `@me`" in normalized
    assert "never born with a `model:<name>` label or an assignee" in normalized


def test_grill_plan_assigns_its_step_tickets_to_me():
    content = (Path(__file__).parents[2] / "commands" / "grill.md").read_text()
    normalized = " ".join(content.split())
    assert "labeled `model:<name>`, assigned to `@me`" in normalized


def test_naming_rule_never_lists_three_or_more_core_words_on_one_line():
    core_words = set(vocabulary.load(Path("."), "").concepts)
    content = (rules.RULES_DIR / "naming.md").read_text()
    for line in content.splitlines():
        found = {w for w in re.findall(r"[a-z]+", line.lower()) if w in core_words}
        assert len(found) < 3, f"{line!r} restates the dictionary: {found}"


def test_check_says_how_to_recover(tmp_path, monkeypatch, capsys):
    _fresh_repo(tmp_path, monkeypatch, "")
    capsys.readouterr()
    assert cli.main(["rules", "check"]) == 1
    assert "mutation-gate rules sync" in _named(capsys)


def test_console_script_dispatches_rules_from_the_real_argv(tmp_path, monkeypatch):
    synced = _fresh_repo(tmp_path, monkeypatch, "")

    def _no_gate_run(cwd=None):
        raise GateError("the gate must not run for a rules command")

    monkeypatch.setattr(cli, "discover", _no_gate_run)
    monkeypatch.setattr(cli.sys, "argv", ["mutation-gate", "rules", "sync"])
    assert cli.main() == 0
    assert sorted(p.name for p in synced.iterdir()) == UNSCOPED


def test_rules_outside_a_git_repo_are_refused(monkeypatch, capsys):
    def _not_a_repo(cwd=None):
        raise GateError("git rev-parse --show-toplevel: fatal: not a git repository")

    monkeypatch.setattr(rules, "discover", _not_a_repo)
    assert cli.main(["rules", "sync"]) == 2
    assert "refused" in _named(capsys)


def test_sync_writes_agents_md_block_when_absent(tmp_path, monkeypatch):
    root = _fresh_repo(tmp_path, monkeypatch, "").parents[1]
    assert cli.main(["rules", "sync"]) == 0
    expected = _expected_block(_unscoped_bytes()) + b"\n"
    assert (root / "AGENTS.md").read_bytes() == expected


def test_sync_preserves_hand_written_agents_md_and_appends_block(tmp_path, monkeypatch):
    root = _fresh_repo(tmp_path, monkeypatch, "").parents[1]
    hand = b"# My notes\n\nDo not touch this.\n"
    (root / "AGENTS.md").write_bytes(hand)
    assert cli.main(["rules", "sync"]) == 0
    written = (root / "AGENTS.md").read_bytes()
    assert written.startswith(hand)
    assert _expected_block(_unscoped_bytes()) in written


def test_tampering_inside_the_agents_md_block_fails_check_naming_it(tmp_path, monkeypatch, capsys):
    root = _fresh_repo(tmp_path, monkeypatch, "").parents[1]
    cli.main(["rules", "sync"])
    agents = root / "AGENTS.md"
    original = agents.read_bytes()
    index = original.index(AGENTS_BEGIN.encode()) + 60
    agents.write_bytes(original[:index] + bytes([original[index] ^ 1]) + original[index + 1:])
    capsys.readouterr()
    assert cli.main(["rules", "check"]) == 1
    assert "AGENTS.md" in _named(capsys)


def test_check_fails_when_agents_md_is_missing(tmp_path, monkeypatch, capsys):
    _fresh_repo(tmp_path, monkeypatch, "")
    capsys.readouterr()
    assert cli.main(["rules", "check"]) == 1
    assert "AGENTS.md: missing" in _named(capsys)


def test_check_fails_when_agents_md_exists_without_the_block(tmp_path, monkeypatch, capsys):
    root = _fresh_repo(tmp_path, monkeypatch, "").parents[1]
    (root / "AGENTS.md").write_bytes(b"# Notes\n\nNo block here.\n")
    capsys.readouterr()
    assert cli.main(["rules", "check"]) == 1
    assert "AGENTS.md: missing the mutation-gate rules block" in _named(capsys)


def test_sync_is_idempotent_for_agents_md(tmp_path, monkeypatch):
    root = _fresh_repo(tmp_path, monkeypatch, "").parents[1]
    cli.main(["rules", "sync"])
    first = (root / "AGENTS.md").read_bytes()
    cli.main(["rules", "sync"])
    assert (root / "AGENTS.md").read_bytes() == first


def test_sync_replaces_stale_block_between_markers_preserving_surrounding_text(tmp_path, monkeypatch):
    root = _fresh_repo(tmp_path, monkeypatch, "").parents[1]
    before = b"# Notes before\n\n"
    stale = f"{AGENTS_BEGIN}\nstale\n{AGENTS_END}".encode()
    after = b"\n\n# Notes after\n"
    (root / "AGENTS.md").write_bytes(before + stale + after)
    assert cli.main(["rules", "sync"]) == 0
    written = (root / "AGENTS.md").read_bytes()
    assert written.startswith(before)
    assert written.endswith(after)
    assert _expected_block(_unscoped_bytes()) in written
    assert b"stale" not in written


def test_editing_outside_the_agents_md_block_does_not_fail_check(tmp_path, monkeypatch):
    root = _fresh_repo(tmp_path, monkeypatch, "").parents[1]
    cli.main(["rules", "sync"])
    agents = root / "AGENTS.md"
    agents.write_bytes(agents.read_bytes() + b"\n# Appended by hand\n")
    assert cli.main(["rules", "check"]) == 0


_MALFORMED_AGENTS_MD = {
    "begin_only": f"{AGENTS_BEGIN}\nsomething\n".encode(),
    "end_only": f"something\n{AGENTS_END}\n".encode(),
    "duplicate_pair": (
        f"{AGENTS_BEGIN}\na\n{AGENTS_END}\n{AGENTS_BEGIN}\nb\n{AGENTS_END}\n"
    ).encode(),
    "end_before_begin": f"{AGENTS_END}\n{AGENTS_BEGIN}\n".encode(),
}


@pytest.mark.parametrize("action", ["sync", "check"])
@pytest.mark.parametrize("shape", sorted(_MALFORMED_AGENTS_MD))
def test_malformed_agents_md_markers_are_refused(tmp_path, monkeypatch, capsys, shape, action):
    root = _fresh_repo(tmp_path, monkeypatch, "").parents[1]
    content = _MALFORMED_AGENTS_MD[shape]
    (root / "AGENTS.md").write_bytes(content)
    capsys.readouterr()
    assert cli.main(["rules", action]) == 2
    assert "refused" in _named(capsys)
    assert (root / "AGENTS.md").read_bytes() == content


def test_model_vv_leads_agents_md_section_with_its_globs(tmp_path, monkeypatch):
    paths = ["filters/", "gst/common/kalman_box.cpp"]
    root = _fresh_repo(tmp_path, monkeypatch, f'model_paths = {paths!r}\n').parents[1]
    assert cli.main(["rules", "sync"]) == 0
    written = (root / "AGENTS.md").read_bytes()
    frontmatter = rules.frontmatter(paths)
    body = (rules.RULES_DIR / rules.SCOPED_RULE).read_bytes()
    assert b"## model-vv\n\n" + frontmatter + body in written


def test_debrief_agent_references_file_follow_ups_step():
    repo_root = Path(__file__).parents[2]
    done_content = (repo_root / "commands" / "done.md").read_text()
    debrief_content = (repo_root / "commands" / "debrief-agent.md").read_text()

    match = re.search(r"### (\d+)\. File follow-ups", done_content)
    assert match, "Could not find '### N. File follow-ups' heading in done.md"
    file_follow_ups_step = match.group(1)

    assert f"step {file_follow_ups_step} uses" in debrief_content, (
        f"debrief-agent.md should reference step {file_follow_ups_step} "
        f"(the 'File follow-ups' step from done.md), but does not"
    )
