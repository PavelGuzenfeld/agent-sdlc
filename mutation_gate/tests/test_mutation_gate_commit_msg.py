"""Intent: #71 decision 11 — `mutation-gate commit-msg` rejects a banned word
parsed from the bundled voice.md's `Never use:` line, an AI Co-Authored-By
trailer, a "Generated with" line and a Signed-off-by trailer, and accepts a
plain message. `--range` runs the same check over every commit in a range,
for the CI job that never runs commit-msg-stage pre-commit hooks. `git` is
stubbed throughout — the gate's own test image has no git binary."""

from pathlib import Path

import pytest

from mutation_gate import cli, commit_msg
from mutation_gate.repo import GateError

EXPECTED_BANNED_WORDS = [
    "delve",
    "robust",
    "comprehensive",
    "straightforward",
    "leverage",
    "furthermore",
    "it's worth noting",
]


def _at(local: str, domain: str) -> str:
    return f"{local}@{domain}"


def _stub_comment_config(output: str):
    def fake_git(*args, cwd=None):
        if args[:2] == ("config", "--get-regexp"):
            return output
        raise GateError("commit.cleanup not set")

    return fake_git


def test_banned_words_pins_the_parse_of_the_bundled_voice_md():
    assert commit_msg.banned_words(commit_msg._voice_text()) == EXPECTED_BANNED_WORDS
    assert "leverage" in EXPECTED_BANNED_WORDS


def test_voice_text_reads_the_packaged_rules_dir_not_a_hardcoded_copy(monkeypatch, tmp_path):
    custom = tmp_path / "voice.md"
    custom.write_text("Never use: zorbing.\n")
    monkeypatch.setattr(commit_msg, "RULES_DIR", tmp_path)
    assert commit_msg.banned_words(commit_msg._voice_text()) == ["zorbing"]


def test_banned_words_raises_when_the_never_use_line_is_missing():
    with pytest.raises(GateError):
        commit_msg.banned_words("# Voice\n\nNo banned line here.\n")


def test_banned_words_raises_when_the_line_parses_to_nothing():
    with pytest.raises(GateError):
        commit_msg.banned_words("Never use: .\n")


@pytest.mark.parametrize("word", EXPECTED_BANNED_WORDS[:-1])
def test_banned_word_matches_whole_word_case_insensitively(word):
    findings = commit_msg.check_message(f"we {word.upper()} today", EXPECTED_BANNED_WORDS)
    assert any(f.reason == f'banned word "{word}" (voice.md: Never use)' for f in findings)


def test_robustness_does_not_trip_the_whole_word_robust():
    findings = commit_msg.check_message("improve robustness of the parser", EXPECTED_BANNED_WORDS)
    assert findings == []


def test_quoted_phrase_matches_as_a_substring():
    findings = commit_msg.check_message(
        "it's worth noting this fixes the bug", EXPECTED_BANNED_WORDS
    )
    assert any(f.reason.startswith('banned word "it\'s worth noting"') for f in findings)


def test_signed_off_by_trailer_is_rejected():
    findings = commit_msg.check_message(f"fix a thing\n\nSigned-off-by: Pavel <{_at('pavel', 'example.com')}>", [])
    assert any(f.reason == "Signed-off-by trailer is not allowed" for f in findings)


def test_lowercase_signed_off_by_trailer_is_rejected():
    findings = commit_msg.check_message(f"fix a thing\n\nsigned-off-by: Pavel <{_at('pavel', 'example.com')}>", [])
    assert any(f.reason == "Signed-off-by trailer is not allowed" for f in findings)


def test_quoted_phrase_matches_regardless_of_case():
    findings = commit_msg.check_message("IT'S WORTH NOTING this fixes the bug", EXPECTED_BANNED_WORDS)
    assert any(f.reason.startswith('banned word "it\'s worth noting"') for f in findings)


def test_generated_with_line_is_rejected():
    findings = commit_msg.check_message(
        "fix a thing\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)", []
    )
    assert any(f.reason == '"Generated with" line is not allowed' for f in findings)


def test_finding_names_the_actual_line_number():
    findings = commit_msg.check_message(
        f"fix a thing\n\nSigned-off-by: Pavel <{_at('pavel', 'example.com')}>", []
    )
    assert [f.line_no for f in findings] == [3]


