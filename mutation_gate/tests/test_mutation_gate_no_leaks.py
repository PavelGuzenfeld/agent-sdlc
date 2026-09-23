"""Intent: #71 decision 12 — `mutation-gate no-leaks` blocks the identity,
RFC1918 and home-path shapes over the staged diff and commit message, plus a
`banned_names_file` of `X → Y` lines, and never echoes the matched text.
Fixture rows come from tests/fixtures/*.txt — never hardcode leak-shaped text
here, or this file trips its own scan. `git` is stubbed."""

from pathlib import Path

import pytest

from mutation_gate import cli, no_leaks
from mutation_gate.repo import Config, GateError, Repo

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _rows(name: str) -> list[tuple[str, str]]:
    rows = []
    for line in (FIXTURES / name).read_text().splitlines():
        label, sep, content = line.partition("|")
        if sep:
            rows.append((label, content))
    return rows


LEAKY_ROWS = [(label, content) for label, content in _rows("leaky.txt") if "ghcr.io" not in content]
CLEAN_ROWS = _rows("clean.txt")
EMAIL = next(content for label, content in _rows("leaky.txt") if label == "email")
GHCR_ROW = next(content for label, content in _rows("leaky.txt") if "ghcr.io" in content)

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DOCS = [
    REPO_ROOT / "skills" / "upstream" / "SKILL.md",
    REPO_ROOT / "commands" / "done.md",
    REPO_ROOT / "commands" / "debrief-agent.md",
    REPO_ROOT / "commands" / "activity.md",
]


def _diff(path: str, *lines: str, start: int = 1) -> str:
    body = "".join(f"+{line}\n" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +{start},{len(lines)} @@\n"
        f"{body}"
    )


def _stub_git(monkeypatch, *, diff: str = "", log: str = ""):
    calls: list[tuple[str, ...]] = []

    def fake_git(*args: str, cwd=None) -> str:
        calls.append(args)
        if args[0] == "diff":
            return diff
        if args[0] == "log":
            return log
        raise AssertionError(f"unexpected git call {args}")

    monkeypatch.setattr(no_leaks, "git", fake_git)
    return calls


def _repo(tmp_path: Path, config: Config | None = None) -> Repo:
    return Repo(root=tmp_path, origin="", remotes=(), config=config or Config())


def _local(monkeypatch, tmp_path: Path, message: str = "plain change", config: Config | None = None) -> int:
    monkeypatch.setattr(no_leaks, "discover", lambda: _repo(tmp_path, config))
    msgfile = tmp_path / "MSG"
    msgfile.write_text(message)
    return cli.main(["no-leaks", str(msgfile)])


def _range(monkeypatch, tmp_path: Path, config: Config | None = None) -> int:
    monkeypatch.setattr(no_leaks, "discover", lambda: _repo(tmp_path, config))
    return cli.main(["no-leaks", "--range", "base..HEAD"])


@pytest.fixture
def banned_config(tmp_path: Path) -> Config:
    banned_file = tmp_path.parent / f"{tmp_path.name}-banned.txt"
    banned_file.write_text("- foo → bar\n")
    yield Config(banned_names_file=str(banned_file))
    banned_file.unlink()


@pytest.mark.parametrize("label,content", LEAKY_ROWS)
def test_generic_scan_matches_every_leaky_fixture_row(label, content):
    assert no_leaks.generic_hit(content), label


@pytest.mark.parametrize("label,content", CLEAN_ROWS)
def test_generic_scan_passes_every_clean_fixture_row(label, content):
    assert not no_leaks.generic_hit(content), label


def test_the_ghcr_namespace_check_stays_shell_only():
    assert not no_leaks.generic_hit(GHCR_ROW)


@pytest.mark.parametrize("path", REFERENCE_DOCS, ids=lambda p: p.name)
def test_the_leak_reference_docs_point_at_the_setting_not_the_old_path(path):
    text = path.read_text()
    assert "banned_names_file" in text
    assert "public-surface" not in text


