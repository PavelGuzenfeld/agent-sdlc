"""Decisions 16, 34, 35 of #103 (#108): a path segment a diff adds, extension
stripped, goes through the vocabulary and the `NOUN+` mold, or the `type` mold
when a file stem matches a class it declares. Vendored core lists exempt a segment."""

from __future__ import annotations

import fnmatch
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import mutants, vocabulary, vocabulary_check, vocabulary_molds, waivers
from .repo import GateError, Repo, git

CHECK = "vocabulary-path"


def _core_path_table() -> dict:
    with vocabulary.CORE_PATH.open("rb") as fh:
        return tomllib.load(fh).get("path", {})


_TABLE = _core_path_table()
EXEMPT_FILES = frozenset(_TABLE.get("exempt_files", []))
EXEMPT_PATTERNS = tuple(re.compile(p) for p in _TABLE.get("exempt_patterns", []))
EXEMPT_PATH_PATTERNS = tuple(re.compile(p) for p in _TABLE.get("exempt_path_patterns", []))
TOOL_DICTATED_FILES = frozenset(_TABLE.get("tool_dictated_files", []))
TOOL_DICTATED_GLOBS = tuple(_TABLE.get("tool_dictated_globs", []))


@dataclass(frozen=True)
class Finding:
    file: str
    segment: str
    kind: str
    name: str
    rule: str
    detail: str
    suggestion: str


_WORD_FAULT_RULES = frozenset({
    vocabulary_check.RULE_UNKNOWN_WORD, vocabulary_check.RULE_VAGUE_WORD,
    vocabulary_check.RULE_REJECTED_SYNONYM, vocabulary_check.RULE_FUNCTION_WORD,
    vocabulary_check.RULE_SYMBOL_SCOPE,
})


def _matches_any(name: str, patterns: tuple[re.Pattern, ...]) -> bool:
    return any(p.search(name) for p in patterns)


def _fully_exempt(name: str) -> bool:
    return (
        name in EXEMPT_FILES
        or name in TOOL_DICTATED_FILES
        or any(fnmatch.fnmatch(name, glob) for glob in TOOL_DICTATED_GLOBS)
        or _matches_any(name, EXEMPT_PATTERNS)
    )


def added_paths(repo: Repo, staged: bool) -> list[str]:
    args = ["diff", "--name-only", "-z", "--no-renames", "--diff-filter=A"]
    if staged:
        args.append("--cached")
    out = git(*args, cwd=repo.root)
    return sorted(p for p in out.split("\0") if p)


def _pre_existing_dirs(repo: Repo, staged: bool, added: frozenset[str]) -> frozenset[str]:
    """Directory prefixes tracked before this diff, `added` dropped first: `git
    add -N` seeds an index entry for the file itself and `ls-files` lists it too."""
    try:
        out = git("ls-tree", "-r", "--name-only", "HEAD", cwd=repo.root) if staged \
            else git("ls-files", cwd=repo.root)
    except GateError:
        return frozenset()
    dirs: set[str] = set()
    root = PurePosixPath(".")
    for rel in out.splitlines():
        if rel in added:
            continue
        for parent in PurePosixPath(rel).parents:
            if parent != root:
                dirs.add(parent.as_posix())
    return frozenset(dirs)


def _declared_type_words(repo: Repo, rel: str) -> list[list[str]]:
    lang = mutants.language_of(rel)
    path = repo.root / rel
    if lang not in vocabulary_check.SUFFIX or not path.exists():
        return []
    mutants.require_ast_grep()
    out: list[list[str]] = []
    for declared in vocabulary_check.declarations(path, lang):
        _, kind, name = declared[:3]
        if kind == "type":
            out.append(vocabulary_check.words(name))
    return out


def _kind_for_file(repo: Repo, rel: str, stem: str) -> str:
    folded = [w.lower() for w in vocabulary_check.words(stem)]
    for words in _declared_type_words(repo, rel):
        if [w.lower() for w in words] == folded:
            return "type"
    return "namespace"


def _findings_for(
    repo: Repo, dictionary, catalogue, rel: str, existing_dirs: frozenset[str],
    wvs: list[waivers.Waiver],
) -> list[Finding]:
    segments = rel.split("/")
    out: list[Finding] = []
    prefix_parts: list[str] = []
    for index, segment in enumerate(segments, start=1):
        is_last = index == len(segments)
        if not is_last:
            prefix_parts.append(segment)
            if _matches_any(segment, EXEMPT_PATH_PATTERNS):
                break
            if "/".join(prefix_parts) in existing_dirs:
                continue
        if is_last and _fully_exempt(segment):
            continue
        if _matches_any(segment, EXEMPT_PATTERNS):
            continue
        if waivers.finding_waived(wvs, CHECK, rel, line=index):
            continue
        stem = Path(segment).stem if is_last else segment
        suffix = Path(segment).suffix if is_last else ""
        kind = _kind_for_file(repo, rel, stem) if is_last else "namespace"
        faults = vocabulary_check.judge(dictionary, kind, stem, catalogue)
        if any(rule in _WORD_FAULT_RULES for rule, _, _ in faults):
            resolved = [w for w in vocabulary_check.words(stem)
                       if vocabulary_molds.tags(dictionary, w)]
            misfit = resolved and vocabulary_molds.fit(dictionary, catalogue, kind, stem, resolved)
            if misfit:
                detail, _ = misfit
                faults = [*faults, (vocabulary_check.RULE_MOLD, detail, "")]
        for rule, detail, suggestion in faults:
            if rule == vocabulary_check.RULE_VAGUE_WORD:
                renamed = suggestion
            else:
                renamed = f"{suggestion}{suffix}" if suggestion else ""
            out.append(Finding(rel, segment, kind, stem, rule, detail, renamed))
    return out


def check(repo: Repo, staged: bool, wvs: list[waivers.Waiver]) -> list[Finding]:
    added = [rel for rel in added_paths(repo, staged)
             if not any(rel.startswith(p) for p in repo.config.exclude_paths)]
    if not added:
        return []
    dictionary = vocabulary.load(repo.root, repo.config.vocabulary)
    catalogue = vocabulary_molds.narrow(repo.config.vocabulary_molds)
    existing_dirs = _pre_existing_dirs(repo, staged, frozenset(added))
    out: list[Finding] = []
    for rel in added:
        out.extend(_findings_for(repo, dictionary, catalogue, rel, existing_dirs, wvs))
    return out


def describe(f: Finding) -> str:
    text = f"{f.file}: {f.kind} `{f.name}` — {f.detail}"
    return f"{text} — try `{f.suggestion}`" if f.suggestion else text


def suggest(repo: Repo, f: Finding) -> str:
    return (
        "Rename it with a dictionary word in the NOUN+ mold (`mutation-gate vocabulary "
        f"lookup <word>`), add a [[concept]] to {repo.config.vocabulary}, or record a "
        f"waiver in {waivers.path(repo)}:\n"
        "[[waiver]]\n"
        f'check = "{CHECK}"\n'
        f'file = "{f.file}"\n'
        'reason = "REPLACE ME — who outside this repo dictates this name"\n'
    )
