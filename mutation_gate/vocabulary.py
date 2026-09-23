"""`mutation-gate vocabulary lookup <word>`: the packaged core dictionary plus the
repo's domain file, one concept map (#104; decisions 3, 4, 5, 15, 23, 25, 37 of #103)."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .repo import GateError, discover

CORE_PATH = Path(__file__).resolve().parent / "vocabulary_core.toml"

POS = ("noun", "verb", "adjective")
FORMS = ("plural", "-s", "-ed", "-ing", "-er")
RETURNS = ("value", "none")
CONCEPT_KEYS = {"word", "meaning", "pos", "reject", "forms", "irregular", "head", "returns"}
CONCEPT_KINDS = ("canonical", "rejected", "form")
DOMAIN_TABLES = {"concept", "reject", "symbol", "vague", "collection", "distinct"}
CORE_TABLES = DOMAIN_TABLES | {"function_words", "convention"}

_SIBILANT_ENDINGS = ("s", "x", "z", "ch", "sh")
_SINGLE_VOWEL_CLOSED_SYLLABLE = re.compile(r"[^aeiou]*[aeiou][^aeiouwxy]")


@dataclass(frozen=True)
class Concept:
    word: str
    meaning: str
    pos: tuple[str, ...]
    reject: tuple[str, ...]
    forms: tuple[str, ...]
    irregular: dict[str, str]
    head: bool
    returns: str
    source: str


@dataclass(frozen=True)
class Match:
    word: str
    kind: str
    pos: tuple[str, ...]
    detail: str
    source: str
    form: str = ""


@dataclass(frozen=True)
class Dictionary:
    concepts: dict[str, Concept]
    matches: dict[str, Match]
    collections: frozenset[str]
    distinct: frozenset[frozenset[str]]
    conventions: frozenset[str]

    def resolve(self, word: str) -> Match | None:
        return self.matches.get(word)


def _emit(line: str) -> None:
    print(line, file=sys.stderr)


def _has_consonant_y_ending(word: str) -> bool:
    return word.endswith("y") and word[-2:-1] not in "aeiou"


def derive(word: str, form: str) -> str:
    if form in ("plural", "-s"):
        if word.endswith(_SIBILANT_ENDINGS):
            return word + "es"
        if _has_consonant_y_ending(word):
            return word[:-1] + "ies"
        return word + "s"
    suffix = form[1:]
    if word.endswith("e"):
        keep = form == "-ing" and word.endswith("ee")
        return (word if keep else word[:-1]) + suffix
    if form != "-ing" and _has_consonant_y_ending(word):
        return word[:-1] + "i" + suffix
    doubled = word + word[-1] if _SINGLE_VOWEL_CLOSED_SYLLABLE.fullmatch(word) else word
    return doubled + suffix


def derive_forms(concept: Concept) -> dict[str, str]:
    return {
        form: concept.irregular.get(form) or derive(concept.word, form)
        for form in (*concept.forms, *concept.irregular)
    }


def _require(entry: dict, key: str, source: str):
    value = entry.get(key)
    if not value:
        raise GateError(f"{source}: `{entry.get('word', '?')}` needs a non-empty `{key}`")
    return value


def _require_within(source: str, word: str, values, allowed: tuple[str, ...], label: str) -> None:
    for value in values:
        if value not in allowed:
            raise GateError(
                f"{source}: `{word}`: {label} {value} is not one of {', '.join(allowed)}"
            )


def _parse_concept(entry: dict, source: str) -> Concept:
    word = _require(entry, "word", source)
    unknown = sorted(set(entry) - CONCEPT_KEYS)
    if unknown:
        raise GateError(f"{source}: `{word}` has unknown key(s) {', '.join(unknown)}")
    meaning = _require(entry, "meaning", source)
    pos = tuple(_require(entry, "pos", source))
    forms = tuple(entry.get("forms", []))
    irregular = dict(entry.get("irregular", {}))
    returns = entry.get("returns", "")
    _require_within(source, word, pos, POS, "pos")
    _require_within(source, word, forms, FORMS, "form")
    _require_within(source, word, irregular, FORMS, "form")
    _require_within(source, word, filter(None, [returns]), RETURNS, "returns")
    return Concept(
        word=word, meaning=meaning, pos=pos, reject=tuple(entry.get("reject", [])),
        forms=forms, irregular=irregular, head=bool(entry.get("head", False)),
        returns=returns, source=source,
    )


def _claim(matches: dict[str, Match], spelling: str, match: Match) -> None:
    existing = matches.get(spelling)
    if existing is None:
        matches[spelling] = match
        return
    same_concept = (existing.word == match.word
                    and existing.kind in CONCEPT_KINDS and match.kind in CONCEPT_KINDS)
    if not same_concept:
        raise GateError(
            f"{match.source}: `{spelling}` ({match.kind}) is already "
            f"{existing.kind} `{existing.word}` in {existing.source}"
        )


def _reject(concept: Concept, spelling: str, source: str) -> Match:
    return Match(word=concept.word, kind="rejected", pos=concept.pos, source=source,
                 detail=f"{spelling} is a rejected synonym of {concept.word}")


def _claim_concept(matches: dict[str, Match], concept: Concept) -> None:
    forms = derive_forms(concept)
    detail = f"forms: {', '.join(forms.values())}" if forms else ""
    _claim(matches, concept.word, Match(word=concept.word, kind="canonical", pos=concept.pos,
                                        detail=detail, source=concept.source))
    for spelling in concept.reject:
        _claim(matches, spelling, _reject(concept, spelling, concept.source))
    for form, spelling in forms.items():
        _claim(matches, spelling, Match(
            word=concept.word, kind="form", pos=concept.pos, source=concept.source, form=form,
            detail=f"{spelling} is the {form} form of {concept.word}",
        ))


def _read_layer(path: Path, tables: set[str]) -> dict:
    if not path.exists():
        raise GateError(f"{path}: no such vocabulary file")
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    unknown = sorted(set(raw) - tables)
    if unknown:
        raise GateError(f"{path}: unknown table(s) {', '.join(unknown)}")
    return raw


def _claim_function_words(matches: dict[str, Match], raw: dict) -> None:
    for kind, words in raw.get("function_words", {}).items():
        hints = words if isinstance(words, dict) else dict.fromkeys(words, "")
        for word, hint in hints.items():
            _claim(matches, word, Match(word=word, kind=kind, pos=(kind,), detail=hint,
                                        source=str(CORE_PATH)))


def load(root: Path, domain: str) -> Dictionary:
    layers = [(str(CORE_PATH), _read_layer(CORE_PATH, CORE_TABLES))]
    if domain:
        layers.append((str(root / domain), _read_layer(root / domain, DOMAIN_TABLES)))
    concepts: dict[str, Concept] = {}
    matches: dict[str, Match] = {}
    collections: set[str] = set()
    distinct: set[frozenset[str]] = set()
    _claim_function_words(matches, layers[0][1])
    for source, raw in layers:
        for entry in raw.get("vague", []):
            word = _require(entry, "word", source)
            _claim(matches, word, Match(word=word, kind="vague", pos=("vague",), source=source,
                                        detail=_require(entry, "hint", source)))
        for entry in raw.get("symbol", []):
            word = _require(entry, "word", source)
            meaning = _require(entry, "meaning", source)
            _claim(matches, word, Match(word=word, kind="symbol", pos=("symbol",), source=source,
                                        detail=f"{meaning}; locals and parameters only"))
        for entry in raw.get("concept", []):
            concept = _parse_concept(entry, source)
            if concept.word in concepts:
                raise GateError(f"{source}: `{concept.word}` is already canonical in "
                                f"{concepts[concept.word].source}")
            concepts[concept.word] = concept
            _claim_concept(matches, concept)
        collections.update(raw.get("collection", {}).get("types", []))
    for source, raw in layers:
        for spelling, target in raw.get("reject", {}).items():
            if target not in concepts:
                raise GateError(
                    f"{source}: [reject] {spelling} = {target!r}: `{target}` is not canonical"
                )
            _claim(matches, spelling, _reject(concepts[target], spelling, source))
        for entry in raw.get("distinct", []):
            pair = _require(entry, "pair", source)
            if len(pair) != 2:
                raise GateError(f"{source}: [[distinct]] {pair} is not a pair")
            if any(word not in concepts for word in pair):
                raise GateError(
                    f"{source}: [[distinct]] {pair} names a word that is not canonical"
                )
            distinct.add(frozenset(pair))
    conventions = frozenset(layers[0][1].get("convention", {}).get("names", []))
    return Dictionary(concepts, matches, frozenset(collections), frozenset(distinct), conventions)


def describe(match: Match) -> str:
    head = f"{match.word}: {', '.join(match.pos)}"
    return f"{head}\n  {match.detail}" if match.detail else head


def main(argv: list[str]) -> int:
    from . import vocabulary_check, vocabulary_molds

    parser = argparse.ArgumentParser(prog="mutation-gate vocabulary")
    parser.add_argument("action", choices=["lookup"])
    parser.add_argument("--kind", choices=sorted(vocabulary_molds.KINDS),
                        help="judge the word as a declared name of this kind")
    parser.add_argument("word")
    args = parser.parse_args(argv)
    try:
        repo = discover()
    except GateError:
        repo = None
    root = repo.root if repo else Path.cwd()
    domain = repo.config.vocabulary if repo else ""
    try:
        dictionary = load(root, domain)
        catalogue = vocabulary_molds.narrow(repo.config.vocabulary_molds if repo else {})
    except GateError as exc:
        _emit(f"mutation-gate vocabulary refused: {exc}")
        return 2
    if args.kind:
        faults = vocabulary_check.judge(dictionary, args.kind, args.word, catalogue)
        if not faults:
            print(f"{args.word}: fits the {args.kind} mold")
            return 0
        detail, suggestion = faults[0]
        _emit(f"vocabulary lookup: `{args.word}` as a {args.kind}: {detail}"
              + (f" — try `{suggestion}`" if suggestion else ""))
        return 1
    match = dictionary.resolve(args.word)
    if match is None:
        _emit(f"vocabulary lookup: `{args.word}` is not in the dictionary")
        return 1
    print(describe(match))
    return 0
