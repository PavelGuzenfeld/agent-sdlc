"""Layer 0 of model-vv.md as a hook (dotfiles#56, decisions 1–7, 10–12).

Only the mechanical part: a spec exists when model code changes, a diff-touched
model test cites a spec line, the line exists and is no longer tagged, and a
keyword probe blocks once on model code nobody declared. Layers 1, 2, 4 and 5
are not checkable without reading intent and stay prose. Runs before any mutant
and runs no tests, so there is no token to honour.
"""

from __future__ import annotations

import hashlib
import os
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import adversary, coverage_map, mutants, waivers
from .repo import CONFIG_NAME, GateError, Repo, git

SPEC_PATH = "docs/model-spec.md"
ISSUE_PREFIX = "issue:"
SPEC_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?\*{0,2}MS-(\d+)\*{0,2}[.:)]?\s")
CITATION_RE = re.compile(r"\bMS-(\d+)\b")
INTENT_TAGS = ("(needs intent)", "(reconstructed)")

# Measured on gst-nvmm-cpp: 11 hits on kalman_box.cpp, 3 on its header, 0 on
# three benchmark files. Small sample; model_exclude entries are the tuning data.
PROBE_TOKENS = (
    r"atan2", r"jacobian", r"cholesky", r"covariance", r"innovation",
    r"residual", r"process noise", r"\bdt\b", r"sigma",
)
PROBE_RE = re.compile("|".join(PROBE_TOKENS), re.IGNORECASE)
WRAP_RE = re.compile(r"wrap", re.IGNORECASE)
PI_RE = re.compile(r"\bpi\b|M_PI|two_pi|TWO_PI", re.IGNORECASE)

# One function_definition per test; the head names it. Catch2's
# TEST_CASE("string") does not parse as a function_definition and is not covered.
TEST_HEAD = {
    "python": re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)"),
    "cpp": re.compile(r"^\s*TEST(?:_F|_P)?\s*\(\s*([^)]*?)\s*\)"),
}


@dataclass(frozen=True)
class Finding:
    check: str
    file: str
    detail: str
    test: str = ""
    ms: int = 0


@dataclass(frozen=True)
class TestExtent:
    name: str
    start: int
    end: int
    text: str

    def touches(self, lines: set[int]) -> bool:
        return any(self.start <= n <= self.end for n in lines)

    def citations(self) -> set[int]:
        return {int(n) for n in CITATION_RE.findall(self.text)}


def spec_source(repo: Repo) -> str:
    return repo.config.model_spec or SPEC_PATH