def test_generated_with_mid_sentence_is_allowed():
    findings = commit_msg.check_message("this lockfile was generated with npm", [])
    assert findings == []


def test_generated_with_line_without_an_emoji_prefix_is_rejected():
    findings = commit_msg.check_message("fix a thing\n\nGenerated with npm", [])
    assert any(f.reason == '"Generated with" line is not allowed' for f in findings)


@pytest.mark.parametrize(
    "trailer",
    [
        f"Co-Authored-By: Claude <{_at('noreply', 'anthropic.com')}>",
        f"Co-Authored-By: GitHub Copilot <{_at('copilot', 'github.com')}>",
        f"co-authored-by: ChatGPT <{_at('bot', 'openai.com')}>",
    ],
)
def test_ai_co_authored_by_trailer_is_rejected(trailer):
    findings = commit_msg.check_message(f"fix a thing\n\n{trailer}", [])
    assert any("Co-Authored-By names an AI" in f.reason for f in findings)


def test_human_co_authored_by_trailer_is_allowed():
    findings = commit_msg.check_message(
        f"fix a thing\n\nCo-Authored-By: Jane Doe <{_at('jane', 'example.com')}>", []
    )
    assert findings == []


def test_human_name_containing_an_ai_marker_substring_is_allowed():
    findings = commit_msg.check_message(
        f"fix a thing\n\nCo-Authored-By: Maria Lombardi <{_at('maria', 'example.com')}>", []
    )
    assert findings == []


def test_plain_message_passes():
    assert commit_msg.check_message("fix a plain thing", EXPECTED_BANNED_WORDS) == []


def test_editor_comment_lines_and_scissors_diff_are_stripped():
    message = (
        "fix a plain thing\n"
        "\n"
        "# Please enter the commit message for your changes. Lines starting\n"
        "# with '#' will be ignored.\n"
        "#\n"
        "# ------------------------ >8 ------------------------\n"
        "# Do not modify or remove the line above.\n"
        "# Everything below it will be ignored.\n"
        "diff --git a/x.py b/x.py\n"
        "+we should leverage this\n"
    )
    assert commit_msg.check_message(commit_msg._strip_editor_cruft(message), EXPECTED_BANNED_WORDS) == []


def test_a_ticket_reference_before_the_scissors_line_survives_the_strip():
    message = (
        "Fix #12 something\n"
        "\n"
        f"Co-Authored-By: Claude <{_at('noreply', 'anthropic.com')}>\n"
        "\n"
        "# ------------------------ >8 ------------------------\n"
        "# Do not modify or remove the line above.\n"
        "diff --git a/x.py b/x.py\n"
        "+we should leverage this\n"
    )
    stripped = commit_msg._strip_editor_cruft(message)
    assert "Fix #12 something" in stripped
    findings = commit_msg.check_message(stripped, EXPECTED_BANNED_WORDS)
    reasons = [f.reason for f in findings]
    assert any("Co-Authored-By names an AI" in r for r in reasons)
    assert not any("leverage" in r for r in reasons)


def test_strip_editor_cruft_strips_every_line_prefixed_with_the_given_comment_char():
    message = (
        "fix a plain thing\n"
        "\n"
        "; Please enter the commit message for your changes. Lines starting\n"
        "; with ';' will be ignored.\n"
        "#not a comment under a semicolon char, stays as body\n"
    )
    stripped = commit_msg._strip_editor_cruft(message, ";")
    assert "fix a plain thing" in stripped
    assert "Please enter the commit message" not in stripped
    assert "with ';' will be ignored" not in stripped
    assert "#not a comment under a semicolon char, stays as body" in stripped


def test_indented_comment_char_line_is_not_column_zero_so_it_survives():
    message = "body text\n  # indented, not at column zero\n"
    assert commit_msg._strip_editor_cruft(message, "#") == message


def test_scissors_line_under_a_semicolon_comment_char_truncates_the_diff():
    message = (
        "fix a plain thing\n"
        "\n"
        "; ------------------------ >8 ------------------------\n"
        "diff --git a/x.py b/x.py\n"
        "+we should leverage this\n"
    )
    stripped = commit_msg._strip_editor_cruft(message, ";")
    assert "fix a plain thing" in stripped
    assert "leverage" not in stripped


