"""WordNet synonym check on dictionary additions (#110; decisions 12, 37 of
#103). A canonical word a diff adds to any dictionary layer blocks when it
shares a WordNet synset, restricted to the parts of speech both concepts
declare, with an existing canonical word — unless the pair is in
`[[distinct]]` or waived. `vocabulary_synonyms = "report"` turns the block
into a report line. nltk is optional at import time; a missing install or
unfetchable data refuses only once a dictionary change needs a lookup.
"""

from __future__ import annotations

import tomllib
import zipfile
from dataclasses import dataclass

from . import vocabulary, waivers
from .repo import CACHE_ROOT, CONFIG_NAME, GateError, Repo, git

try:
    import nltk
except ImportError:
    nltk = None

CHECK = "vocabulary-synonyms"
NLTK_DATA_DIR = CACHE_ROOT / "nltk_data"
_POS_TAGS = {"noun": ("n",), "verb": ("v",), "adjective": ("a", "s")}


@dataclass(frozen=True)
class DictionaryDiff:
    source: str
    added: tuple[str, ...]
    changed: tuple[str, ...]
    removed: tuple[str, ...]


@dataclass(frozen=True)
class Collision:
    word: str
    other: str
    pos: str
    source: str
    line: int


def _concepts_of(text: str) -> dict[str, dict]:
    if not text.strip():
        return {}
    return {e["word"]: e for e in tomllib.loads(text).get("concept", []) if e.get("word")}


def _pre_image(repo: Repo, rel: str, staged: bool) -> str:
    try:
        return git("show", f"{'HEAD' if staged else ''}:{rel}", cwd=repo.root)
    except GateError:
        return ""


def _word_line(text: str, word: str) -> int:
    needle = f'word = "{word}"'
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip() == needle:
            return number
    return 0


def layers(repo: Repo) -> list[str]:
    out = []
    try:
        out.append(str(vocabulary.CORE_PATH.relative_to(repo.root)))
    except ValueError:
        pass
    if repo.config.vocabulary:
        out.append(repo.config.vocabulary)
    return out


def diff_layer(repo: Repo, rel: str, staged: bool) -> DictionaryDiff | None:
    path = repo.root / rel
    if not path.exists():
        return None
    post = _concepts_of(path.read_text())
    pre = _concepts_of(_pre_image(repo, rel, staged))
    added = tuple(w for w in post if w not in pre)
    removed = tuple(w for w in pre if w not in post)
    changed = tuple(w for w in post if w in pre and post[w] != pre[w])
    if not (added or changed or removed):
        return None
    return DictionaryDiff(rel, added, changed, removed)


def diffs_for(repo: Repo, changed: dict[str, set[int]], staged: bool) -> list[DictionaryDiff]:
    out = []
    for rel in layers(repo):
        if rel not in changed:
            continue
        d = diff_layer(repo, rel, staged)
        if d:
            out.append(d)
    return out


def report(diffs: list[DictionaryDiff]) -> str:
    lines = ["Dictionary"]
    for d in diffs:
        lines.append(f"  {d.source}")
        for label, words in (("added", d.added), ("changed", d.changed), ("removed", d.removed)):
            if words:
                lines.append(f"    {label}: {', '.join(sorted(words))}")
    return "\n".join(lines)


def _ensure_data() -> None:
    if nltk is None:
        raise GateError(
            "WordNet is unavailable — nltk is not installed "
            '(pip install "agent-sdlc[vocabulary]")'
        )
    if str(NLTK_DATA_DIR) not in nltk.data.path:
        nltk.data.path.append(str(NLTK_DATA_DIR))
    try:
        nltk.data.find("corpora/wordnet")
        return
    except LookupError:
        pass
    NLTK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    fetched = nltk.download("wordnet", download_dir=str(NLTK_DATA_DIR), quiet=True)
    if not fetched:
        raise GateError("WordNet data is missing and could not be fetched (offline?)")
    zipped = NLTK_DATA_DIR / "corpora" / "wordnet.zip"
    if zipped.exists():
        with zipfile.ZipFile(zipped) as archive:
            archive.extractall(NLTK_DATA_DIR / "corpora")
    try:
        nltk.data.find("corpora/wordnet")
    except LookupError as exc:
        raise GateError("WordNet data fetch reported success but is unreadable") from exc


def synset_names(word: str, pos: str) -> frozenset[str]:
    _ensure_data()
    from nltk.corpus import wordnet as wn
    return frozenset(s.name() for tag in _POS_TAGS[pos] for s in wn.synsets(word, pos=tag))


def _collisions_for(
    dictionary: vocabulary.Dictionary, diffs: list[DictionaryDiff], sources: dict[str, str]
) -> list[Collision]:
    out: list[Collision] = []
    seen: set[frozenset[str]] = set()
    for d in diffs:
        for word in d.added:
            concept = dictionary.concepts.get(word)
            if concept is None:
                continue
            for other_word, other in dictionary.concepts.items():
                pair = frozenset((word, other_word))
                if other_word == word or pair in dictionary.distinct or pair in seen:
                    continue
                for pos in sorted(set(concept.pos) & set(other.pos)):
                    if synset_names(word, pos) & synset_names(other_word, pos):
                        out.append(Collision(word=word, other=other_word, pos=pos,
                                              source=d.source, line=_word_line(sources[d.source], word)))
                        seen.add(pair)
                        break
    return out


def check(
    repo: Repo, changed: dict[str, set[int]], wvs: list[waivers.Waiver], staged: bool
) -> tuple[list[DictionaryDiff], list[Collision]]:
    if repo.config.vocabulary_synonyms not in ("block", "report"):
        raise GateError(
            f'{CONFIG_NAME}: vocabulary_synonyms must be "block" or "report", '
            f"got {repo.config.vocabulary_synonyms!r}"
        )
    diffs = diffs_for(repo, changed, staged)
    if not diffs or not any(d.added for d in diffs):
        return diffs, []
    dictionary = vocabulary.load(repo.root, repo.config.vocabulary)
    sources = {d.source: (repo.root / d.source).read_text() for d in diffs}
    collisions = _collisions_for(dictionary, diffs, sources)
    collisions = [c for c in collisions
                  if not waivers.finding_waived(wvs, CHECK, c.source, line=c.line)]
    return diffs, collisions


def suggest(repo: Repo, c: Collision) -> str:
    return (
        f'Add `{c.word} = "{c.other}"` under [reject] in {c.source}, pick a different '
        f"canonical word, or record a waiver in {waivers.path(repo)}:\n"
        "[[waiver]]\n"
        f'check = "{CHECK}"\n'
        f'file = "{c.source}"\n'
        f"line = {c.line}\n"
        'reason = "REPLACE ME — why these are different concepts"\n'
    )