def test_a_staged_email_is_blocked_without_echoing_it(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, diff=_diff("fixture.txt", EMAIL))
    assert _local(monkeypatch, tmp_path) == 1
    err = capsys.readouterr().err
    assert "fixture.txt:1" in err
    assert EMAIL not in err


def test_a_clean_staged_line_passes(monkeypatch, tmp_path):
    _stub_git(monkeypatch, diff=_diff("fixture.txt", "plain prose line"))
    assert _local(monkeypatch, tmp_path) == 0


def test_a_leading_digit_does_not_widen_the_rfc1918_boundary():
    assert not no_leaks.generic_hit("x0192.168.5.5")


def test_the_diff_line_number_follows_the_hunk_header(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, diff=_diff("fixture.txt", EMAIL, start=3))
    assert _local(monkeypatch, tmp_path) == 1
    assert "fixture.txt:3" in capsys.readouterr().err


def test_consecutive_added_lines_number_one_past_the_other(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, diff=_diff("fixture.txt", "plain prose line", EMAIL, start=5))
    assert _local(monkeypatch, tmp_path) == 1
    assert "fixture.txt:6" in capsys.readouterr().err


def test_the_diff_content_drops_only_the_leading_plus(monkeypatch, tmp_path):
    _stub_git(monkeypatch, diff=_diff("fixture.txt", "XY plain line"))
    assert no_leaks._diff_added_lines(_repo(tmp_path), "--cached") == [("fixture.txt", 1, "XY plain line")]


