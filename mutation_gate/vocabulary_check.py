"""Decisions 2, 11, 15, 22 and 34 of #103 as a check (#105): a name a diff declares
is built from dictionary words, spells private as a trailing `_`, and takes a
`[symbol]` word only as a local or parameter. References are never checked."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import mutants, vocabulary, vocabulary_molds, waivers
from .repo import GateError, Repo

CHECK = "vocabulary"
SUFFIX = {"python": ".py", "cpp": ".cpp"}
SYMBOL_KINDS = ("local", "parameter")


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

_CASE_CHUNKS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")
_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    kind: str
    name: str
    detail: str
    suggestion: str


def _inline_rules(lang: str) -> str:
    return "\n---\n".join(
        json.dumps({"id": kind, "language": lang, "rule": rule})
        for kind, rule in RULES[lang].items()
    )


def declarations(path: Path, lang: str) -> list[tuple[int, str, str]]:
    """(line, declaration kind, name), 1-based, scanned from a copy carrying the
    language's own suffix: ast-grep reads `.h` as C and would find nothing."""
    with tempfile.TemporaryDirectory(prefix="mutation-gate-vocabulary-") as tmp:
        copy = Path(tmp, "source" + SUFFIX[lang])
        shutil.copyfile(path, copy)
        proc = subprocess.run(
            ["ast-grep", "scan", f"--inline-rules={_inline_rules(lang)}", "--json=compact",
             copy.name],
            cwd=tmp, capture_output=True, text=True, check=False,
        )
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
    return name == "_" or dunder or name in dictionary.conventions


def judge(dictionary: vocabulary.Dictionary, kind: str, name: str,
          catalogue: dict[str, tuple[str, ...]] = vocabulary_molds.KINDS) -> list[tuple[str, str]]:
    """(detail, suggested name or "") per fault in one declared name; the mold is
    judged only once every word resolved."""
    if _exempt(dictionary, name):
        return []
    out: list[tuple[str, str]] = []
    if name.startswith("_"):
        out.append(("a leading `_` is not the private mark; private is a trailing `_`",
                    f"{name.strip('_')}_"))
    parts = words(name)
    faults: list[tuple[str, str]] = []
    for position, word in enumerate(parts):
        if position == 0 and word.lower() in vocabulary_molds.PREFIXES:
            continue
        match = dictionary.resolve(word) or dictionary.resolve(word.lower())
        if match is None:
            faults.append((f"`{word}` is not in the dictionary", ""))
        elif match.kind == "vague":
            faults.append((f"`{word}` is vague — {match.detail}", ""))
        elif match.kind == "rejected":
            renamed = name.replace(word, _spelled_like(word, match.word))
            faults.append((f"`{word}`: {match.detail}",
                           renamed if match.word != word.lower() else ""))
        elif match.kind == "symbol" and kind not in SYMBOL_KINDS:
            faults.append((f"`{word}`: {match.detail}", ""))
    if not faults and parts:
        misfit = vocabulary_molds.fit(dictionary, catalogue, kind, name, parts)
        if misfit:
            faults.append(misfit)
    return out + faults


def check(repo: Repo, changed: dict[str, set[int]], wvs) -> list[Finding]:
    dictionary = vocabulary.load(repo.root, repo.config.vocabulary)
    catalogue = vocabulary_molds.narrow(repo.config.vocabulary_molds)
    out: list[Finding] = []
    for rel, lines in sorted(changed.items()):
        lang = mutants.language_of(rel)
        excluded = any(rel.startswith(p) for p in repo.config.exclude_paths)
        if lang not in SUFFIX or excluded or not (repo.root / rel).exists():
            continue
        mutants.require_ast_grep()
        for line, kind, name in declarations(repo.root / rel, lang):
            if line not in lines or waivers.finding_waived(wvs, CHECK, rel, line=line):
                continue
            for detail, suggestion in judge(dictionary, kind, name, catalogue):
                out.append(Finding(rel, line, kind, name, detail, suggestion))
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