def test_a_hash_scissors_line_does_not_truncate_under_a_semicolon_comment_char():
    message = (
        "fix a plain thing\n"
        "\n"
        "# ------------------------ >8 ------------------------\n"
        "diff --git a/x.py b/x.py\n"
        "+we should leverage this\n"
    )
    stripped = commit_msg._strip_editor_cruft(message, ";")
    assert "leverage" in stripped


def test_strip_editor_cruft_strips_every_line_prefixed_with_a_multi_char_comment_string():
    message = (
        "fix a plain thing\n"
        "\n"
        ";; Please enter the commit message for your changes. Lines starting\n"
        ";; with ';;' will be ignored.\n"
    )
    stripped = commit_msg._strip_editor_cruft(message, ";;")
    assert "fix a plain thing" in stripped
    assert "Please enter the commit message" not in stripped


def test_scissors_line_under_a_multi_char_comment_string_truncates_the_diff():
    message = (
        "fix a plain thing\n"
        "\n"
        ";; ------------------------ >8 ------------------------\n"
        "diff --git a/x.py b/x.py\n"
        "+we should leverage this\n"
    )
    stripped = commit_msg._strip_editor_cruft(message, ";;")
    assert "fix a plain thing" in stripped
    assert "leverage" not in stripped


def test_strip_editor_cruft_is_a_no_op_when_comment_char_is_none():
    message = "fix a thing\n\n# nothing was resolved so nothing is stripped\n"
    assert commit_msg._strip_editor_cruft(message, None) == message


def test_strip_editor_cruft_keeps_comment_lines_but_still_cuts_the_scissors_diff_when_strip_comments_is_false():
    message = (
        "fix a plain thing\n"
        "\n"
        "# a template comment above scissors\n"
        "\n"
        "# ------------------------ >8 ------------------------\n"
        "diff --git a/x.py b/x.py\n"
        "+we should leverage this\n"
    )
    stripped = commit_msg._strip_editor_cruft(message, "#", strip_comments=False)
    assert "a template comment above scissors" in stripped
    assert "leverage" not in stripped


@pytest.mark.parametrize("mode", ["", "default", "strip"])
def test_strips_comments_is_true_for_the_modes_git_actually_strips_comments_under(mode):
    assert commit_msg._strips_comments(mode) is True


@pytest.mark.parametrize("mode", ["whitespace", "verbatim", "scissors"])
def test_strips_comments_is_false_for_the_modes_git_keeps_comment_lines_under(mode):
    assert commit_msg._strips_comments(mode) is False


def test_configured_cleanup_mode_reads_commit_cleanup(monkeypatch):
    seen = {}

    def fake_git(*args, cwd=None):
        seen["args"] = args
        return "whitespace\n"

    monkeypatch.setattr(commit_msg, "git", fake_git)
    assert commit_msg._configured_cleanup_mode() == "whitespace"
    assert seen["args"] == ("config", "--get", "commit.cleanup")


def test_configured_cleanup_mode_defaults_to_empty_when_commit_cleanup_is_unset(monkeypatch):
    def boom(*a, cwd=None):
        raise GateError("key not set")

    monkeypatch.setattr(commit_msg, "git", boom)
    assert commit_msg._configured_cleanup_mode() == ""


def test_configured_cleanup_mode_defaults_to_empty_when_git_binary_is_missing(monkeypatch):
    def boom(*a, cwd=None):
        raise FileNotFoundError("git")

    monkeypatch.setattr(commit_msg, "git", boom)
    assert commit_msg._configured_cleanup_mode() == ""


def test_resolve_comment_char_returns_the_literal_configured_value(monkeypatch):
    monkeypatch.setattr(commit_msg, "git", lambda *a, cwd=None: "core.commentchar ;\n")
    assert commit_msg._resolve_comment_char("anything") == ";"


def test_configured_comment_char_reads_both_comment_config_keys(monkeypatch):
    seen = {}

    def fake_git(*args, cwd=None):
        seen["args"] = args
        return "core.commentchar ;\n"

    monkeypatch.setattr(commit_msg, "git", fake_git)
    commit_msg._configured_comment_char()
    assert seen["args"] == ("config", "--get-regexp", r"^core\.comment(char|string)$")


def test_configured_comment_char_prefers_commentstring_when_listed_after_commentchar(monkeypatch):
    monkeypatch.setattr(
        commit_msg, "git", lambda *a, cwd=None: "core.commentchar @\ncore.commentstring ;;\n"
    )
    assert commit_msg._configured_comment_char() == ";;"


