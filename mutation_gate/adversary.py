"""The isolated adversary pass (decisions 14, 15, 20, 23, 24).

Fires when the gate goes green — green is exactly when nothing else is looking.
The export carries intent and tests but never the implementation, so the review
cannot be anchored by what the code happens to do. It reports; it never blocks.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .repo import Repo, git

BRANCH_ISSUE_RE = re.compile(r"(?:^|/)(\d+)(?:-|$)")

PROMPT = """You are reviewing a test suite in isolation. You have the stated intent
and the tests. You deliberately do NOT have the implementation — do not ask for it
and do not speculate about it.

One question: do these tests pin the behaviour the intent requires?

Report only:
- requirements in the intent that NO test asserts
- tests that assert something the intent does not ask for
- assertions loose enough to pass on behaviour the intent forbids (a tolerance,
  a one-sided bound, an "is not None" where a value is specified)

Be specific and cite test names. If the tests fully cover the intent, say so in
one line. Do not suggest refactors or style changes.
"""


@dataclass
class Intent:
    source: str
    text: str


def resolve_intent(
    repo: Repo, user_prompt: str | None, session_prompt: str | None = None
) -> Intent | None:
    """Priority: an explicit prompt, then the branch's ticket, then the Stop
    hook's session prompt (#100). A ticket number with an empty body still
    skips rather than falling back — an unreachable `gh` must not review blind."""
    if user_prompt:
        return Intent("user prompt", user_prompt)
    number = _branch_issue(repo)
    if number:
        body = _issue_body(repo, number)
        return Intent(f"issue #{number}", body) if body else None
    if session_prompt:
        return Intent("session prompt", session_prompt)
    return None


def _branch_issue(repo: Repo) -> str:
    """Matches `NN-slug` and `type/NN-slug` only, so `fix/utf-8-decode` yields
    nothing: an unrelated ticket is worse intent than no ticket."""
    try:
        branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo.root).strip()
    except Exception:
        return ""
    match = BRANCH_ISSUE_RE.search(branch)
    return match.group(1) if match else ""


def _issue_body(repo: Repo, number: str) -> str:
    proc = subprocess.run(
        ["gh", "issue", "view", number, "-R", _slug(repo), "--json", "title,body",
         "-q", ".title + \"\\n\\n\" + .body"],
        capture_output=True, text=True, check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _slug(repo: Repo) -> str:
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", repo.origin)
    return m.group(1) if m else ""


def build_export(tests: list[Path], intent: Intent, dest: Path) -> None:
    """Tests plus intent, no implementation and no .git."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "INTENT.md").write_text(f"# Intent (from {intent.source})\n\n{intent.text}\n")
    tests_dir = dest / "tests"
    tests_dir.mkdir(exist_ok=True)
    for t in tests:
        shutil.copyfile(t, tests_dir / t.name)


def run(tests: list[Path], intent: Intent | None, results_note: str) -> str:
    """Returns the adversary's findings, or a one-line reason it did not run."""
    if intent is None:
        return (
            "adversary skipped: no linked ticket and no user prompt available; "
            "mutation results stand alone\n" + results_note
        )
    with tempfile.TemporaryDirectory(prefix="mutation-gate-adv-") as tmp:
        work = Path(tmp)
        build_export(tests, intent, work)
        findings = run_isolated("adversary", PROMPT, work)
    return f"intent: {intent.source}\n\n{findings}"


def run_isolated(name: str, prompt: str, work: Path, extra: tuple[str, ...] = ()) -> str:
    """`claude -p` in `work` with no rules, skills or memory; stdin closed so it
    cannot wait on a terminal. Returns findings or the one-line reason it did not run."""
    if not shutil.which("claude"):
        return f"{name} skipped: `claude` not on PATH"
    proc = subprocess.run(
        ["claude", "-p", prompt, "--restricted", "--disable-slash-commands", *extra],
        cwd=work, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False, timeout=600,
    )
    if proc.returncode != 0:
        return f"{name} failed to run: {proc.stderr.strip()[:200]}"
    return proc.stdout.strip()
