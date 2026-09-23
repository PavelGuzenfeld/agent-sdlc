"""Entry point. Two modes: --staged for pre-commit, --worktree for the Stop hook.

Exit 0 = pass, 1 = blocked, 2 = refused (misconfiguration; nothing was measured).
A refusal is never a pass — the failure mode of a broken harness is false
reassurance. Exception: a lock held by a concurrent run exits 0 for
--worktree only — the Stop hook is best-effort, and a live gate on the same
repo is a reason to skip, not a refusal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import adversary, commit_msg, coverage_map, diff_discipline, model_vv, mutants, no_comments, no_new_docs, rules, runner, token, vocabulary, vocabulary_check, waivers
from .repo import CACHE_ROOT, CONFIG_NAME, GateError, discover, skip_reason


TIMEOUT_FACTOR = 6.0


def _emit(line: str = "") -> None:
    print(line, file=sys.stderr)


def _write_report(repo, name: str, text: str) -> Path:
    """A green pre-commit hook only surfaces its output on failure (#62), so the
    adversary/blind-pass reports need a durable home besides the terminal."""
    path = CACHE_ROOT / repo.key / "reports" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _warn_stale_waivers(repo, rel: str, wvs) -> None:
    """Say when a recorded decision stopped applying. Reports, never blocks: a stale
    waiver already fails safe, since its mutant comes back as a survivor. What it does
    not do without this is say why (dotfiles#88).

    Best-effort by construction. It costs a second generator pass over the whole file,
    and anything that goes wrong in it must leave the gate's verdict untouched — a
    warning that can fail a run is worse than no warning.
    """
    if not any(w.file == rel and w.line and not w.uncovered for w in wvs):
        return
    try:
        whole = {rel: set(range(1, len((repo.root / rel).read_text().splitlines()) + 1))}
        every = mutants.generate(repo.root, whole, repo.config.language)
    except (OSError, GateError, ValueError):
        return
    for w in waivers.stale(wvs, rel, every):
        _emit(f"  {rel}: waiver at line {w.line} column {w.column} matches no mutant "
              f"— stale after an edit above it? ({w.old!r} => {w.new!r})")


def _gate_file(
    repo, rel: str, lines: set[int], wvs, on_demand: bool = False
) -> tuple[bool, list, list]:
    """Returns (blocked, survivors, candidate test paths) for one changed file."""
    cands = coverage_map.candidates(repo, rel)
    source_blob = coverage_map.blob_hashes(repo, [repo.root / rel])
    fp = token.fingerprint(source_blob[0] if source_blob else "",
                           coverage_map.blob_hashes(repo, cands))

    # --file is the acceptance run: whoever asked for the whole file measured
    # wants it measured, token or not (#24).
    if not on_demand and token.is_valid(repo, rel, fp):
        _emit(f"  {rel}: already gated by the other hook (token valid)")
        return False, [], cands

    if not cands:
        waiver = waivers.uncovered_waived(wvs, rel)
        if waiver:
            _emit(f"  {rel}: no covering tests — waived ({waiver.reason})")
            token.write(repo, rel, fp, "uncovered-waived")
            return False, [], []
        _emit(f"  {rel}: BLOCKED — no covering tests")
        _emit("    add to " + str(waivers.path(repo)) + ":")
        _emit("    " + waivers.suggest_uncovered(rel).replace("\n", "\n    "))
        return True, [], []

    language = mutants.language_of(rel) or repo.config.language
    lang_cfg = repo.config.for_language(language)

    generated = mutants.generate(repo.root, {rel: lines}, repo.config.language)
    _warn_stale_waivers(repo, rel, wvs)
    if not generated:
        _emit(f"  {rel}: no mutable sites on the changed lines")
        token.write(repo, rel, fp, "no-mutants")
        return False, [], cands

    cover = coverage_map.covering_tests(repo, rel, cands, fp)
    all_tests = [str(p.relative_to(repo.root)) for p in cands]

    baseline = runner.baseline_green(repo, all_tests, lang_cfg.test_command)
    configured = repo.config.mutant_timeout
    timeout = configured if configured else max(30.0, baseline * TIMEOUT_FACTOR)
    source = "configured" if configured else "from baseline"
    _emit(f"  {rel}: baseline {baseline:.1f}s, per-mutant timeout {timeout:.0f}s ({source})")

    survivors, blocked, timed_out = [], False, 0
    total = len(generated)
    for index, m in enumerate(generated, 1):
        tests = sorted({t.split("|")[0] for t in cover.get(m.line, [])})
        selected = all_tests if not tests else tests
        # Progress on every mutant: a silent run is indistinguishable from a hang.
        _emit(f"  [{index}/{total}] {rel}:{m.line}:{m.column} {m.old} => {m.new}")
        result = runner.classify(repo, m, selected, lang_cfg.test_command, timeout)
        if result.verdict in (runner.KILLED, runner.KILLED_TIMEOUT):
            timed_out += result.verdict == runner.KILLED_TIMEOUT
            continue
        waiver = waivers.waived(wvs, m)
        if waiver:
            _emit(f"  {rel}:{m.line}:{m.column} {m.old} => {m.new}  SURVIVED (waived: {waiver.reason})")
            continue
        survivors.append(m)
        blocked = True
    if timed_out:
        # Otherwise the score reads as a clean sweep and says nothing about what
        # produced it: a suite that hangs and a build that is merely slow time
        # out identically, and both are counted killed.
        _emit(f"  {rel}: {timed_out}/{total} mutant(s) timed out and were counted "
              f"KILLED — set mutant_timeout in {CONFIG_NAME} if the run is only slow")
    if not blocked:
        token.write(repo, rel, fp, "pass")
    return blocked, survivors, cands


def _stop_hook_cwd() -> Path | None:
    """The Stop hook's own process cwd is the session's launch directory, not
    wherever a Bash `cd` took the shell (#68 item 1) — the real one is the
    `cwd` field of the hook's JSON payload on stdin."""
    if sys.stdin.isatty():
        return None
    try:
        cwd = json.loads(sys.stdin.read()).get("cwd")
    except (json.JSONDecodeError, ValueError, AttributeError):
        return None
    return Path(cwd) if cwd else None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["rules"]:
        return rules.main(argv[1:])
    if argv[:1] == ["commit-msg"]:
        return commit_msg.main(argv[1:])
    if argv[:1] == ["vocabulary"]:
        return vocabulary.main(argv[1:])
    if argv[:1] == ["diff-discipline"]:
        return diff_discipline.main(argv[1:])
    if argv[:1] == ["no-new-docs"]:
        return no_new_docs.main(argv[1:])
    parser = argparse.ArgumentParser(prog="mutation-gate")
    parser.add_argument("--staged", action="store_true", help="gate the index (pre-commit)")
    parser.add_argument("--worktree", action="store_true", help="gate the working tree")
    parser.add_argument("--user-prompt", default=None, help="intent fallback for the adversary")
    parser.add_argument("--no-adversary", action="store_true")
    parser.add_argument("--file", default=None,
                        help="gate every line of one file (acceptance / on-demand)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print candidates and mutants; run no tests")
    parser.add_argument("files", nargs="*", help="ignored; pre-commit passes filenames")
    args = parser.parse_args(argv)
    staged = args.staged or not args.worktree

    try:
        repo = discover(_stop_hook_cwd() if args.worktree else None)
    except GateError as exc:
        if "not a git repository" in str(exc):
            _emit("mutation-gate skipped: not a git repository")
            return 0
        _emit(f"mutation-gate refused: {exc}")
        return 2

    reason = skip_reason(repo)
    if reason:
        _emit(f"mutation-gate skipped: {reason}")
        return 0

    # Lock before guard_clean_start: recovery restores the *other* run's backup.
    try:
        lock = runner.repo_lock(repo)
        lock.__enter__()
    except GateError as exc:
        if not staged:
            _emit(f"mutation-gate skipped: {exc}")
            return 0
        _emit(f"mutation-gate refused: {exc}")
        return 2
    try:
        return _run(repo, args, staged)
    finally:
        lock.__exit__(None, None, None)


def _run(repo, args, staged: bool) -> int:
    try:
        runner.guard_clean_start(repo)
        wvs = waivers.load(repo)
    except (GateError, ValueError) as exc:
        _emit(f"mutation-gate refused: {exc}")
        return 2

    if args.file:
        target = (repo.root / args.file)
        all_changed = {args.file: set(range(1, len(target.read_text().splitlines()) + 1))}
    else:
        all_changed = mutants.changed_lines(repo.root, staged)

    # Before mutants: nothing here runs tests, so a missing spec fails in
    # milliseconds instead of after a baseline run (#56 decision 10).
    try:
        findings = model_vv.check(repo, all_changed, wvs, staged)
    except GateError as exc:
        _emit(f"mutation-gate refused: {exc}")
        return 2
    if findings:
        _emit(f"BLOCKED: model-vv — {len(findings)} finding(s).")
        for f in findings:
            _emit(f"  {f.check:<12}{f.file}: {f.detail}")
        _emit("")
        _emit(model_vv.suggest(repo, findings[0]))
        return 1

    if repo.config.no_comments:
        comments = no_comments.check(repo, all_changed, wvs, staged)
        if comments:
            _emit(f"BLOCKED: no-comments — {len(comments)} added comment line(s).")
            for c in comments:
                _emit(f"  {c.file}:{c.line}: {c.text}")
            _emit("")
            _emit(no_comments.suggest(repo, comments[0]))
            return 1

    if repo.config.vocabulary:
        try:
            names = vocabulary_check.check(repo, all_changed, wvs)
        except GateError as exc:
            _emit(f"mutation-gate refused: {exc}")
            return 2
        if names:
            _emit(f"BLOCKED: vocabulary — {len(names)} finding(s).")
            for n in names:
                _emit(f"  {vocabulary_check.describe(n)}")
            _emit("")
            _emit(vocabulary_check.suggest(repo, names[0]))
            return 1

    if args.file:
        changed = all_changed
    else:
        changed = {}
        for f, lines in all_changed.items():
            if not mutants.language_of(f) or repo.is_test(f):
                continue
            prefix = _excluded(repo, f)
            if prefix:
                _emit(f"  {f}: not gated — {CONFIG_NAME} exclude_paths {prefix!r}")
                continue
            changed[f] = lines
    if not changed:
        _emit("mutation-gate: no gated source files in this change")
        return 0

    try:
        mutants.require_ast_grep()
    except GateError as exc:
        _emit(f"mutation-gate refused: {exc}")
        return 2

    if args.dry_run:
        for rel, lines in sorted(changed.items()):
            cands = coverage_map.candidates(repo, rel)
            gen = mutants.generate(repo.root, {rel: lines}, repo.config.language)
            _emit(f"{rel}: {len(cands)} candidate test file(s), {len(gen)} mutant(s)")
            _warn_stale_waivers(repo, rel, wvs)
            for c in cands:
                _emit(f"    test  {c.relative_to(repo.root)}")
            for m in gen:
                _emit(f"    mut   {m.line}:{m.column}: {m.old} => {m.new}")
        return 0

    _emit(f"mutation-gate: {len(changed)} changed source file(s)")
    all_survivors, all_cands, blocked = [], [], False
    try:
        for rel, lines in sorted(changed.items()):
            file_blocked, survivors, cands = _gate_file(
                repo, rel, lines, wvs, on_demand=bool(args.file)
            )
            blocked |= file_blocked
            all_survivors.extend(survivors)
            all_cands.extend(cands)
    except GateError as exc:
        _emit(f"mutation-gate refused: {exc}")
        return 2

    if blocked:
        _emit("")
        _emit(f"BLOCKED: {len(all_survivors)} mutant(s) survived with no waiver.")
        for m in all_survivors:
            _emit(f"  {m.ident}")
        if all_survivors:
            _emit("")
            _emit(f"Write the killing test, or record a waiver in {waivers.path(repo)}:")
            _emit(waivers.suggest(all_survivors[0]))
        return 1

    _emit("mutation-gate: pass")
    if not args.no_adversary and all_cands:
        intent = adversary.resolve_intent(repo, args.user_prompt)
        findings = adversary.run(sorted(set(all_cands)), intent, "")
        path = _write_report(repo, "adversary", findings)
        _emit("")
        _emit(f"── adversary (isolated; reports only, never blocks; saved to {path}) ──")
        _emit(findings)
    if not args.no_adversary and model_vv.model_changed(repo, all_changed):
        findings = model_vv.blind_pass(repo)
        path = _write_report(repo, "blind-pass", findings)
        _emit("")
        _emit(f"── blind pass (code only, no spec; reports only, never blocks; saved to {path}) ──")
        _emit(findings)
    return 0


def _excluded(repo, rel: str) -> str | None:
    return next((p for p in repo.config.exclude_paths if rel.startswith(p)), None)


if __name__ == "__main__":
    sys.exit(main())
