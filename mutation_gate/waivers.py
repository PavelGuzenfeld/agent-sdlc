"""Committed waivers (decisions 6, 11).

Any survivor blocks; proceeding means recording it here with a reason. The file
is also the tuning data for the catalogue — a pattern that keeps appearing as
an equivalent mutant gets retired from CATALOGUE.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .mutants import Mutant
from .repo import WAIVERS_NAME, Repo

_NUMERIC = re.compile(r"-?\d+(\.\d+)?")


@dataclass(frozen=True)
class Waiver:
    reason: str
    file: str = ""
    old: str = ""
    new: str = ""
    line: int = 0
    column: int = 0
    uncovered: bool = False
    # Model-V&V findings (dotfiles#56 decision 7): no-spec, no-citation, dangling,
    # tagged. A key left empty widens the waiver, as deleting `line` does above.
    check: str = ""
    test: str = ""
    ms: int = 0

    def covers(self, mutant: Mutant) -> bool:
        if self.check or self.file != mutant.file:
            return False
        if self.uncovered:
            return True
        if self.line and self.line != mutant.line:
            return False
        if self.column and self.column != mutant.column:
            return False
        return self.old == mutant.old and self.new == mutant.new

    def covers_finding(self, check: str, file: str, test: str, ms: int, line: int) -> bool:
        if self.check != check:
            return False
        if self.file and self.file != file:
            return False
        if self.test and self.test != test:
            return False
        if self.line and self.line != line:
            return False
        return not self.ms or self.ms == ms


def _ambiguous(entry: dict) -> bool:
    """A literal mutant is identified only by its value, so `old = "0"` without a
    line waives every `0 => 1` in the file — silently covering sites nobody looked
    at. That is the hole a waiver file exists to close, so refuse it."""
    old = str(entry.get("old", ""))
    return bool(old) and not entry.get("line") and _NUMERIC.fullmatch(old) is not None


def load(repo: Repo) -> list[Waiver]:
    path = repo.root / WAIVERS_NAME
    if not path.exists():
        return []
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    out = []
    for entry in raw.get("waiver", []):
        if not entry.get("reason"):
            raise ValueError(f"{WAIVERS_NAME}: a waiver for {entry.get('file')} has no reason")
        if _ambiguous(entry):
            raise ValueError(
                f"{WAIVERS_NAME}: waiver for {entry.get('file')} old={entry.get('old')!r} "
                "is a bare literal and needs `line = <n>`; without it it would waive "
                "every identical literal mutation in the file"
            )
        out.append(Waiver(**entry))
    return out


def waived(waivers: list[Waiver], mutant: Mutant) -> Waiver | None:
    return next((w for w in waivers if w.covers(mutant)), None)


def stale(waivers: list[Waiver], file: str, every_mutant: list[Mutant]) -> list[Waiver]:
    """Waivers naming a site in `file` that the generator no longer produces.

    A waiver is keyed on line and column, so inserting anything above one moves its
    target out from under it. It then matches nothing, its mutant comes back as an
    unwaived survivor, and the run says only that something survived — never that a
    decision already recorded in the file stopped applying (dotfiles#88).

    `every_mutant` must be the whole file's mutants, not the diff's: the waiver whose
    line has drifted is exactly the one the changed-line set will not contain.
    """
    return [
        w for w in waivers
        if w.file == file and w.line and not w.uncovered and not w.check
        and not any(w.covers(m) for m in every_mutant)
    ]


def uncovered_waived(waivers: list[Waiver], file: str) -> Waiver | None:
    return next((w for w in waivers if w.uncovered and w.file == file), None)


def finding_waived(
    waivers: list[Waiver], check: str, file: str, test: str = "", ms: int = 0, line: int = 0
) -> Waiver | None:
    return next((w for w in waivers if w.covers_finding(check, file, test, ms, line)), None)


def suggest_finding(check: str, file: str, test: str = "", ms: int = 0) -> str:
    keys = [f'check = "{check}"', f'file = "{file}"']
    if test:
        keys.append(f'test = "{test}"')
    if ms:
        keys.append(f"ms = {ms}")
    return (
        "[[waiver]]\n" + "\n".join(keys) + "\n"
        'reason = "REPLACE ME — why no spec line can or should back this"\n'
    )


def suggest(mutant: Mutant) -> str:
    """Always scoped to the one site: `_ambiguous` refuses a bare literal without
    a line, and one line can hold two mutants with identical text. Widening is a
    decision to make by deleting a key."""
    return (
        "[[waiver]]\n"
        f'file = "{mutant.file}"\n'
        f"line = {mutant.line}\n"
        f"column = {mutant.column}\n"
        f'old = """{mutant.old}"""\n'
        f'new = """{mutant.new}"""\n'
        'reason = "REPLACE ME — why no test can or should kill this"\n'
    )


def suggest_uncovered(file: str) -> str:
    return (
        "[[waiver]]\n"
        f'file = "{file}"\n'
        "uncovered = true\n"
        'reason = "REPLACE ME — why this file has no covering tests"\n'
    )


def path(repo: Repo) -> Path:
    return repo.root / WAIVERS_NAME
