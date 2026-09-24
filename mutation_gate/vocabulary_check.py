"""Decisions 2, 11, 15, 22 and 34 of #103 as a check (#105): a name a diff declares
is built from dictionary words, spells private as a trailing `_`, and takes a
`[symbol]` word only as a local or parameter. References are never checked."""

from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from . import mutants, vocabulary, vocabulary_molds, waivers
from .repo import GateError, Repo, git

CHECK = "vocabulary"
SUFFIX = {"python": ".py", "cpp": ".cpp", "typescript": ".ts", "tsx": ".tsx", "gdscript": ".gd"}
SYMBOL_KINDS = ("local", "parameter")
UNKNOWN_DETAIL = "is not in the dictionary"
GDSCRIPT_CONFIG = "sgconfig.yml"
GDSCRIPT_MISSING = ("gdscript skipped: no " + GDSCRIPT_CONFIG + " — install the "
                    "parser with bin/install-gdscript-parser and commit one")


def _emit(line: str) -> None:
    print(line, file=sys.stderr)


@functools.cache
def _gdscript_ready(repo_root: Path) -> Path | None:
    """Probes rather than trusts `sgconfig.yml`'s mere existence, since the
    library it names can still be missing. Cached per root and warns once, so
    every check in a gate run shares one probe and one skip line (#233)."""
    config = repo_root / GDSCRIPT_CONFIG
    if not config.exists():
        _emit(GDSCRIPT_MISSING)
        return None
    probe = json.dumps({"id": "probe", "language": "gdscript", "rule": {"kind": "name"}})
    with tempfile.TemporaryDirectory(prefix="mutation-gate-vocabulary-") as tmp:
        source = Path(tmp, "probe.gd")
        source.write_text("")
        proc = subprocess.run(
            ["ast-grep", "scan", f"--config={config}", f"--inline-rules={probe}",
             "--json=compact", source.name],
            cwd=tmp, capture_output=True, text=True, check=False,
        )
    if proc.returncode == 0:
        return config
    _emit(GDSCRIPT_MISSING)
    return None


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
_TS_METHOD_NOT_ACCESSOR = {"kind": "method_definition", "field": "name",
                           "not": {"regex": r"^(get|set)\b"}}
_TS_PRIVATE_METHOD_NAME = {"any": [
    {"kind": "private_property_identifier", "inside": _TS_METHOD_NOT_ACCESSOR},
    {"kind": "property_identifier", "inside": {
        **_TS_METHOD_NOT_ACCESSOR, "has": {"kind": "accessibility_modifier", "regex": "^private$"}}},
]}
RULE_FIELD_PRIVATE = "field_private"
RULE_METHOD_PRIVATE = "method_private"

RULES["typescript"] = {
    "function": _TS_FUNCTION_NAME,
    "type": _TS_TYPE_NAME,
    "property": _TS_GETTER,
    "field": _TS_FIELD_NAME,
    RULE_FIELD_PRIVATE: _TS_PRIVATE_FIELD_NAME,
    RULE_METHOD_PRIVATE: _TS_PRIVATE_METHOD_NAME,
}
RULES["tsx"] = {
    "function": {"all": [_TS_FUNCTION_NAME, {"not": _TS_PASCAL}]},
    "type": {"any": [*_TS_TYPE_NAME["any"], {"all": [_TS_FUNCTION_NAME, _TS_PASCAL]}]},
    "property": _TS_GETTER,
    "field": _TS_FIELD_NAME,
    RULE_FIELD_PRIVATE: _TS_PRIVATE_FIELD_NAME,
    RULE_METHOD_PRIVATE: _TS_PRIVATE_METHOD_NAME,
}

_GD_GETTER = {"field": "setget", "kind": "setget", "has": {"field": "get", "kind": "get_body"}}
_GD_CONSTRUCTOR_PARAMETERS = {"kind": "parameters", "inside": {"kind": "constructor_definition"}}
RULES["gdscript"] = {
    "event": {"kind": "name", "inside": {"kind": "signal_statement", "field": "name"}},
    "function": {"kind": "name", "inside": {"kind": "function_definition", "field": "name"}},
    "parameter": {"kind": "identifier", "any": [
        {"inside": _GD_CONSTRUCTOR_PARAMETERS},
        {"inside": {"any": [{"kind": "typed_parameter"}, {"kind": "default_parameter"},
                             {"kind": "typed_default_parameter"}],
                     "inside": _GD_CONSTRUCTOR_PARAMETERS}},
    ]},
    "property": {"kind": "name", "inside": {
        "kind": "variable_statement", "field": "name", "has": _GD_GETTER}},
    "variable": {"kind": "name", "inside": {
        "kind": "variable_statement", "field": "name", "not": {"has": _GD_GETTER}}},
}

