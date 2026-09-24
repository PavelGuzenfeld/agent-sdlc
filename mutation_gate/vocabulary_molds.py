"""Decisions 6, 7, 8, 10, 14, 24, 25, 27, 28, 29 and 32 of #103 (#106): the shape a
declared name must take, matched over every part-of-speech assignment its words allow.
A shape is a regex over one letter per word: N noun, H head noun, A adjective, V verb,
P past participle, G -ing form, p preposition, d determiner, o ordinal, t particle."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from . import vocabulary
from .repo import CONFIG_NAME, GateError

MAX_WORDS = 4
POS_LETTER = {"verb": "V", "adjective": "A"}
FORM_LETTER = {"-s": "V", "-ed": "P", "-ing": "G", "-er": "H"}
FUNCTION_WORD_LETTER = {"preposition": "p", "determiner": "d", "ordinal": "o", "particle": "t"}

_NOUN_PHRASE = "[do]?[AGN]*[NH]"
_QUALIFIED = f"{_NOUN_PHRASE}P?"
_TAIL = f"(?:p{_QUALIFIED})?"
_PHRASE = f"{_QUALIFIED}{_TAIL}"
_VERB_PHRASE = f"Vt?(?:{_QUALIFIED})?{_TAIL}"
_EVENT = "[AN]*[NH]P"


@dataclass(frozen=True)
class Mold:
    shape: str
    rule: str
    prefix: tuple[str, ...] = ()
    capped: bool = True


MOLDS: dict[str, Mold] = {
    "variable": Mold(_PHRASE, "a noun phrase, with at most one prepositional tail"),
    "predicate": Mold(f"(?:A|P|G|{_VERB_PHRASE}|{_PHRASE})",
                      "`is_`, `has_` or `can_`, then what is asked", ("is", "has", "can")),
    "function": Mold(_VERB_PHRASE, "a verb first, then what it acts on"),
    "test": Mold(f"{_QUALIFIED}(?:[GPp]{_QUALIFIED})*{_VERB_PHRASE}",
                 "`test_`, then subject, optional condition, outcome", ("test",), capped=False),
    "handler": Mold(_EVENT, "`on_`, then the event: nouns, then a past participle", ("on",)),
    "conversion": Mold(_QUALIFIED, "`from_`, `to_` or `as_`, then a noun phrase with no "
                       "prepositional tail", ("from", "to", "as")),
    "type": Mold(_NOUN_PHRASE, "a noun phrase ending in a noun, never an -ing form"),
    "namespace": Mold("N*[NH]", "nouns only"),
    "event": Mold(_EVENT, "nouns, then a past participle"),
    "enumerator": Mold(f"(?:A|P|G|{_PHRASE})", "an adjective, a participle or a noun phrase"),
}

_VALUE = ("variable", "predicate")
KINDS: dict[str, tuple[str, ...]] = {
    "function": ("function", "predicate", "test", "handler"),
    "method": ("function", "predicate", "test", "handler", "conversion"),
    **dict.fromkeys(("variable", "field", "constant", "local", "parameter", "property"), _VALUE),
    "bool": ("predicate",),
    "type": ("type",),
    "namespace": ("namespace",),
    "enumerator": ("enumerator",),
    "event": ("event",),
}
PREFIXES = frozenset(word for mold in MOLDS.values() for word in mold.prefix)


def narrow(config: dict[str, list[str]]) -> dict[str, tuple[str, ...]]:
    out = dict(KINDS)
    for kind, variants in config.items():
        if kind not in KINDS:
            raise GateError(f"{CONFIG_NAME}: vocabulary_molds.{kind}: not a declaration kind; "
                            f"one of {', '.join(KINDS)}")
        widening = sorted(set(variants) - set(KINDS[kind]))
        if widening or not variants:
            raise GateError(f"{CONFIG_NAME}: vocabulary_molds.{kind} = {list(variants)}: a repo "
                            f"narrows {', '.join(KINDS[kind])}, never widens")
        out[kind] = tuple(v for v in KINDS[kind] if v in variants)
    return out


def tags(dictionary: vocabulary.Dictionary, word: str) -> str:
    match = dictionary.resolve(word) or dictionary.resolve(word.lower())
    if match is None:
        return ""
    if match.kind == "symbol":
        return "N"
    if match.kind in FUNCTION_WORD_LETTER:
        return FUNCTION_WORD_LETTER[match.kind]
    concept = dictionary.concepts.get(match.word)
    if concept is None:
        return ""
    spelling = word.lower()
    noun = "H" if concept.head else "N"
    letters: set[str] = set()
    if spelling == concept.word:
        letters = {POS_LETTER.get(pos, noun) for pos in concept.pos}
    for form, derived in vocabulary.derive_forms(concept).items():
        if derived == spelling:
            letters.add(noun if form == "plural" else FORM_LETTER[form])
    return "".join(sorted(letters))


def _fits(mold: Mold, words: list[str], tagsets: list[str]) -> bool:
    if mold.prefix:
        if words[0].lower() not in mold.prefix:
            return False
        tagsets = tagsets[1:]
    if mold.capped and len(words) > MAX_WORDS:
        return False
    shape = re.compile(mold.shape)
    return any(shape.fullmatch("".join(pick)) for pick in itertools.product(*tagsets))


def _rejoin(name: str, moved: list[str]) -> str:
    tail = "_" if name.endswith("_") else ""
    if "_" in name.strip("_"):
        return "_".join(moved) + tail
    first = moved[0][0].lower() if name[0].islower() else moved[0][0].upper()
    return first + moved[0][1:] + "".join(w[0].upper() + w[1:] for w in moved[1:]) + tail


def _moved(molds: list[Mold], name: str, words: list[str], tagsets: list[str], pinned: int) -> str:
    movable = range(pinned, len(words))
    heads_first = sorted(movable, key=lambda i: "H" not in tagsets[i])
    for i in heads_first:
        for j in reversed(movable):
            if i == j:
                continue
            candidate, picks = list(words), list(tagsets)
            candidate.insert(j, candidate.pop(i))
            picks.insert(j, picks.pop(i))
            if any(_fits(m, candidate, picks) for m in molds):
                return _rejoin(name, candidate)
    return ""


def fit(dictionary: vocabulary.Dictionary, catalogue: dict[str, tuple[str, ...]], kind: str,
        name: str, words: list[str]) -> tuple[str, str] | None:
    """(first failing rule, suggested name or "") or None when some assignment fits."""
    molds = [MOLDS[variant] for variant in catalogue[kind]]
    tagsets = [tags(dictionary, word) for word in words]
    if any(_fits(mold, words, tagsets) for mold in molds):
        return None
    first = words[0].lower()
    own = next((mold for mold in molds if first in mold.prefix), None)
    lead = own or molds[0]
    if lead.capped and len(words) > MAX_WORDS:
        return f"{len(words)} words; a name has 1 to {MAX_WORDS}", ""
    foreign = next((variant for variant, mold in MOLDS.items()
                    if first in mold.prefix and variant not in catalogue[kind]), "")
    if foreign:
        return f"`{words[0]}_` starts the {foreign} mold, not open to a {kind}", ""
    relaxed = [t.replace("H", "N") for t in tagsets]
    if any(_fits(mold, words, relaxed) for mold in molds):
        head = next(word for word, t in zip(words, tagsets) if "H" in t)
        detail = (f"`{head}` is a head noun: last in its noun phrase, or last before a "
                  "prepositional tail")
    else:
        detail = f"a{'n' if kind[0] in 'aeiou' else ''} {kind} takes {lead.rule}"
    return detail, _moved(molds, name, words, tagsets, pinned=1 if own else 0)
