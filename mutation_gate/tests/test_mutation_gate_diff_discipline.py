"""Intent: #71 decision 9 — `mutation-gate diff-discipline` blocks a branch that
adds more than 40 production lines against the merge-base with the default
branch unless the branch is named `N-slug` or a branch commit message (or the
message being written) carries `#N`. Deletions, test_paths and declared V&V
artefacts do not count. `git` is stubbed — the gate's test image has none."""

from pathlib import Path

import pytest

from mutation_gate import cli, diff_discipline
from mutation_gate.repo import Config, GateError, Golden, Repo

ORIGIN_MAIN = "refs/remotes/origin/main"


def _numstat(added: dict[str, int], deleted: dict[str, int] | None = None) -> str:
    deleted = deleted or {}
    records = [f"{n}\t0\t{path}\0" for path, n in added.items()]
    records += [f"0\t{n}\t{path}\0" for path, n in deleted.items()]
    return "".join(records)


def _stub_git(monkeypatch, *, branch: str = "feature", numstat: str = "", log: str = "",
              origin_head: str | None = ORIGIN_MAIN, verifiable: set[str] = frozenset(),
              merge_base: str | None = "base0") -> list[tuple[str, ...]]:
    calls: list[tuple[str, ...]] = []

    def fake_git(*args: str, cwd=None) -> str:
        calls.append(args)
        if args[0] == "symbolic-ref":
            if origin_head is None:
                raise GateError("git symbolic-ref: not a symbolic ref")
            return origin_head + "\n"
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return branch + "\n"
        if args[:2] == ("rev-parse", "--verify"):
            if args[-1] in verifiable:
                return "f" * 40 + "\n"
            raise GateError("git rev-parse: fatal")
        if args[0] == "merge-base":
            if merge_base is None:
                raise GateError("git merge-base: fatal: Not a valid object name HEAD")
            return merge_base + "\n"
        if args[0] == "log":
            return log
        if args[0] == "diff":
            return numstat
        raise AssertionError(f"unexpected git call {args}")

    monkeypatch.setattr(diff_discipline, "git", fake_git)
    return calls


def _repo(tmp_path: Path, config: Config | None = None) -> Repo:
    return Repo(root=tmp_path, origin="", remotes=(), config=config or Config())


def _local(monkeypatch, tmp_path: Path, message: str = "plain change", config: Config | None = None) -> int:
    monkeypatch.setattr(diff_discipline, "discover", lambda cwd=None: _repo(tmp_path, config))
    msgfile = tmp_path / "MSG"
    msgfile.write_text(message)
    return cli.main(["diff-discipline", str(msgfile)])


def _range(monkeypatch, tmp_path: Path, *extra: str, config: Config | None = None) -> int:
    monkeypatch.setattr(diff_discipline, "discover", lambda cwd=None: _repo(tmp_path, config))
    return cli.main(["diff-discipline", "--range", "base0..HEAD", *extra])


def test_limit_is_forty():
    assert diff_discipline.LINE_LIMIT == 40


def test_forty_one_production_lines_without_a_ticket_block(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 20, "src/b.py": 21}))
    assert _local(monkeypatch, tmp_path) == 1
    err = capsys.readouterr().err
    assert "41 added production line(s)" in err
    assert "limit 40" in err
    assert "src/a.py: 20" in err
    assert "src/b.py: 21" in err


def test_forty_production_lines_without_a_ticket_pass(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 20, "src/b.py": 20}))
    assert _local(monkeypatch, tmp_path) == 0


def test_block_says_how_to_pass(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 41}))
    _local(monkeypatch, tmp_path)
    err = capsys.readouterr().err
    assert "open a ticket" in err
    assert "N-slug" in err
    assert "#N" in err


def test_block_names_what_was_excluded(monkeypatch, tmp_path, capsys):
    config = Config(model_test_paths=["model_tests"])
    _stub_git(monkeypatch, numstat=_numstat(
        {"src/a.py": 41, "tests/test_a.py": 7, "model_tests/harness.py": 5}
    ))
    assert _local(monkeypatch, tmp_path, config=config) == 1
    err = capsys.readouterr().err
    assert "excluded: 7 under test_paths, 5 in V&V artefacts" in err


def test_deleted_lines_do_not_count(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 40}, deleted={"src/old.py": 300}))
    assert _local(monkeypatch, tmp_path) == 0


def test_lines_under_test_paths_do_not_count(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"tests/test_a.py": 41}))
    assert _local(monkeypatch, tmp_path) == 0


def test_configured_test_paths_are_honoured_not_the_default(monkeypatch, tmp_path):
    config = Config(test_paths=["spec"])
    _stub_git(monkeypatch, numstat=_numstat({"tests/test_a.py": 41}))
    assert _local(monkeypatch, tmp_path, config=config) == 1


def test_a_file_merely_prefixed_by_a_test_dir_name_counts(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"tests_helper.py": 41}))
    assert _local(monkeypatch, tmp_path) == 1