def test_configured_comment_char_prefers_commentchar_when_listed_after_commentstring(monkeypatch):
    monkeypatch.setattr(
        commit_msg, "git", lambda *a, cwd=None: "core.commentstring ;;\ncore.commentchar @\n"
    )
    assert commit_msg._configured_comment_char() == "@"


def test_configured_comment_char_defaults_to_hash_when_the_matched_line_carries_no_value(monkeypatch):
    monkeypatch.setattr(commit_msg, "git", lambda *a, cwd=None: "core.commentchar\n")
    assert commit_msg._configured_comment_char() == "#"


def test_resolve_comment_char_defaults_to_hash_when_core_commentchar_is_unset(monkeypatch):
    def boom(*a, cwd=None):
        raise GateError("key not set")

    monkeypatch.setattr(commit_msg, "git", boom)
    assert commit_msg._resolve_comment_char("anything") == "#"


def test_resolve_comment_char_defaults_to_hash_when_git_binary_is_missing(monkeypatch):
    def boom(*a, cwd=None):
        raise FileNotFoundError("git")

    monkeypatch.setattr(commit_msg, "git", boom)
    assert commit_msg._resolve_comment_char("anything") == "#"


@pytest.mark.parametrize("char", ["@", ";", "!"])
def test_resolve_comment_char_auto_reads_whichever_char_git_actually_used(monkeypatch, char):
    monkeypatch.setattr(commit_msg, "git", lambda *a, cwd=None: "core.commentchar auto\n")
    message = (
        "fix a thing\n"
        "\n"
        f"{char} Please enter the commit message for your changes. Lines starting\n"
        f"{char} with '{char}' will be ignored, and an empty message aborts the commit.\n"
    )
    assert commit_msg._resolve_comment_char(message) == char


def test_resolve_comment_char_auto_ignores_an_unrelated_char_before_the_hint(monkeypatch):
    monkeypatch.setattr(commit_msg, "git", lambda *a, cwd=None: "core.commentchar auto\n")
    message = (
        "fix a thing\n"
        "; not the resolved char, just message prose\n"
        "\n"
        "@ Please enter the commit message for your changes. Lines starting\n"
        "@ with '@' will be ignored, and an empty message aborts the commit.\n"
    )
    assert commit_msg._resolve_comment_char(message) == "@"


def test_resolve_comment_char_auto_strips_nothing_without_a_hint_line(monkeypatch):
    monkeypatch.setattr(commit_msg, "git", lambda *a, cwd=None: "core.commentchar auto\n")
    assert commit_msg._resolve_comment_char("fix a thing\n\nbody text\n") is None


def test_resolve_comment_char_auto_from_commentstring_reads_the_hint_line(monkeypatch):
    monkeypatch.setattr(commit_msg, "git", lambda *a, cwd=None: "core.commentstring auto\n")
    message = (
        "fix a thing\n"
        "\n"
        "; Please enter the commit message for your changes. Lines starting\n"
        "; with ';' will be ignored, and an empty message aborts the commit.\n"
    )
    assert commit_msg._resolve_comment_char(message) == ";"


def _msgfile(tmp_path: Path, text: str) -> str:
    path = tmp_path / "MSG"
    path.write_text(text)
    return str(path)


def test_cli_rejects_a_banned_word_and_names_the_reason(tmp_path, capsys):
    msgfile = _msgfile(tmp_path, "we should leverage this")
    assert cli.main(["commit-msg", msgfile]) == 1
    assert 'banned word "leverage"' in capsys.readouterr().err


def test_cli_accepts_a_plain_message(tmp_path):
    msgfile = _msgfile(tmp_path, "fix a plain thing")
    assert cli.main(["commit-msg", msgfile]) == 0


def test_cli_rejects_a_signed_off_by_trailer(tmp_path, capsys):
    msgfile = _msgfile(tmp_path, f"fix a thing\n\nSigned-off-by: Pavel <{_at('pavel', 'example.com')}>")
    assert cli.main(["commit-msg", msgfile]) == 1
    assert "Signed-off-by trailer is not allowed" in capsys.readouterr().err