def test_a_malformed_hunk_header_falls_back_to_line_zero(monkeypatch, tmp_path):
    diff = (
        "diff --git a/fixture.txt b/fixture.txt\n"
        "--- a/fixture.txt\n"
        "+++ b/fixture.txt\n"
        "@@ garbled @@\n"
        "+plain line\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert no_leaks._diff_added_lines(_repo(tmp_path), "--cached") == [("fixture.txt", 0, "plain line")]


def test_an_added_line_after_a_dev_null_post_image_is_not_attributed(monkeypatch, tmp_path):
    diff = (
        "diff --git a/fixture.txt b/fixture.txt\n"
        "--- a/fixture.txt\n"
        "+++ /dev/null\n"
        "@@ -1,0 +1,1 @@\n"
        f"+{EMAIL}\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert _local(monkeypatch, tmp_path) == 0


def test_a_quoted_post_image_header_for_a_non_ascii_name_still_attributes_the_line(monkeypatch, tmp_path, capsys):
    diff = (
        'diff --git "a/caf\\303\\251.txt" "b/caf\\303\\251.txt"\n'
        '--- "a/caf\\303\\251.txt"\n'
        '+++ "b/caf\\303\\251.txt"\n'
        "@@ -0,0 +1,1 @@\n"
        f"+{EMAIL}\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert _local(monkeypatch, tmp_path) == 1
    assert "caf\\303\\251.txt:1" in capsys.readouterr().err


def test_a_post_image_header_with_a_trailing_tab_for_a_spaced_name_still_attributes_the_line(monkeypatch, tmp_path, capsys):
    diff = (
        "diff --git a/my file.txt b/my file.txt\n"
        "--- a/my file.txt\n"
        "+++ b/my file.txt\t\n"
        "@@ -0,0 +1,1 @@\n"
        f"+{EMAIL}\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert _local(monkeypatch, tmp_path) == 1
    assert "my file.txt:1" in capsys.readouterr().err


def test_a_post_image_header_without_the_pinned_prefix_refuses(monkeypatch, tmp_path):
    diff = (
        "diff --git a/fixture.txt b/fixture.txt\n"
        "--- fixture.txt\n"
        "+++ fixture.txt\n"
        "@@ -0,0 +1,1 @@\n"
        f"+{EMAIL}\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert _local(monkeypatch, tmp_path) == 2


def test_a_mnemonic_prefixed_post_image_header_refuses(monkeypatch, tmp_path):
    diff = (
        "diff --git a/fixture.txt i/fixture.txt\n"
        "--- w/fixture.txt\n"
        "+++ i/fixture.txt\n"
        "@@ -0,0 +1,1 @@\n"
        f"+{EMAIL}\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert _local(monkeypatch, tmp_path) == 2


def test_a_post_image_header_quoted_on_only_one_side_refuses(monkeypatch, tmp_path):
    diff = (
        "diff --git a/fixture.txt b/fixture.txt\n"
        "--- a/fixture.txt\n"
        '+++ "b/fixture.txt\n'
        "@@ -0,0 +1,1 @@\n"
        f"+{EMAIL}\n"
    )
    _stub_git(monkeypatch, diff=diff)
    assert _local(monkeypatch, tmp_path) == 2


def test_a_commit_message_line_with_an_email_is_blocked_without_echoing_it(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, diff="")
    assert _local(monkeypatch, tmp_path, message=f"fix a thing\n\n{EMAIL}") == 1
    err = capsys.readouterr().err
    assert "commit-msg:3" in err
    assert EMAIL not in err


def test_parse_bullet_backtick_and_alternation():
    text = "- `foo` / `baz` → bar\nsome unrelated prose line\n"
    assert no_leaks.parse_banned_names(text) == [
        no_leaks.BannedName(token="foo", replacement="bar"),
        no_leaks.BannedName(token="baz", replacement="bar"),
    ]


def test_a_bare_mapping_with_no_bullet_parses():
    assert no_leaks.parse_banned_names("foo → bar\n") == [no_leaks.BannedName(token="foo", replacement="bar")]


def test_a_prose_line_without_an_arrow_is_ignored():
    assert no_leaks.parse_banned_names("no arrow on this line\n") == []


def test_a_prose_line_does_not_stop_a_later_mapping_from_parsing():
    text = "no arrow on this line\nfoo → bar\n"
    assert no_leaks.parse_banned_names(text) == [no_leaks.BannedName(token="foo", replacement="bar")]


def test_an_empty_replacement_does_not_stop_a_later_mapping_from_parsing():
    text = "foo →\nbaz → qux\n"
    assert no_leaks.parse_banned_names(text) == [no_leaks.BannedName(token="baz", replacement="qux")]


def test_load_banned_names_unset_returns_empty():
    assert no_leaks.load_banned_names("") == []


def test_load_banned_names_missing_file_returns_empty(tmp_path):
    assert no_leaks.load_banned_names(str(tmp_path / "missing.txt")) == []


def test_load_banned_names_expands_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "names.txt").write_text("- foo → bar\n")
    assert no_leaks.load_banned_names("~/names.txt") == [no_leaks.BannedName("foo", "bar")]


def test_a_staged_banned_name_is_blocked_and_suggests_the_replacement(monkeypatch, tmp_path, capsys, banned_config):
    _stub_git(monkeypatch, diff=_diff("fixture.txt", "the foo setting"))
    assert _local(monkeypatch, tmp_path, config=banned_config) == 1
    err = capsys.readouterr().err
    assert 'use "bar"' in err
    assert "the foo setting" not in err


def test_a_banned_name_match_is_whole_word(monkeypatch, tmp_path, banned_config):
    _stub_git(monkeypatch, diff=_diff("fixture.txt", "a food critic"))
    assert _local(monkeypatch, tmp_path, config=banned_config) == 0


def test_an_email_is_blocked_even_with_a_banned_names_file_configured(monkeypatch, tmp_path, banned_config):
    _stub_git(monkeypatch, diff=_diff("fixture.txt", EMAIL))
    assert _local(monkeypatch, tmp_path, config=banned_config) == 1


def test_a_banned_name_in_the_message_being_written_is_blocked(monkeypatch, tmp_path, capsys, banned_config):
    _stub_git(monkeypatch, diff="")
    assert _local(monkeypatch, tmp_path, message="mentions foo here", config=banned_config) == 1
    err = capsys.readouterr().err
    assert "commit-msg:1" in err
    assert 'use "bar"' in err


def test_banned_names_file_loads_from_mutation_gate_toml(tmp_path):
    (tmp_path / ".mutation-gate.toml").write_text('banned_names_file = "/outside/banned-names.txt"\n')
    assert Config.load(tmp_path).banned_names_file == "/outside/banned-names.txt"


def test_a_banned_names_file_that_parses_to_no_mapping_refuses(monkeypatch, tmp_path):
    empty_file = tmp_path.parent / f"{tmp_path.name}-empty.txt"
    empty_file.write_text("just prose, no mappings here\n")
    config = Config(banned_names_file=str(empty_file))
    _stub_git(monkeypatch, diff=_diff("fixture.txt", "plain prose line"))
    assert _local(monkeypatch, tmp_path, config=config) == 2
    empty_file.unlink()


def test_a_missing_banned_names_file_skips_that_check_only(monkeypatch, tmp_path):
    config = Config(banned_names_file=str(tmp_path / "missing.toml"))
    _stub_git(monkeypatch, diff=_diff("fixture.txt", "the foo setting"))
    assert _local(monkeypatch, tmp_path, config=config) == 0

    _stub_git(monkeypatch, diff=_diff("fixture.txt", EMAIL))
    assert _local(monkeypatch, tmp_path, config=config) == 1


def test_an_unset_banned_names_file_still_blocks_the_generic_scan(monkeypatch, tmp_path):
    _stub_git(monkeypatch, diff=_diff("fixture.txt", EMAIL))
    assert _local(monkeypatch, tmp_path) == 1


_DIFF_ARGS = ("diff", "-U0", "--no-color", "--no-renames", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/")


def test_local_form_uses_the_staged_index(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch)
    _local(monkeypatch, tmp_path)
    assert (*_DIFF_ARGS, "--cached") in calls


def test_range_form_diffs_the_given_range_and_walks_its_commit_messages(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch)
    _range(monkeypatch, tmp_path)
    assert (*_DIFF_ARGS, "base..HEAD") in calls
    assert ("log", "-z", "base..HEAD", "--pretty=format:%H%x1f%B") in calls


def test_range_form_blocks_a_banned_name_in_a_ranged_commit_message(monkeypatch, tmp_path, capsys, banned_config):
    log = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\x1fmentions foo in the message\n\0"
    _stub_git(monkeypatch, log=log)
    assert _range(monkeypatch, tmp_path, config=banned_config) == 1
    err = capsys.readouterr().err
    assert "deadbeefdead:1" in err
    assert 'use "bar"' in err


def test_range_form_skips_an_empty_log_record_without_dropping_later_ones(monkeypatch, tmp_path, capsys, banned_config):
    log = "\0deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\x1fmentions foo in the message\n\0"
    _stub_git(monkeypatch, log=log)
    assert _range(monkeypatch, tmp_path, config=banned_config) == 1
    assert "deadbeefdead:1" in capsys.readouterr().err


def test_local_form_refuses_with_no_msgfile_and_no_range(monkeypatch, tmp_path):
    _stub_git(monkeypatch)
    monkeypatch.setattr(no_leaks, "discover", lambda: _repo(tmp_path))
    assert cli.main(["no-leaks"]) == 2


def test_a_failing_diff_refuses(monkeypatch, tmp_path):
    def boom(*args, cwd=None):
        raise GateError("git diff: fatal")

    monkeypatch.setattr(no_leaks, "git", boom)
    monkeypatch.setattr(no_leaks, "discover", lambda: _repo(tmp_path))
    assert _local(monkeypatch, tmp_path) == 2