def test_model_test_paths_are_vv_artefacts(monkeypatch, tmp_path):
    config = Config(model_test_paths=["model_tests"])
    _stub_git(monkeypatch, numstat=_numstat({"model_tests/harness.py": 41}))
    assert _local(monkeypatch, tmp_path, config=config) == 0


def test_golden_source_and_artifact_are_vv_artefacts(monkeypatch, tmp_path):
    config = Config(golden=[Golden(source="model/cv.sympy.py", artifact="model/cv_fq.json")])
    _stub_git(monkeypatch, numstat=_numstat({"model/cv.sympy.py": 21, "model/cv_fq.json": 20}))
    assert _local(monkeypatch, tmp_path, config=config) == 0


def test_a_file_model_spec_is_a_vv_artefact(monkeypatch, tmp_path):
    config = Config(model_spec="docs/model-spec.md")
    _stub_git(monkeypatch, numstat=_numstat({"docs/model-spec.md": 41}))
    assert _local(monkeypatch, tmp_path, config=config) == 0


def test_an_issue_model_spec_excludes_no_file(monkeypatch, tmp_path):
    config = Config(model_spec="issue:24")
    _stub_git(monkeypatch, numstat=_numstat({"issue:24": 41}))
    assert _local(monkeypatch, tmp_path, config=config) == 1


def test_model_paths_are_production_code_not_artefacts(monkeypatch, tmp_path):
    config = Config(model_paths=["model"])
    _stub_git(monkeypatch, numstat=_numstat({"model/filter.py": 41}))
    assert _local(monkeypatch, tmp_path, config=config) == 1


def test_a_binary_file_is_skipped(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 40}) + "-\t-\tassets/logo.png\0")
    assert _local(monkeypatch, tmp_path) == 0


def test_a_binary_file_does_not_hide_the_files_after_it(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat="-\t-\tassets/logo.png\0" + _numstat({"src/a.py": 41}))
    assert _local(monkeypatch, tmp_path) == 1


def test_an_empty_record_does_not_hide_the_files_after_it(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat="\0" + _numstat({"src/a.py": 41}))
    assert _local(monkeypatch, tmp_path) == 1


def test_a_tab_in_a_path_keeps_the_whole_path(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, numstat="41\t0\tsrc/odd\tname.py\0")
    assert _local(monkeypatch, tmp_path) == 1
    assert "src/odd\tname.py: 41" in capsys.readouterr().err


def test_branch_named_n_slug_passes_without_counting(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch, branch="12-feature", numstat=_numstat({"src/a.py": 500}))
    assert _local(monkeypatch, tmp_path) == 0
    assert not any(c[0] == "diff" for c in calls)


def test_branch_prefix_needs_the_dash(monkeypatch, tmp_path):
    _stub_git(monkeypatch, branch="12feature", numstat=_numstat({"src/a.py": 41}))
    assert _local(monkeypatch, tmp_path) == 1


def test_a_dashed_non_numeric_branch_is_not_a_ticket_prefix(monkeypatch, tmp_path):
    _stub_git(monkeypatch, branch="feature-x", numstat=_numstat({"src/a.py": 41}))
    assert _local(monkeypatch, tmp_path) == 1


def test_type_slash_n_slug_branch_is_not_a_ticket_prefix(monkeypatch, tmp_path):
    _stub_git(monkeypatch, branch="fix/12-feature", numstat=_numstat({"src/a.py": 41}))
    assert _local(monkeypatch, tmp_path) == 1


def test_hash_n_in_an_earlier_branch_commit_passes(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 41}), log="first half\n\nRefs #12\n\nsecond half\n")
    assert _local(monkeypatch, tmp_path) == 0


def test_hash_n_in_the_message_being_written_passes(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 41}))
    assert _local(monkeypatch, tmp_path, message="second half for #12") == 0


def test_hash_without_digits_is_not_a_reference(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 41}), log="see #abc and # 12\n")
    assert _local(monkeypatch, tmp_path, message="fix # thing") == 1


def test_hash_n_only_in_the_commit_v_diff_below_the_scissors_does_not_pass(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 41}))
    message = (
        "second half\n"
        "\n"
        "# On branch feature\n"
        "# ------------------------ >8 ------------------------\n"
        "diff --git a/x.py b/x.py\n"
        "+issue = '#12'\n"
    )
    assert _local(monkeypatch, tmp_path, message=message) == 1


def test_local_form_counts_the_index_against_the_merge_base(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch, merge_base="abc123")
    _local(monkeypatch, tmp_path)
    assert ("diff", "--numstat", "-z", "--no-renames", "--cached", "abc123") in calls
    assert ("log", "--format=%B", "abc123..HEAD") in calls