def test_cli_under_semicolon_comment_char_trips_on_the_body_word_not_the_template_line(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(commit_msg, "git", _stub_comment_config("core.commentchar ;\n"))
    message = (
        "we should leverage this\n"
        "\n"
        "fix a plain thing\n"
        "; we should leverage this too\n"
    )
    msgfile = _msgfile(tmp_path, message)
    assert cli.main(["commit-msg", msgfile]) == 1
    err = capsys.readouterr().err
    assert "line 1:" in err
    assert "line 4:" not in err


def test_cli_under_semicolon_comment_char_accepts_a_banned_word_confined_to_the_template_line(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(commit_msg, "git", _stub_comment_config("core.commentchar ;\n"))
    message = "fix a plain thing\n\n; we should leverage this template hint\n"
    msgfile = _msgfile(tmp_path, message)
    assert cli.main(["commit-msg", msgfile]) == 0


def test_cli_under_a_multi_char_commentstring_trips_on_the_body_word_not_the_template_line(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(commit_msg, "git", _stub_comment_config("core.commentstring ;;\n"))
    message = (
        "we should leverage this\n"
        "\n"
        "fix a plain thing\n"
        ";; we should leverage this too\n"
    )
    msgfile = _msgfile(tmp_path, message)
    assert cli.main(["commit-msg", msgfile]) == 1
    err = capsys.readouterr().err
    assert "line 1:" in err
    assert "line 4:" not in err


def test_cli_commentstring_wins_over_an_earlier_commentchar(tmp_path, monkeypatch):
    monkeypatch.setattr(
        commit_msg,
        "git",
        _stub_comment_config("core.commentchar @\ncore.commentstring ;;\n"),
    )
    message = "fix a plain thing\n\n;; we should leverage this template hint\n"
    msgfile = _msgfile(tmp_path, message)
    assert cli.main(["commit-msg", msgfile]) == 0


def test_cli_under_auto_comment_char_strips_using_the_char_git_actually_used(tmp_path, monkeypatch):
    monkeypatch.setattr(commit_msg, "git", _stub_comment_config("core.commentchar auto\n"))
    message = (
        "fix a plain thing\n"
        "\n"
        "@ Please enter the commit message for your changes. Lines starting\n"
        "@ with '@' will be ignored, and an empty message aborts the commit.\n"
        "@ we should leverage this hint\n"
    )
    msgfile = _msgfile(tmp_path, message)
    assert cli.main(["commit-msg", msgfile]) == 0


def _fake_git_for_cleanup_mode(mode: str):
    def fake_git(*args, cwd=None):
        if args[:2] == ("config", "--get-regexp"):
            raise GateError("core.comment(char|string) not set")
        if args == ("config", "--get", "commit.cleanup"):
            return f"{mode}\n"
        raise AssertionError(args)

    return fake_git


def test_cli_under_commit_cleanup_whitespace_checks_a_banned_word_confined_to_a_comment_line(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(commit_msg, "git", _fake_git_for_cleanup_mode("whitespace"))
    message = "fix a plain thing\n\n# we should leverage this\n"
    msgfile = _msgfile(tmp_path, message)
    assert cli.main(["commit-msg", msgfile]) == 1
    assert 'banned word "leverage"' in capsys.readouterr().err


def test_cli_under_commit_cleanup_strip_ignores_a_banned_word_confined_to_a_comment_line(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(commit_msg, "git", _fake_git_for_cleanup_mode("strip"))
    message = "fix a plain thing\n\n# we should leverage this\n"
    msgfile = _msgfile(tmp_path, message)
    assert cli.main(["commit-msg", msgfile]) == 0


def test_cli_with_commit_cleanup_unset_keeps_todays_strip_behavior(tmp_path, monkeypatch):
    def boom(*a, cwd=None):
        raise GateError("key not set")

    monkeypatch.setattr(commit_msg, "git", boom)
    message = "fix a plain thing\n\n# we should leverage this\n"
    msgfile = _msgfile(tmp_path, message)
    assert cli.main(["commit-msg", msgfile]) == 0


def test_cli_refuses_with_no_msgfile_and_no_range():
    assert cli.main(["commit-msg"]) == 2


def test_cli_refuses_on_an_unreadable_msgfile(tmp_path):
    assert cli.main(["commit-msg", str(tmp_path / "missing")]) == 2


def test_cli_refuses_when_the_never_use_line_parses_to_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(commit_msg, "_voice_text", lambda: "Never use: .\n")
    msgfile = _msgfile(tmp_path, "fix a plain thing")
    assert cli.main(["commit-msg", msgfile]) == 2


def test_cli_status_comment_above_the_scissors_line_is_not_checked(tmp_path):
    message = (
        "fix a plain thing\n"
        "\n"
        "# we should leverage this in the status comment\n"
        "# ------------------------ >8 ------------------------\n"
        "diff --git a/x.py b/x.py\n"
    )
    msgfile = _msgfile(tmp_path, message)
    assert cli.main(["commit-msg", msgfile]) == 0


def test_cli_rejects_an_ai_trailer_after_a_ticket_reference_under_commit_v(tmp_path, capsys):
    message = (
        "Fix #12 something\n"
        "\n"
        f"Co-Authored-By: Claude <{_at('noreply', 'anthropic.com')}>\n"
        "\n"
        "# ------------------------ >8 ------------------------\n"
        "diff --git a/x.py b/x.py\n"
        "+we should leverage this\n"
    )
    msgfile = _msgfile(tmp_path, message)
    assert cli.main(["commit-msg", msgfile]) == 1
    err = capsys.readouterr().err
    assert "Co-Authored-By names an AI" in err
    assert "leverage" not in err


def test_cli_refuses_when_the_range_lookup_raises(monkeypatch):
    def boom(*args, cwd=None):
        raise GateError("bad range")

    monkeypatch.setattr(commit_msg, "git", boom)
    assert cli.main(["commit-msg", "--range", "bad..bad"]) == 2


SHA_A = "a" * 40
SHA_B = "b" * 12 + "Z" + "b" * 27
SHA_C = "c" * 40

RANGE_LOG = (
    f"{SHA_A}\x1ffix a plain thing\n\x00"
    f"{SHA_B}\x1fwe should leverage this\n\x00"
    f"{SHA_C}\x1fanother plain thing\n\x00"
)


def test_range_form_blocks_on_the_offending_commit_only(monkeypatch, capsys):
    monkeypatch.setattr(commit_msg, "git", lambda *a, cwd=None: RANGE_LOG)
    assert cli.main(["commit-msg", "--range", "base..head"]) == 1
    err = capsys.readouterr().err
    assert f"commit-msg: {SHA_B[:12]}\n" in err
    assert "Z" not in err
    assert 'banned word "leverage"' in err
    assert SHA_A[:12] not in err
    assert SHA_C[:12] not in err


def test_range_form_passes_when_every_message_in_range_is_clean(monkeypatch):
    clean_log = f"{SHA_A}\x1ffix a plain thing\n\x00{SHA_C}\x1fanother plain thing\n\x00"
    monkeypatch.setattr(commit_msg, "git", lambda *a, cwd=None: clean_log)
    assert cli.main(["commit-msg", "--range", "base..head"]) == 0


def test_range_form_skips_an_empty_record_without_dropping_the_next_commit(monkeypatch, capsys):
    log_with_empty_record = f"{SHA_A}\x1ffix a plain thing\n\x00\x00{SHA_B}\x1fwe should leverage this\n\x00"
    monkeypatch.setattr(commit_msg, "git", lambda *a, cwd=None: log_with_empty_record)
    assert cli.main(["commit-msg", "--range", "base..head"]) == 1
    assert f"commit-msg: {SHA_B[:12]}\n" in capsys.readouterr().err


def test_range_form_catches_an_ai_trailer_not_just_a_banned_word(monkeypatch, capsys):
    log = f"{SHA_A}\x1ffix a thing\n\nCo-Authored-By: Claude <{_at('noreply', 'anthropic.com')}>\n\x00"
    monkeypatch.setattr(commit_msg, "git", lambda *a, cwd=None: log)
    assert cli.main(["commit-msg", "--range", "base..head"]) == 1
    assert "Co-Authored-By names an AI" in capsys.readouterr().err


def test_range_messages_passes_the_given_range_to_git(monkeypatch):
    seen = {}

    def fake_git(*args, cwd=None):
        seen["args"] = args
        return ""

    monkeypatch.setattr(commit_msg, "git", fake_git)
    commit_msg._range_messages("base..head")
    assert seen["args"] == ("log", "-z", "base..head", "--pretty=format:%H%x1f%B")