_TYPED = {"has": {"field": "type", "pattern": "$TYPE"}}
_NAMED = {"has": {"field": "name", "pattern": "$CLASS"}}
CAPTURES: dict[str, dict[str, dict]] = {
    "python": {
        "written": {"kind": "identifier", "any": [
            {"inside": {"kind": "function_definition", "field": "name",
                        "has": {"field": "return_type", "pattern": "$TYPE"}}},
            {"inside": {"kind": "assignment", "field": "left", **_TYPED}},
            {"inside": {"kind": "attribute", "field": "attribute",
                        "inside": {"kind": "assignment", "field": "left", **_TYPED}}},
            {"inside": {"kind": "typed_parameter", **_TYPED}},
            {"inside": {"kind": "typed_default_parameter", "field": "name", **_TYPED}},
        ]},
        "enclosing": {"kind": "identifier", "inside": {
            "kind": "function_definition", "field": "name",
            "inside": {"kind": "block", "stopBy": {"not": {"kind": "decorated_definition"}},
                       "inside": {"kind": "class_definition", **_NAMED}}}},
    },
    "cpp": {
        "written": {"any": [{"kind": "identifier"}, {"kind": "field_identifier"}], "inside": {
            "any": [{"kind": "declaration"}, {"kind": "field_declaration"},
                    {"kind": "function_definition"}, {"kind": "parameter_declaration"},
                    {"kind": "optional_parameter_declaration"}],
            "stopBy": {"not": {"any": [{"kind": "init_declarator"}, {"kind": "function_declarator"},
                                       {"kind": "reference_declarator"}]}}, **_TYPED}},
        "alias": {"kind": "type_identifier", "any": [
            {"inside": {"kind": "alias_declaration", "field": "name", **_TYPED}},
            {"inside": {"kind": "type_definition", "field": "declarator", **_TYPED}},
        ]},
        "enclosing": {"kind": "field_identifier", "inside": {
            "kind": "field_declaration_list", **_END, "inside": _NAMED}},
    },
    "typescript": {},
    "tsx": {},
    "gdscript": {},
}

_CASE_CHUNKS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")
_DIGIT = re.compile(r"\d")
_OUTER_TYPE = re.compile(r"[^\[<]*")
UNWRITTEN = ("", "auto")
VOID = ("None", "void")
NOUN_KINDS = ("variable", "field", "constant", "local", "parameter", "property")
VERB_KINDS = ("function", "method")


class Declared(NamedTuple):
    line: int
    kind: str
    name: str
    written: str = ""
    enclosing: str = ""


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
        for kind, rule in (RULES[lang] | CAPTURES[lang]).items()
    )


def _captured(hit: dict) -> dict[str, str]:
    return {key: value["text"] for key, value in hit["metaVariables"]["single"].items()}


def _declared(hits: list[dict], lang: str) -> list[Declared]:
    aliases = {h["text"]: _captured(h)["TYPE"] for h in hits if h["ruleId"] == "alias"}
    captured: dict[int, dict[str, str]] = {}
    for h in hits:
        if h["ruleId"] in CAPTURES[lang]:
            captured.setdefault(h["range"]["byteOffset"]["start"], {}).update(_captured(h))
    out: list[Declared] = []
    for h in hits:
        if h["ruleId"] in RULES[lang]:
            meta = captured.get(h["range"]["byteOffset"]["start"], {})
            written = meta.get("TYPE", "")
            out.append(Declared(h["range"]["start"]["line"] + 1, h["ruleId"], h["text"],
                                aliases.get(written, written), meta.get("CLASS", "")))
    return sorted(out)


