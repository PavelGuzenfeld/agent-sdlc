"""Decisions 2, 11, 15, 22 and 34 of #103 as a check (#105): a name a diff declares
is built from dictionary words, spells private as a trailing `_`, and takes a
`[symbol]` word only as a local or parameter. References are never checked."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import mutants, vocabulary, vocabulary_molds, waivers
from .repo import GateError, Repo, git

CHECK = "vocabulary"
SUFFIX = {"python": ".py", "cpp": ".cpp", "typescript": ".ts", "tsx": ".tsx", "gdscript": ".gd"}
SYMBOL_KINDS = ("local", "parameter")
UNKNOWN_DETAIL = "is not in the dictionary"
GDSCRIPT_CONFIG = "sgconfig.yml"
GDSCRIPT_MISSING = ("gdscript vocabulary skipped: no " + GDSCRIPT_CONFIG + " — install the "
                    "parser with bin/install-gdscript-parser and commit one")


def _emit(line: str) -> None:
    print(line, file=sys.stderr)


def _decorated(regex: str) -> dict:
    return {"inside": {"kind": "decorated_definition",
                       "has": {"kind": "decorator", "regex": regex}}}


_END = {"stopBy": "end"}
_LEFT_OF_ASSIGNMENT = {"inside": {"kind": "assignment", "field": "left"}}
_IN_FUNCTION = {"inside": {"kind": "function_definition", **_END}}
_IN_CLASS = {"inside": {"kind": "class_definition", **_END}}
_IN_ENUM = {"inside": {"kind": "class_definition", **_END, "has": {
    "field": "superclasses", "regex": r"\b(Int|Str)?(Enum|Flag)\b"}}}
_OVERRIDDEN = _decorated(r"^@(\w+\.)?override$")
_PROPERTY = _decorated(r"^@(\w+\.)*(cached_)?property$")
_SETTER = _decorated(r"\.(setter|deleter)$")
_METHOD = {"inside": {"kind": "block", "stopBy": {"not": {"kind": "decorated_definition"}},
                      "inside": {"kind": "class_definition"}}}
_INCLUDE_GUARD = {"all": [{"not": {"has": {"field": "value", "kind": "preproc_arg"}}},
                          {"inside": {"kind": "preproc_ifdef"}}, {"nthChild": 2}]}
_THROUGH_DECLARATOR_WRAPPERS = {"stopBy": {"not": {"any": [
    {"kind": "pointer_declarator"}, {"kind": "reference_declarator"}, {"kind": "array_declarator"},
]}}}
_CPP_DECLARATOR = {"inside": {"any": [{"kind": "init_declarator"}, {"kind": "declaration"}],
                              "field": "declarator", **_THROUGH_DECLARATOR_WRAPPERS}}
_IN_BLOCK = {"inside": {"kind": "compound_statement", **_END}}

RULES: dict[str, dict[str, dict]] = {
    "python": {
        "function": {"kind": "identifier", "inside": {
            "kind": "function_definition", "field": "name",
            "not": {"any": [_OVERRIDDEN, _PROPERTY, _SETTER, _METHOD]}}},
        "method": {"kind": "identifier", "inside": {
            "kind": "function_definition", "field": "name", **_METHOD,
            "not": {"any": [_OVERRIDDEN, _PROPERTY, _SETTER]}}},
        "property": {"kind": "identifier", "inside": {
            "kind": "function_definition", "field": "name", **_PROPERTY}},
        "enumerator": {"kind": "identifier", "all": [
            _LEFT_OF_ASSIGNMENT, _IN_ENUM, {"not": _IN_FUNCTION}]},
        "type": {"kind": "identifier", "inside": {"kind": "class_definition", "field": "name"}},
        "parameter": {"kind": "identifier", "any": [
            {"inside": {"kind": "parameters"}},
            {"inside": {"kind": "typed_parameter"}},
            {"inside": {"kind": "default_parameter", "field": "name"}},
            {"inside": {"kind": "typed_default_parameter", "field": "name"}},
            {"inside": {"kind": "list_splat_pattern", "inside": {"kind": "parameters"}}},
            {"inside": {"kind": "dictionary_splat_pattern", "inside": {"kind": "parameters"}}},
        ]},
        "local": {"kind": "identifier", "all": [_LEFT_OF_ASSIGNMENT, _IN_FUNCTION]},
        "field": {"kind": "identifier", "any": [
            {"all": [_LEFT_OF_ASSIGNMENT, _IN_CLASS, {"not": {"any": [_IN_FUNCTION, _IN_ENUM]}}]},
            {"inside": {"kind": "attribute", "field": "attribute",
                        "has": {"field": "object", "regex": "^(self|cls)$"},
                        **_LEFT_OF_ASSIGNMENT}},
        ]},
        "variable": {"kind": "identifier", **_LEFT_OF_ASSIGNMENT,
                     "not": {"any": [_IN_FUNCTION, _IN_CLASS]}},
    },
    "cpp": {
        "method": {"kind": "field_identifier", "inside": {
            "kind": "function_declarator", "field": "declarator",
            "not": {"has": {"kind": "virtual_specifier"}}}},
        "function": {"kind": "identifier", "any": [
            {"inside": {"kind": "function_declarator", "field": "declarator"}},
            {"inside": {"kind": "preproc_function_def", "field": "name"}},
        ]},
        "constant": {"kind": "identifier", "inside": {
            "kind": "preproc_def", "field": "name", "not": _INCLUDE_GUARD}},
        "field": {"kind": "field_identifier", "inside": {"kind": "field_declaration", **_END},
                  "not": {"inside": {"any": [{"kind": "function_declarator"},
                                             {"kind": "field_expression"}], **_END}}},
        "parameter": {"kind": "identifier", "inside": {
            "any": [{"kind": "parameter_declaration"}, {"kind": "optional_parameter_declaration"}],
            "field": "declarator", **_END}},
        "local": {"kind": "identifier", "all": [_CPP_DECLARATOR, _IN_BLOCK]},
        "variable": {"kind": "identifier", **_CPP_DECLARATOR, "not": _IN_BLOCK},
        "type": {"kind": "type_identifier", "inside": {"field": "name", "any": [
            {"kind": "class_specifier"}, {"kind": "struct_specifier"},
            {"kind": "enum_specifier"}, {"kind": "alias_declaration"},
        ]}},
        "namespace": {"kind": "namespace_identifier",
                      "inside": {"kind": "namespace_definition", "field": "name"}},
        "enumerator": {"kind": "identifier", "inside": {"kind": "enumerator", "field": "name"}},
    },
}

_TS_PASCAL = {"regex": "^[A-Z]"}
_TS_FUNCTION_NAME = {"any": [
    {"kind": "identifier", "inside": {"kind": "function_declaration", "field": "name"}},
    {"kind": "identifier", "inside": {
        "kind": "variable_declarator", "field": "name",
        "has": {"field": "value", "any": [{"kind": "arrow_function"}, {"kind": "function_expression"}]}}},
]}
_TS_TYPE_NAME = {"any": [
    {"kind": "type_identifier", "inside": {"kind": "class_declaration", "field": "name"}},
    {"kind": "type_identifier", "inside": {"kind": "interface_declaration", "field": "name"}},
    {"kind": "type_identifier", "inside": {"kind": "type_alias_declaration", "field": "name"}},
]}
_TS_GETTER = {"kind": "property_identifier", "inside": {
    "kind": "method_definition", "field": "name", "regex": r"^get\b"}}
_TS_FIELD_NAME = {"any": [
    {"kind": "property_identifier", "inside": {"kind": "public_field_definition", "field": "name"}},
    {"kind": "private_property_identifier", "inside": {"kind": "public_field_definition", "field": "name"}},
]}
_TS_PRIVATE_FIELD_NAME = {"any": [
    {"kind": "private_property_identifier", "inside": {"kind": "public_field_definition", "field": "name"}},
    {"kind": "property_identifier", "inside": {
        "kind": "public_field_definition", "field": "name",
        "has": {"kind": "accessibility_modifier", "regex": "^private$"}}},
]}
RULE_FIELD_PRIVATE = "field_private"

RULES["typescript"] = {
    "function": _TS_FUNCTION_NAME,
    "type": _TS_TYPE_NAME,
    "property": _TS_GETTER,
    "field": _TS_FIELD_NAME,
    RULE_FIELD_PRIVATE: _TS_PRIVATE_FIELD_NAME,
}
RULES["tsx"] = {
    "function": {"all": [_TS_FUNCTION_NAME, {"not": _TS_PASCAL}]},
    "type": {"any": [*_TS_TYPE_NAME["any"], {"all": [_TS_FUNCTION_NAME, _TS_PASCAL]}]},
    "property": _TS_GETTER,
    "field": _TS_FIELD_NAME,
    RULE_FIELD_PRIVATE: _TS_PRIVATE_FIELD_NAME,
}

_GD_GETTER = {"field": "setget", "kind": "setget", "has": {"field": "get", "kind": "get_body"}}
RULES["gdscript"] = {
    "event": {"kind": "name", "inside": {"kind": "signal_statement", "field": "name"}},
    "function": {"kind": "name", "inside": {"kind": "function_definition", "field": "name"}},
    "property": {"kind": "name", "inside": {
        "kind": "variable_statement", "field": "name", "has": _GD_GETTER}},
    "variable": {"kind": "name", "inside": {
        "kind": "variable_statement", "field": "name", "not": {"has": _GD_GETTER}}},
}

_CASE_CHUNKS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")
_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    kind: str
    name: str
    rule: str
    detail: str
    suggestion: str


def _inline_rules(lang: str) -> str:
    return "\n---\n".join(
        json.dumps({"id": kind, "language": lang, "rule": rule})
        for kind, rule in RULES[lang].items()
    )


def declarations(
    path: Path, lang: str, config: Path | None = None
) -> list[tuple[int, str, str]]:
    """(line, declaration kind, name), 1-based, scanned from a copy carrying the
    language's own suffix: ast-grep reads `.h` as C and would find nothing.
    `config` points a custom language (GDScript) at its parser library."""
    with tempfile.TemporaryDirectory(prefix="mutation-gate-vocabulary-") as tmp:
        copy = Path(tmp, "source" + SUFFIX[lang])
        shutil.copyfile(path, copy)
        cmd = ["ast-grep", "scan"]
        if config is not None:
            cmd.append(f"--config={config}")
        cmd += [f"--inline-rules={_inline_rules(lang)}", "--json=compact", copy.name]
        proc = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise GateError(f"ast-grep scan failed on {path}: {proc.stderr.strip()}")
    hits = json.loads(proc.stdout) if proc.stdout.strip() else []
    return sorted((h["range"]["start"]["line"] + 1, h["ruleId"], h["text"]) for h in hits)


def words(name: str) -> list[str]:
    out: list[str] = []
    for chunk in name.removesuffix("_").split("_"):
        out.extend([chunk] if _DIGIT.search(chunk) else _CASE_CHUNKS.findall(chunk))
    return out


def _spelled_like(word: str, canonical: str) -> str:
    if word.isupper():
        return canonical.upper()
    return canonical.capitalize() if word[0].isupper() else canonical


def _exempt(dictionary: vocabulary.Dictionary, name: str) -> bool:
    dunder = name.startswith("__") and name.endswith("__")
    prefixed = any(name.startswith(p) for p in dictionary.convention_prefixes)
    return name == "_" or dunder or name in dictionary.conventions or prefixed


RULE_LEADING_UNDERSCORE = "leading_underscore"
RULE_UNKNOWN_WORD = "unknown_word"
RULE_VAGUE_WORD = "vague_word"
RULE_REJECTED_SYNONYM = "rejected_synonym"
RULE_FUNCTION_WORD = "function_word"
RULE_SYMBOL_SCOPE = "symbol_scope"
RULE_MOLD = "mold"
RULE_PRIVATE_TRAILING = "private_trailing_underscore"


def private_trailing(dictionary: vocabulary.Dictionary, name: str) -> list[tuple[str, str, str]]:
    """Decision 34 for TS `private`/`#` members: the marker is syntax, not the
    identifier's own spelling, so a bare or leading-`_` name still needs a trailing `_`."""
    if _exempt(dictionary, name) or name.startswith("_") or name.endswith("_"):
        return []
    return [(RULE_PRIVATE_TRAILING, "a private member takes a trailing `_`", f"{name}_")]


