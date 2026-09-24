#!/usr/bin/env python3
"""Mine declared-name words across a set of repo clones for #112: for each
repo, every declared name's words (skipping decision-11 exemptions), folded
to lower case, counted per repo. Writes the full word/repo table as TOML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mutation_gate import mutants, no_leaks, vocabulary, vocabulary_check  # noqa: E402
from mutation_gate.repo import discover, git  # noqa: E402

_UNSUPPORTED_LANGUAGES = frozenset({"gdscript"})


def _own_name(dictionary: vocabulary.Dictionary, name: str, lang: str) -> bool:
    dunder = name.startswith("__") and name.endswith("__")
    return name == "_" or dunder or name in dictionary.convention_for(lang).names


def mine_repo(root: Path) -> tuple[str, dict[str, int]]:
    repo = discover(root)
    sha = git("rev-parse", "HEAD", cwd=root).strip()
    dictionary = vocabulary.load(repo.root, repo.config.vocabulary)
    counts: dict[str, int] = {}
    for rel in vocabulary_check.gated_files(repo):
        lang = mutants.language_of(rel)
        if lang not in vocabulary_check.SUFFIX or lang in _UNSUPPORTED_LANGUAGES:
            continue
        for declared in vocabulary_check.declarations(root / rel, lang):
            name = declared[2]
            if _own_name(dictionary, name, lang):
                continue
            for word in vocabulary_check.words(name):
                key = word.lower()
                counts[key] = counts.get(key, 0) + 1
    return sha, counts


def _screen(words: set[str], banned_names_file: str) -> list[str]:
    names = no_leaks.load_banned_names(banned_names_file) if banned_names_file else []
    return [name.token.lower() for name in names if name.token.lower() in words]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo", nargs="+", help="label=path, one per cloned repo")
    parser.add_argument("--banned-names-file", default="")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args(argv)

    per_repo: dict[str, dict[str, int]] = {}
    shas: dict[str, str] = {}
    for entry in args.repo:
        label, _, path = entry.partition("=")
        sha, counts = mine_repo(Path(path))
        shas[label] = sha
        per_repo[label] = counts

    all_words: set[str] = set()
    for counts in per_repo.values():
        all_words.update(counts)

    hits = _screen(all_words, args.banned_names_file)
    if hits:
        for token in hits:
            print(f"BANNED TOKEN MINED: {token}", file=sys.stderr)
        return 2

    rows = []
    for word in sorted(all_words):
        present = {label: counts[word] for label, counts in per_repo.items() if word in counts}
        rows.append((word, len(present), present))
    rows.sort(key=lambda r: (-r[1], r[0]))

    with open(args.output, "w") as fh:
        fh.write("[shas]\n")
        for label, sha in sorted(shas.items()):
            fh.write(f'{label} = "{sha}"\n')
        fh.write("\n")
        for word, repo_count, present in rows:
            fh.write("[[word]]\n")
            fh.write(f'text = "{word}"\n')
            fh.write(f"repo_count = {repo_count}\n")
            fh.write("occurrences = {")
            fh.write(", ".join(f"{label} = {count}" for label, count in sorted(present.items())))
            fh.write("}\n\n")
    print(f"wrote {len(rows)} words across {len(per_repo)} repos to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