def declarations(path: Path, lang: str, config: Path | None = None) -> list[Declared]:
    """1-based lines, scanned from a copy carrying the language's own suffix: ast-grep
    reads `.h` as C and would find nothing. A same-file alias resolves one level.
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
        raise GateError(f"ast-grep scan failed on {path}: {mutants.render_error_line(proc)}")
    hits = json.loads(proc.stdout) if proc.stdout.strip() else []
    return _declared(hits, lang)


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
RULE_TYPE_BOOL = "type_bool"
RULE_TYPE_COLLECTION = "type_collection"
RULE_TYPE_RETURN = "type_return"


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
            faults.append((RULE_VAGUE_WORD, f"`{word}` is vague", match.detail))
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


def _plural_of(dictionary: vocabulary.Dictionary, name: str, word: str,
               match: vocabulary.Match) -> str:
    plural = vocabulary.derive_forms(dictionary.concepts[match.word]).get("plural", "")
    return name[: -len(word)] + _spelled_like(word, plural) if plural else ""


def _judge_noun(dictionary: vocabulary.Dictionary, name: str, parts: list[str],
                written: str) -> list[tuple[str, str, str]]:
    if _OUTER_TYPE.match(written).group().strip() not in dictionary.collections:
        return []
    if any("p" in vocabulary_molds.tags(dictionary, word) for word in parts):
        return []
    last = parts[-1]
    match = dictionary.resolve(last) or dictionary.resolve(last.lower())
    if match is None or match.form == "plural":
        return []
    singular = (match.kind == "canonical" and "noun" in match.pos) or match.form == "-er"
    if not singular:
        return []
    return [(RULE_TYPE_COLLECTION, f"`{name}` is singular; `{written}` is a collection type",
             _plural_of(dictionary, name, last, match))]


def _judge_verb(dictionary: vocabulary.Dictionary, kind: str, first: str, written: str,
                enclosing: str) -> list[tuple[str, str, str]]:
    declared = f"it is declared to return `{written}`"
    if first in vocabulary_molds.MOLDS["conversion"].prefix:
        if kind != "method":
            return []
        if first == "from" and enclosing and written.strip("\"'") not in (enclosing, "Self"):
            return [(RULE_TYPE_RETURN,
                     f"`from_` returns the enclosing type `{enclosing}`; {declared}", "")]
        if first != "from" and written in VOID:
            return [(RULE_TYPE_RETURN, f"`{first}_` returns a value; {declared}", "")]
        return []
    match = dictionary.resolve(first)
    concept = dictionary.concepts.get(match.word) if match else None
    if concept is None or not concept.returns:
        return []
    if (concept.returns == "none") != (written in VOID):
        return [(RULE_TYPE_RETURN,
                 f"`{first}` is flagged `returns = \"{concept.returns}\"`; {declared}", "")]
    return []


_TRI_STATE_BOOL = re.compile(
    r"(?:typing\.)?Optional\[bool\]"
    r"|(?:typing\.)?Union\[\s*bool\s*,\s*None\s*\]"
    r"|(?:typing\.)?Union\[\s*None\s*,\s*bool\s*\]"
    r"|bool\s*\|\s*None"
    r"|None\s*\|\s*bool"
    r"|std::optional<bool>"
)


def judge_type(dictionary: vocabulary.Dictionary,
               declared: Declared) -> list[tuple[str, str, str]]:
    """T1 to T3 of decision 9 on the written type alone; an unwritten one is skipped."""
    if declared.written in UNWRITTEN or _exempt(dictionary, declared.name):
        return []
    parts = words(declared.name)
    first = parts[0].lower()
    out: list[tuple[str, str, str]] = []
    if first in vocabulary_molds.MOLDS["predicate"].prefix and declared.written != "bool":
        detail = f"`{first}_` asks yes or no; its type is `{declared.written}`, not `bool`"
        if _TRI_STATE_BOOL.fullmatch(declared.written):
            detail += "; a tri-state value needs a noun name"
        out.append((RULE_TYPE_BOOL, detail, ""))
    if declared.kind in NOUN_KINDS:
        out += _judge_noun(dictionary, declared.name, parts, declared.written)
    if declared.kind in VERB_KINDS:
        out += _judge_verb(dictionary, declared.kind, first, declared.written, declared.enclosing)
    return out


def check(repo: Repo, changed: dict[str, set[int]], wvs) -> list[Finding]:
    dictionary = vocabulary.load(repo.root, repo.config.vocabulary)
    catalogue = vocabulary_molds.narrow(repo.config.vocabulary_molds)
    out: list[Finding] = []
    for rel, lines in sorted(changed.items()):
        lang = mutants.language_of(rel)
        excluded = any(rel.startswith(p) for p in repo.config.exclude_paths)
        if lang not in SUFFIX or excluded or not (repo.root / rel).exists():
            continue
        config = _gdscript_ready(repo.root) if lang == "gdscript" else None
        if lang == "gdscript" and config is None:
            continue
        mutants.require_ast_grep()
        for declared in declarations(repo.root / rel, lang, config):
            line, kind, name = declared[:3]
            if line not in lines or waivers.finding_waived(wvs, CHECK, rel, line=line):
                continue
            if kind in (RULE_FIELD_PRIVATE, RULE_METHOD_PRIVATE):
                faults = private_trailing(dictionary, name)
                reported_kind = "field" if kind == RULE_FIELD_PRIVATE else "method"
            else:
                faults = judge(dictionary, kind, name, catalogue) + judge_type(dictionary, declared)
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
    name and path segment decisions 34/35 would reject a leading `_` on, minus
    #108's core [path] tool-dictated and exempt lists."""
    from . import vocabulary_path

    dictionary = vocabulary.load(repo.root, repo.config.vocabulary)
    rows: list[tuple[str, int, str, str]] = []
    for rel in gated_files(repo):
        lang = mutants.language_of(rel)
        config = _gdscript_ready(repo.root) if lang == "gdscript" else None
        if lang == "gdscript" and config is None:
            continue
        for line, _kind, name, *_ in declarations(repo.root / rel, lang, config):
            if name.startswith("_") and not _exempt(dictionary, name):
                rows.append((rel, line, name, f"{name.strip('_')}_"))
        segments = rel.split("/")
        last = len(segments) - 1
        for index, segment in enumerate(segments):
            is_last = index == last
            if not is_last and vocabulary_path.matches_any(segment, vocabulary_path.EXEMPT_PATH_PATTERNS):
                break
            if is_last and vocabulary_path.fully_exempt(segment):
                continue
            if vocabulary_path.matches_any(segment, vocabulary_path.EXEMPT_PATTERNS):
                continue
            stem = segment if not is_last else Path(segment).stem
            suffix = "" if not is_last else Path(segment).suffix
            if stem.startswith("_") and not _exempt(dictionary, stem):
                rows.append((rel, 0, segment, f"{stem.strip('_')}_{suffix}"))
    return rows