def judge(dictionary: vocabulary.Dictionary, kind: str, name: str,
          catalogue: dict[str, tuple[str, ...]] = vocabulary_molds.KINDS) -> list[tuple[str, str, str]]:
    """(rule, detail, suggested name or "") per fault in one declared name; the
    mold is judged only once every word resolved."""
    if _exempt(dictionary, name):
        return []
    out: list[tuple[str, str, str]] = []
    if name.startswith("_"):
        out.append((RULE_LEADING_UNDERSCORE,
                    "a leading `_` is not the private mark; private is a trailing `_`",
                    f"{name.strip('_')}_"))
    parts = words(name)
    faults: list[tuple[str, str, str]] = []
    for position, word in enumerate(parts):
        if position == 0 and word.lower() in vocabulary_molds.PREFIXES:
            continue
        match = dictionary.resolve(word) or dictionary.resolve(word.lower())
        if match is None:
            faults.append((RULE_UNKNOWN_WORD, f"`{word}` {UNKNOWN_DETAIL}", ""))
        elif match.kind == "vague":
            faults.append((RULE_VAGUE_WORD, f"`{word}` is vague — {match.detail}", ""))
        elif match.kind == "rejected":
            rule = RULE_FUNCTION_WORD if match.pos == ("rejected",) else RULE_REJECTED_SYNONYM
            renamed = name.replace(word, _spelled_like(word, match.word))
            faults.append((rule, f"`{word}`: {match.detail}",
                           renamed if match.word != word.lower() else ""))
        elif match.kind == "symbol" and kind not in SYMBOL_KINDS:
            faults.append((RULE_SYMBOL_SCOPE, f"`{word}`: {match.detail}", ""))
    if not faults and parts:
        misfit = vocabulary_molds.fit(dictionary, catalogue, kind, name, parts)
        if misfit:
            detail, suggestion = misfit
            faults.append((RULE_MOLD, detail, suggestion))
    return out + faults