def fetch_issue_body(repo: Repo, number: str) -> str | None:
    proc = subprocess.run(
        ["gh", "issue", "view", number, "--json", "body", "-q", ".body"],
        cwd=repo.root, capture_output=True, text=True, check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


def _issue_cache(repo: Repo, number: str) -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "mutation-gate"
    slug = hashlib.sha1(str(repo.root).encode()).hexdigest()[:12]
    return base / f"spec-{slug}-issue-{number}.md"


def spec_text(repo: Repo) -> str | None:
    """The spec as text, or None when a file source is absent. An issue source is
    fetched through gh and cached; offline it falls back to the cache and refuses
    when there is none, because a spec the gate cannot read is not a spec."""
    source = spec_source(repo)
    if not source.startswith(ISSUE_PREFIX):
        path = repo.root / source
        return path.read_text(errors="ignore") if path.exists() else None
    number = source[len(ISSUE_PREFIX):]
    cache = _issue_cache(repo, number)
    body = fetch_issue_body(repo, number)
    if body is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(body)
        return body
    if cache.exists():
        return cache.read_text()
    raise GateError(f"cannot read model spec {source}: gh failed and no cached copy exists")


def load_spec(repo: Repo) -> dict[int, str] | None:
    """MS-n -> its line. Duplicate numbers refuse: a citation must name one line."""
    text = spec_text(repo)
    if text is None:
        return None
    source = spec_source(repo)
    lines: dict[int, str] = {}
    for raw in text.splitlines():
        m = SPEC_LINE_RE.match(raw)
        if not m:
            continue
        n = int(m.group(1))
        if n in lines:
            raise GateError(f"{source}: MS-{n} is defined twice")
        lines[n] = raw
    return lines


def tagged(line: str) -> bool:
    return any(tag in line for tag in INTENT_TAGS)


def probe_hit(text: str) -> str | None:
    m = PROBE_RE.search(text)
    if m:
        return m.group(0)
    if WRAP_RE.search(text) and PI_RE.search(text):
        return "wrap+pi"
    return None


def _under(rel: str, prefixes: list[str]) -> bool:
    return any(rel.startswith(p) for p in prefixes)


def _post_image(repo: Repo, rel: str, staged: bool) -> str:
    if staged:
        try:
            return git("show", f":{rel}", cwd=repo.root)
        except GateError:
            return ""
    path = repo.root / rel
    return path.read_text(errors="ignore") if path.exists() else ""


def _files_under(root: Path, prefix: str) -> list[Path]:
    base = root / prefix
    if base.is_file():
        return [base]
    return sorted(p for p in base.rglob("*") if p.is_file()) if base.is_dir() else []


def model_tests(repo: Repo) -> set[str]:
    """Repo-relative test files in model scope: under model_test_paths, or (python
    only) importing a model_paths module — the same candidacy the mutant run uses."""
    cfg = repo.config
    scope: set[str] = set()
    for prefix in cfg.model_test_paths:
        scope.update(str(p.relative_to(repo.root)) for p in _files_under(repo.root, prefix))
    for prefix in cfg.model_paths:
        for model_file in _files_under(repo.root, prefix):
            if model_file.suffix != ".py":
                continue
            rel = str(model_file.relative_to(repo.root))
            scope.update(str(t.relative_to(repo.root)) for t in coverage_map.candidates(repo, rel))
    return scope


def test_extents(path: Path, language: str) -> list[TestExtent]:
    head = TEST_HEAD.get(language)
    if head is None:
        return []
    proc = subprocess.run(
        ["ast-grep", "run", "-l", language, "--kind", "function_definition",
         "--json=compact", str(path)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode not in (0, 1):
        raise GateError(f"ast-grep failed on {path}: {proc.stderr.strip()[:200]}")
    if not proc.stdout.strip():
        return []
    out = []
    for hit in json.loads(proc.stdout):
        m = head.match(hit["text"])
        if not m:
            continue
        rng = hit["range"]
        out.append(TestExtent(m.group(1), rng["start"]["line"] + 1, rng["end"]["line"] + 1, hit["text"]))
    return out


def _probe(repo: Repo, changed: dict[str, set[int]], staged: bool) -> list[Finding]:
    cfg = repo.config
    out = []
    for rel in sorted(changed):
        if (
            not mutants.language_of(rel)
            or repo.is_test(rel)
            or _under(rel, cfg.model_paths)
            or _under(rel, [e.path for e in cfg.model_exclude])
        ):
            continue
        hit = probe_hit(_post_image(repo, rel, staged))
        if hit:
            out.append(Finding("probe", rel, f"reads like model code ({hit!r}); declare it in "
                               f"model_paths or list it under [[model_exclude]] with a reason"))
    return out


def check(repo: Repo, changed: dict[str, set[int]], wvs, staged: bool) -> list[Finding]:
    findings = _probe(repo, changed, staged) + _golden_findings(repo, changed, staged)
    cfg = repo.config
    if cfg.model_paths:
        findings.extend(_spec_findings(repo, changed))
    unwaivable = {"probe", "golden"}
    return [
        f for f in findings
        if f.check in unwaivable
        or not waivers.finding_waived(wvs, f.check, f.file, f.test, f.ms)
    ]


def _golden_findings(repo: Repo, changed: dict[str, set[int]], staged: bool) -> list[Finding]:
    """Checked when the source or the artefact moved; regenerating is the only fix."""
    out = []
    for g in repo.config.golden:
        if g.source not in changed and g.artifact not in changed:
            continue
        source = _post_image(repo, g.source, staged)
        artifact = _post_image(repo, g.artifact, staged)
        if not source or not artifact:
            raise GateError(f"[[golden]] {g.source} -> {g.artifact}: a file is missing or empty")
        digest = hashlib.sha256(source.encode()).hexdigest()
        if digest not in artifact:
            out.append(Finding("golden", g.artifact,
                               f"does not carry sha256 {digest[:12]}… of {g.source}; regenerate it"))
    return out


def model_changed(repo: Repo, changed: dict[str, set[int]]) -> bool:
    return any(_under(f, repo.config.model_paths) for f in changed)


BLIND_PROMPT = """You are reading the model code of an estimation or tracking system in
isolation. You have the code only: no spec, no tests, no conversation. Do not
ask for them and do not guess at what they say.

Reconstruct, as numbered lines so each can be diffed against a spec you do not
have:
1. Intent — the phenomena modelled, the state vector with units and frame, the
   measurement with units, the time base.
2. Effects the model neglects, each with the order of magnitude at which it
   would matter and the constant or branch in the code that tells you so.
3. The validity envelope the constants, guards, tolerances and singularity
   handling imply — where the model breaks and how you know.

Cite file and line for every claim. Report only; suggest no changes.
"""

BLIND_ISOLATION = ("--strict-mcp-config", "--tools", "Read", "Grep", "Glob")


def build_blind_export(repo: Repo, dest: Path) -> list[str]:
    """model_paths files at their repo-relative paths; no spec, no tests, no .git."""
    copied = []
    for prefix in repo.config.model_paths:
        for src in _files_under(repo.root, prefix):
            rel = src.relative_to(repo.root)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
            copied.append(str(rel))
    return copied


def blind_pass(repo: Repo) -> str:
    with tempfile.TemporaryDirectory(prefix="mutation-gate-blind-") as tmp:
        work = Path(tmp)
        if not build_blind_export(repo, work):
            return "blind pass skipped: model_paths matched no files"
        return adversary.run_isolated("blind pass", BLIND_PROMPT, work, BLIND_ISOLATION)


def _spec_findings(repo: Repo, changed: dict[str, set[int]]) -> list[Finding]:
    spec = load_spec(repo)
    source = spec_source(repo)
    spec_changed = source in changed
    model_changed = [f for f in changed if _under(f, repo.config.model_paths)]
    out: list[Finding] = []
    any_test_touched = False
    for rel in sorted(model_tests(repo)):
        lines = changed.get(rel)
        if lines is None and not spec_changed:
            continue
        for ext in test_extents(repo.root / rel, mutants.language_of(rel) or ""):
            touched = lines is not None and ext.touches(lines)
            if not (touched or spec_changed):
                continue
            any_test_touched |= touched
            cited = ext.citations()
            if touched and not cited:
                out.append(Finding("no-citation", rel, f"{ext.name} cites no MS-n", test=ext.name))
            if spec is None:
                continue
            for n in sorted(cited):
                if n not in spec:
                    out.append(Finding("dangling", rel, f"{ext.name} cites MS-{n}, not in {source}",
                                       test=ext.name, ms=n))
                elif tagged(spec[n]):
                    out.append(Finding("tagged", rel, f"{ext.name} cites MS-{n}, still tagged "
                                       f"{'/'.join(INTENT_TAGS)} — a test against a spec the "
                                       "implementation wrote", test=ext.name, ms=n))
    if spec is None and (model_changed or any_test_touched):
        out.insert(0, Finding("no-spec", model_changed[0] if model_changed else source,
                              f"{source} is absent — draft the skeleton from the code, tag "
                              "every line (needs intent) or (reconstructed), stop for the intent lines"))
    return out


def suggest(repo: Repo, f: Finding) -> str:
    if f.check == "golden":
        return "Regenerate the artefact from its SymPy source; the recorded hash is the only fix."
    if f.check == "probe":
        return (
            f"Declare in {CONFIG_NAME} `model_paths`, or if it is not model code:\n"
            "[[model_exclude]]\n"
            f'path = "{f.file}"\n'
            'reason = "REPLACE ME — why this hit is not model code"\n'
        )
    return (
        f"Fix the spec or the test, or record a waiver in {waivers.path(repo)}:\n"
        + waivers.suggest_finding(f.check, f.file, f.test, f.ms)
    )
