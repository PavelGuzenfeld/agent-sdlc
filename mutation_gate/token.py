"""Mutual exclusion between the two gates (decisions 4, 21).

The token binds to content, never to a clock: the Stop hook gates the working
tree and pre-commit gates the index, so a time-based token would let an edit
made between them ship ungated.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .repo import CACHE_ROOT, Repo


def _gate_hash() -> str:
    """The gate's own sources: a fixed generator or runner must not leave a
    token it issued still valid (#24)."""
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).resolve().parent.glob("*.py")):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def fingerprint(source_blob: str, candidate_blobs: list[str]) -> str:
    """Source blob, the candidate test set — a superset of the tests that ran,
    so a weakened test that only might have mattered still invalidates — and
    the gate that measured them."""
    payload = "\n".join([_gate_hash(), source_blob, *sorted(candidate_blobs)])
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _path(repo: Repo, target: str, fp: str) -> Path:
    safe = target.replace("/", "__")
    return CACHE_ROOT / repo.key / "tokens" / f"{safe}.{fp}"


def is_valid(repo: Repo, target: str, fp: str) -> bool:
    return _path(repo, target, fp).exists()


def write(repo: Repo, target: str, fp: str, verdict: str) -> None:
    path = _path(repo, target, fp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(verdict)


def clear(repo: Repo) -> int:
    tokens = CACHE_ROOT / repo.key / "tokens"
    if not tokens.exists():
        return 0
    count = 0
    for t in tokens.iterdir():
        t.unlink()
        count += 1
    return count