def check(repo: Repo, changed: dict[str, set[int]], wvs) -> list[Finding]:
    dictionary = vocabulary.load(repo.root, repo.config.vocabulary)
    catalogue = vocabulary_molds.narrow(repo.config.vocabulary_molds)
    gdscript_config = repo.root / GDSCRIPT_CONFIG
    gdscript_ready = gdscript_config.exists()
    warned = False
    out: list[Finding] = []
    for rel, lines in sorted(changed.items()):
        lang = mutants.language_of(rel)
        excluded = any(rel.startswith(p) for p in repo.config.exclude_paths)
        if lang not in SUFFIX or excluded or not (repo.root / rel).exists():
            continue
        if lang == "gdscript" and not gdscript_ready:
            if not warned:
                _emit(GDSCRIPT_MISSING)
                warned = True
            continue
        mutants.require_ast_grep()
        config = gdscript_config if lang == "gdscript" else None
        for line, kind, name in declarations(repo.root / rel, lang, config):
            if line not in lines or waivers.finding_waived(wvs, CHECK, rel, line=line):
                continue
            if kind == RULE_FIELD_PRIVATE:
                faults = private_trailing(dictionary, name)
                reported_kind = "field"
            else:
                faults = judge(dictionary, kind, name, catalogue)
                reported_kind = kind
            for rule, detail, suggestion in faults:
                out.append(Finding(rel, line, reported_kind, name, rule, detail, suggestion))
    return out