def test_local_form_prefers_origin_head_as_the_default_branch(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch, origin_head=ORIGIN_MAIN, verifiable={"origin/master", "main"})
    _local(monkeypatch, tmp_path)
    assert ("merge-base", ORIGIN_MAIN, "HEAD") in calls


@pytest.mark.parametrize(
    "verifiable, chosen",
    [
        ({"origin/main", "origin/master", "main", "master"}, "origin/main"),
        ({"origin/master", "main", "master"}, "origin/master"),
        ({"main", "master"}, "main"),
        ({"master"}, "master"),
    ],
)
def test_default_branch_fallback_order_without_origin_head(monkeypatch, tmp_path, verifiable, chosen):
    calls = _stub_git(monkeypatch, origin_head=None, verifiable=verifiable)
    _local(monkeypatch, tmp_path)
    assert ("merge-base", chosen, "HEAD") in calls


def test_no_default_branch_skips_with_a_reason_instead_of_blocking(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, origin_head=None, verifiable=set(), numstat=_numstat({"src/a.py": 500}))
    assert _local(monkeypatch, tmp_path) == 0
    assert "diff-discipline skipped: no default branch" in capsys.readouterr().err


def test_no_merge_base_skips_with_a_reason_instead_of_blocking(monkeypatch, tmp_path, capsys):
    _stub_git(monkeypatch, merge_base=None, numstat=_numstat({"src/a.py": 500}))
    assert _local(monkeypatch, tmp_path) == 0
    assert "diff-discipline skipped: no merge-base" in capsys.readouterr().err


def test_a_failing_diff_refuses(monkeypatch, tmp_path):
    def boom(*args, cwd=None):
        if args[0] == "diff":
            raise GateError("git diff: fatal")
        return "refs/remotes/origin/main\n" if args[0] == "symbolic-ref" else "feature\n"

    monkeypatch.setattr(diff_discipline, "git", boom)
    assert _local(monkeypatch, tmp_path) == 2


def test_local_form_refuses_with_no_msgfile_and_no_range(monkeypatch, tmp_path):
    _stub_git(monkeypatch)
    monkeypatch.setattr(diff_discipline, "discover", lambda cwd=None: _repo(tmp_path))
    assert cli.main(["diff-discipline"]) == 2


def test_local_form_refuses_on_an_unreadable_msgfile(monkeypatch, tmp_path):
    _stub_git(monkeypatch)
    monkeypatch.setattr(diff_discipline, "discover", lambda cwd=None: _repo(tmp_path))
    assert cli.main(["diff-discipline", str(tmp_path / "missing")]) == 2


def test_range_form_blocks_forty_one_lines_and_passes_forty(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 41}))
    assert _range(monkeypatch, tmp_path) == 1
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 40}))
    assert _range(monkeypatch, tmp_path) == 0


def test_range_form_applies_the_same_exclusions(monkeypatch, tmp_path):
    config = Config(model_test_paths=["model_tests"])
    _stub_git(monkeypatch, numstat=_numstat(
        {"src/a.py": 40, "tests/test_a.py": 41, "model_tests/harness.py": 41}, deleted={"src/old.py": 41}
    ))
    assert _range(monkeypatch, tmp_path, config=config) == 0


def test_range_form_diffs_and_logs_the_given_range(monkeypatch, tmp_path):
    calls = _stub_git(monkeypatch)
    _range(monkeypatch, tmp_path)
    assert ("diff", "--numstat", "-z", "--no-renames", "base0..HEAD") in calls
    assert ("log", "--format=%B", "base0..HEAD") in calls
    assert not any(c[0] in ("merge-base", "symbolic-ref") for c in calls)


def test_range_form_takes_the_branch_name_from_the_flag_when_head_is_detached(monkeypatch, tmp_path):
    _stub_git(monkeypatch, branch="HEAD", numstat=_numstat({"src/a.py": 41}))
    assert _range(monkeypatch, tmp_path, "--branch", "12-feature") == 0
    assert _range(monkeypatch, tmp_path, "--branch", "feature") == 1


def test_range_form_reads_the_checked_out_branch_without_the_flag(monkeypatch, tmp_path):
    _stub_git(monkeypatch, branch="12-feature", numstat=_numstat({"src/a.py": 41}))
    assert _range(monkeypatch, tmp_path) == 0


def test_range_form_passes_on_hash_n_in_a_range_commit(monkeypatch, tmp_path):
    _stub_git(monkeypatch, numstat=_numstat({"src/a.py": 41}), log="squash (#77)\n")
    assert _range(monkeypatch, tmp_path) == 0


def test_range_form_refuses_when_git_fails(monkeypatch, tmp_path):
    def boom(*args, cwd=None):
        raise GateError("git log: bad range")

    monkeypatch.setattr(diff_discipline, "git", boom)
    monkeypatch.setattr(diff_discipline, "discover", lambda cwd=None: _repo(tmp_path))
    assert cli.main(["diff-discipline", "--range", "bad..bad"]) == 2
