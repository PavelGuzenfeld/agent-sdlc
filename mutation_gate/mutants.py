"""Mechanical mutant generation (decisions 9, 10): ast-grep patterns intersected
with the lines a diff actually touched.

A mutant is a byte-range splice, so one catalogue site is mutated in isolation
even where the same pattern matches elsewhere in the file.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tokenize
from dataclasses import dataclass
from pathlib import Path

from .repo import GateError

# Broad catalogue per decision 10. Retire an entry here when it keeps landing in
# waiver files as an equivalent mutant — the waiver list is the tuning data.
CATALOGUE: dict[str, list[tuple[str, str]]] = {
    "python": [
        ("$A <= $B", "$A < $B"),
        ("$A < $B", "$A <= $B"),
        ("$A >= $B", "$A > $B"),
        ("$A > $B", "$A >= $B"),
        ("$A == $B", "$A != $B"),
        ("$A != $B", "$A == $B"),
        ("$A and $B", "$A or $B"),
        ("$A or $B", "$A and $B"),
        ("$A + $B", "$A - $B"),
        ("$A - $B", "$A + $B"),
        ("$A * $B", "$A / $B"),
        ("$A / $B", "$A * $B"),
        ("not $A", "$A"),
        ("-$A", "$A"),
        ("min($A, $B)", "max($A, $B)"),
        ("max($A, $B)", "min($A, $B)"),
        ("return True", "return False"),
        ("return False", "return True"),
        ("$A is $B", "$A is not $B"),
        ("$A in $B", "$A not in $B"),
        ("break", "continue"),
        ("continue", "break"),
    ],
    # GDScript accepts both boolean spellings, so both need entries or a mutant is
    # silently missed on whichever spelling the code uses.
    "gdscript": [
        ("$A <= $B", "$A < $B"),
        ("$A < $B", "$A <= $B"),
        ("$A >= $B", "$A > $B"),
        ("$A > $B", "$A >= $B"),
        ("$A == $B", "$A != $B"),
        ("$A != $B", "$A == $B"),
        ("$A and $B", "$A or $B"),
        ("$A or $B", "$A and $B"),
        ("$A && $B", "$A || $B"),
        ("$A || $B", "$A && $B"),
        ("$A + $B", "$A - $B"),
        ("$A - $B", "$A + $B"),
        ("$A * $B", "$A / $B"),
        ("$A / $B", "$A * $B"),
        ("not $A", "$A"),
        ("!$A", "$A"),
        ("-$A", "$A"),
        ("$A is $B", "$A is not $B"),
        ("$A is not $B", "$A is $B"),
        ("$A in $B", "$A not in $B"),
        ("$A not in $B", "$A in $B"),
        ("min($A, $B)", "max($A, $B)"),
        ("max($A, $B)", "min($A, $B)"),
        ("return true", "return false"),
        ("return false", "return true"),
        ("break", "continue"),
        ("continue", "break"),
        ("clamp($A, $B, $C)", "$A"),
        ("clampf($A, $B, $C)", "$A"),
        ("is_equal_approx($A, $B)", "not is_equal_approx($A, $B)"),
        ("lerp($A, $B, $T)", "lerp($B, $A, $T)"),
        ("move_toward($A, $B, $D)", "$B"),
        ("snapped($A, $B)", "$A"),
        ("wrapf($A, $B, $C)", "$A"),
        ("await $A", "$A"),
    ],
    "cpp": [
        ("$A <= $B", "$A < $B"),
        ("$A < $B", "$A <= $B"),
        ("$A >= $B", "$A > $B"),
        ("$A > $B", "$A >= $B"),
        ("$A == $B", "$A != $B"),
        ("$A != $B", "$A == $B"),
        ("$A && $B", "$A || $B"),
        ("$A || $B", "$A && $B"),
        ("$A + $B", "$A - $B"),
        ("$A - $B", "$A + $B"),
        ("$A * $B", "$A / $B"),
        ("!$A", "$A"),
        ("-$A", "$A"),
        ("return true", "return false"),
        ("return false", "return true"),
    ],
}

# TSX is a distinct ast-grep grammar (JSX support), but the same operator patterns
# match both, so one list serves both SUFFIX_LANG entries.
CATALOGUE["typescript"] = CATALOGUE["tsx"] = [
    ("$A <= $B", "$A < $B"),
    ("$A < $B", "$A <= $B"),
    ("$A >= $B", "$A > $B"),
    ("$A > $B", "$A >= $B"),
    ("$A === $B", "$A !== $B"),
    ("$A !== $B", "$A === $B"),
    ("$A && $B", "$A || $B"),
    ("$A || $B", "$A && $B"),
    # Nullish vs. falsy: 0, "" and false take the fallback under || but not ??.
    ("$A ?? $B", "$A || $B"),
    ("$A + $B", "$A - $B"),
    ("$A - $B", "$A + $B"),
    ("$A * $B", "$A / $B"),
    ("$A / $B", "$A * $B"),
    ("!$A", "$A"),
    ("-$A", "$A"),
    ("return true", "return false"),
    ("return false", "return true"),
]

LITERAL_RE = re.compile(rb"(?<![\w.])(\d+\.\d+|\d+)(?![\w.])")

SUFFIX_LANG = {
    ".gd": "gdscript",
    ".py": "python",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".h": "cpp",
    ".cu": "cpp",
    ".cuh": "cpp",
    ".ts": "typescript",
    ".tsx": "tsx",
}


@dataclass(frozen=True)
class Mutant:
    file: str
    line: int
    start: int
    end: int
    old: str
    new: str
    kind: str
    # Byte offset within the line. Two sites on one line can carry identical
    # text — `np.zeros((2 * n, 2 * n))` — and nothing else tells them apart.
    column: int = 0

    @property
    def ident(self) -> str:
        return (
            f"{self.file}:{self.line}:{self.column}:{self.kind}:"
            f"{self.old} => {self.new}"
        )


def language_of(path: str) -> str | None:
    return SUFFIX_LANG.get(Path(path).suffix)


def changed_lines(root: Path, staged: bool) -> dict[str, set[int]]:
    """Post-image line numbers per file. staged=index (pre-commit), else worktree."""
    args = ["diff", "-U0", "--no-color"]
    if staged:
        args.append("--cached")
    out = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    ).stdout
    result: dict[str, set[int]] = {}
    current = None
    for raw in out.splitlines():
        if raw.startswith("+++ b/"):
            current = raw[6:]
            result.setdefault(current, set())
        elif raw.startswith("@@") and current is not None:
            m = re.search(r"\+(\d+)(?:,(\d+))?", raw)
            if m:
                start, count = int(m.group(1)), int(m.group(2) or 1)
                result[current].update(range(start, start + count))
    return {f: lines for f, lines in result.items() if lines}


def _ast_grep(path: Path, lang: str, pattern: str, replacement: str) -> list[dict]:
    """`--pattern=` / `--rewrite=`, never `-p` / `-r`: a pattern starting with a
    dash (`-$A`, `!$A`) is otherwise parsed as a flag and silently matches
    nothing, so the catalogue claims coverage it does not have."""
    proc = subprocess.run(
        [
            "ast-grep", "run", "-l", lang,
            f"--pattern={pattern}", f"--rewrite={replacement}",
            "--json=compact", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in (0, 1):
        raise GateError(
            f"ast-grep failed on pattern {pattern!r}: {proc.stderr.strip()[:200]}"
        )
    if not proc.stdout.strip():
        return []
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise GateError(f"ast-grep gave unparseable JSON for {pattern!r}: {exc}") from exc


def _line_starts(data: bytes) -> list[int]:
    starts, pos = [0], 0
    for line in data.splitlines(keepends=True):
        pos += len(line)
        starts.append(pos)
    return starts


# Kind names are grammar-specific and ast-grep rejects one the grammar lacks:
# C++ spells it `string_literal`, so the GDScript `string` would abort the scan.
#
# array_declarator and template_argument_list carry compile-time extents:
# `double q[8]`, `std::array<double, 4>`. A wider one only adds a slot no code
# names — an indexed loop bounded by the same literal never reaches it, and a
# range-for reaches a value-initialised one. Seven rebuilt bit-identical over
# the public surface. Costs `std::get<N>`; revisit if the fleet indexes tuples.
MASK_KINDS = {
    "gdscript": ("string", "comment"),
    "cpp": (
        "string_literal", "system_lib_string", "comment",
        "array_declarator", "template_argument_list",
    ),
    "typescript": ("string", "template_string", "comment"),
    "tsx": ("string", "template_string", "comment"),
}


def kind_hits(path: Path, lang: str, kind: str) -> list[dict]:
    proc = subprocess.run(
        ["ast-grep", "run", "-l", lang, "--kind", kind, "--json=compact", str(path)],
        capture_output=True, text=True, check=False,
    )
    if not proc.stdout.strip():
        return []
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []


def _kind_spans(path: Path, lang: str) -> list[tuple[int, int]]:
    """Grammar-driven alternative to `tokenize` for languages it cannot read."""
    return [
        (h["range"]["byteOffset"]["start"], h["range"]["byteOffset"]["end"])
        for kind in MASK_KINDS[lang]
        for h in kind_hits(path, lang, kind)
    ]


def masked_spans(path: Path, lang: str) -> list[tuple[int, int]]:
    """Byte spans where a literal perturbation cannot be observed: strings and
    comments, which are not code, and the compile-time extents of MASK_KINDS.
    Mutating inside one yields a guaranteed meaningless survivor."""
    if lang in MASK_KINDS:
        return _kind_spans(path, lang)
    if lang != "python":
        return []
    spans, starts = [], _line_starts(path.read_bytes())
    try:
        with path.open("rb") as fh:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type in (tokenize.STRING, tokenize.COMMENT):
                    spans.append(
                        (starts[tok.start[0] - 1] + tok.start[1],
                         starts[tok.end[0] - 1] + tok.end[1])
                    )
    except (tokenize.TokenError, IndentationError, SyntaxError, IndexError, ValueError):
        return []
    return spans


def _masked(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def _literal_mutants(
    rel: str, data: bytes, lines: set[int], spans: list[tuple[int, int]]
) -> list[Mutant]:
    """One numeric-literal perturbation per changed line — the class that caught
    the 0.5*hypot bug, which no relational pattern reaches."""
    out, starts, rows = [], _line_starts(data), data.splitlines()
    for lineno in sorted(lines):
        if lineno > len(rows):
            continue
        begin, text = starts[lineno - 1], rows[lineno - 1]
        if text.lstrip().startswith((b"#", b"//")):
            continue
        for m in LITERAL_RE.finditer(text):
            if _masked(begin + m.start(1), spans):
                continue
            lit = m.group(1).decode()
            new = f"{float(lit) + 1.0:g}" if "." in lit else str(int(lit) + 1)
            out.append(
                Mutant(rel, lineno, begin + m.start(1), begin + m.end(1), lit, new,
                       "literal", m.start(1))
            )
            break
    return out


def generate(root: Path, files: dict[str, set[int]], language: str) -> list[Mutant]:
    """Every catalogue site landing on a changed line. No budget (decision 8)."""
    out: list[Mutant] = []
    for rel, lines in sorted(files.items()):
        path = root / rel
        if not path.exists():
            continue
        lang = language_of(rel) or language
        data = path.read_bytes()
        starts = _line_starts(data)
        spans = masked_spans(path, lang)
        seen: set[tuple[int, int]] = set()
        for pattern, replacement in CATALOGUE.get(lang, []):
            for hit in _ast_grep(path, lang, pattern, replacement):
                lineno = hit["range"]["start"]["line"] + 1
                span = (
                    hit["range"]["byteOffset"]["start"],
                    hit["range"]["byteOffset"]["end"],
                )
                # `$A in $B` also matches `not in` and rewrites it to itself; skipped
                # BEFORE `seen`, or the identity shadows the real `not in => in` mutant.
                if hit["replacement"] == hit["text"]:
                    continue
                if lineno not in lines or span in seen:
                    continue
                seen.add(span)
                out.append(
                    Mutant(rel, lineno, span[0], span[1],
                           hit["text"], hit["replacement"], "operator",
                           span[0] - starts[lineno - 1])
                )
        out.extend(_literal_mutants(rel, data, lines, spans))
    return sorted(out, key=lambda m: (m.file, m.line, m.start, m.new))


def require_ast_grep() -> None:
    if not shutil.which("ast-grep"):
        raise GateError("ast-grep not found on PATH; the gate cannot generate mutants")
    proc = subprocess.run(["ast-grep", "--version"], capture_output=True, check=False)
    if proc.returncode != 0:
        raise GateError("ast-grep not found on PATH; the gate cannot generate mutants")