def describe(f: Finding) -> str:
    text = f"{f.file}:{f.line}: {f.kind} `{f.name}` — {f.detail}"
    return f"{text} — try `{f.suggestion}`" if f.suggestion else text


def suggest(repo: Repo, f: Finding) -> str:
    return (
        "Rename it with a dictionary word in the mold for its kind (`mutation-gate vocabulary "
        f"lookup <word>`, `lookup --kind {f.kind} <name>`), add a "
        f"[[concept]] to {repo.config.vocabulary}, or record a waiver in {waivers.path(repo)}:\n"
        "[[waiver]]\n"
        f'check = "{CHECK}"\n'
        f'file = "{f.file}"\n'
        f"line = {f.line}\n"
        'reason = "REPLACE ME — who outside this repo dictates this name"\n'
    )


def gated_files(repo: Repo) -> list[str]:
    """Tracked files of a gated language, minus exclude_paths (#111 decision 2)."""
    tracked = git("ls-files", "-z", cwd=repo.root).split("\0")
    return sorted(
        rel for rel in tracked
        if rel and mutants.language_of(rel) in SUFFIX
        and not any(rel.startswith(p) for p in repo.config.exclude_paths)
    )


def audit(repo: Repo) -> list[Finding]:
    """Every declaration in `gated_files`, judged with no waivers (#111)."""
    changed = {
        rel: set(range(1, len((repo.root / rel).read_text().splitlines()) + 1))
        for rel in gated_files(repo)
    }
    return check(repo, changed, [])


def leading_underscore(repo: Repo) -> list[tuple[str, int, str, str]]:
    """(file, line, old, new) rows for #111 `--leading-underscore`: every declared
    name and path segment decisions 34/35 would reject a leading `_` on."""
    dictionary = vocabulary.load(repo.root, repo.config.vocabulary)
    gdscript_config = repo.root / GDSCRIPT_CONFIG
    gdscript_ready = gdscript_config.exists()
    rows: list[tuple[str, int, str, str]] = []
    for rel in gated_files(repo):
        lang = mutants.language_of(rel)
        if lang == "gdscript" and not gdscript_ready:
            continue
        config = gdscript_config if lang == "gdscript" else None
        for line, _kind, name in declarations(repo.root / rel, lang, config):
            if name.startswith("_") and not _exempt(dictionary, name):
                rows.append((rel, line, name, f"{name.strip('_')}_"))
        segments = rel.split("/")
        last = len(segments) - 1
        for index, segment in enumerate(segments):
            stem = segment if index != last else Path(segment).stem
            suffix = "" if index != last else Path(segment).suffix
            if stem.startswith("_") and not _exempt(dictionary, stem):
                rows.append((rel, 0, segment, f"{stem.strip('_')}_{suffix}"))
    return rows
