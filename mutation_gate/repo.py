"""Repo discovery, gating policy, and the fork auto-detection of decision 19."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field, fields
from pathlib import Path

OWN_NAMESPACES_ENV = "MUTATION_GATE_OWN_NAMESPACES"

FORK_REMOTE_NAMES = ("upstream", "fork")

CONFIG_NAME = ".mutation-gate.toml"
WAIVERS_NAME = ".mutation-gate-waivers.toml"

# Outside every work tree and keyed by Repo.key: backups, tokens and the
# coverage cache must survive a run that dies mid-mutant.
CACHE_ROOT = Path.home() / ".cache" / "mutation-gate"


class GateError(RuntimeError):
    pass


def git(*args: str, cwd: Path | None = None) -> str:
    # Inherits git's environment on purpose: under a hook GIT_INDEX_FILE is the
    # index being committed, which --staged must read. Test commands scrub it.
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise GateError(f"git not found on PATH: {exc}") from exc
    if out.returncode != 0:
        raise GateError(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


# Forces `git diff`'s post-image header back to `b/<path>` regardless of
# diff.noprefix or diff.mnemonicPrefix, so every `+++ ` line parser in this
# package can assume one shape (#151, #159).
DIFF_PREFIX_PIN_ARGS = ("--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/")


def post_image_path(field: str) -> str | None:
    field = field.removesuffix("\t")
    if field.startswith('"') and field.endswith('"'):
        field = field[1:-1]
    if field == "/dev/null":
        return None
    if not field.startswith("b/"):
        raise GateError("a diff post-image header did not parse")
    return field[2:]


@dataclass
class LanguageConfig:
    """The five fields a second language in the same repo cannot share with the
    first — how to find its tests, run them, and read their coverage."""

    test_paths: list[str] = field(default_factory=lambda: ["tests"])
    # Repo-root-relative Path.glob patterns, for tests that sit beside their
    # sources: a directory prefix there would ungate the sources too (#66).
    test_globs: list[str] = field(default_factory=list)
    test_command: str = "pytest -q {tests}"
    coverage_command: str = (
        "pytest -q --cov={file} --cov-context=test --cov-report= {tests}"
    )
    coverage_data_file: str = ".coverage"


@dataclass(frozen=True)
class ModelExclude:
    """A probe hit that is not model code. The reason is the tuning record, the
    way a waiver's reason is for the mutant catalogue (dotfiles#56 decision 2)."""

    path: str
    reason: str


@dataclass(frozen=True)
class DocAllow:
    """A new `.md` file the built-in allowlist does not cover. The reason is
    the record, the way a waiver's reason is for the mutant catalogue."""

    glob: str
    reason: str


@dataclass(frozen=True)
class Golden:
    """Layer 3: the generated F/Q artefact must carry the sha256 of the SymPy
    source it was generated from (dotfiles#56 decision 8)."""

    source: str
    artifact: str


@dataclass
class Config:
    enabled: bool = True
    language: str = "python"
    test_paths: list[str] = field(default_factory=lambda: ["tests"])
    test_globs: list[str] = field(default_factory=list)
    test_command: str = "pytest -q {tests}"
    coverage_command: str = (
        "pytest -q --cov={file} --cov-context=test --cov-report= {tests}"
    )
    coverage_data_file: str = ".coverage"
    # Per-language overrides for a repo gating more than one language. A
    # language absent here falls back to the flat fields above, so a
    # single-language repo needs none of this.
    languages: dict[str, LanguageConfig] = field(default_factory=dict)
    # Path prefixes — a directory or a single file — the gate must not touch, and
    # announces on every skip. For code no reachable build compiles: every mutant
    # there survives for want of a build, which reads as a test hole and is not.
    exclude_paths: list[str] = field(default_factory=list)
    # Model-V&V scope (dotfiles#56). Declared, never inferred: a keyword classifier
    # blocks on false positives or misses, both silently. Same prefix semantics
    # as exclude_paths. Tests under model_test_paths must cite a spec line.
    model_paths: list[str] = field(default_factory=list)
    # Where the MS-n lines live: a repo-relative file, or "issue:N" for a GitHub issue
    # of the repo read through `gh` (a repo that keeps its spec in tickets, not files).
    model_spec: str = "docs/model-spec.md"
    model_test_paths: list[str] = field(default_factory=list)
    model_exclude: list[ModelExclude] = field(default_factory=list)
    golden: list[Golden] = field(default_factory=list)
    # Regex the test output must contain for a run to count as green. Empty
    # trusts the exit code, which a runner that never loaded the code also gives.
    pass_pattern: str = ""
    force_gate: bool = False
    # Cap on the unmutated baseline run. Without it a suite that hangs unmutated
    # hangs the gate forever, before a single mutant is measured.
    baseline_timeout: float = 900.0
    # Per-mutant cap, when the derived one is wrong. The gate scales it from the
    # baseline, which is right only where a mutant costs what the baseline cost;
    # where a build sits between the edit and the tests it does not (#78).
    mutant_timeout: float | None = None
    # Import hops from a test to the mutated file. 1 = direct import; raising it
    # selects nearly the whole suite once a common module sits in the path.
    closure_depth: int = 1
    # Extra import roots, repo-root-relative, for a src layout whose PYTHONPATH
    # comes from pytest.ini/pyproject rather than a test file's sys.path.insert.
    import_roots: list[str] = field(default_factory=list)
    # Block on a comment line the diff added (#100, decision 5 of #93). Opt-in:
    # work repos and forks keep their comments (decision 29).
    no_comments: bool = False
    vocabulary: str = ""
    vocabulary_molds: dict[str, list[str]] = field(default_factory=dict)
    vocabulary_synonyms: str = "report"
    own_namespaces: list[str] = field(default_factory=list)
    doc_allow: list[DocAllow] = field(default_factory=list)
    banned_names_file: str = ""

    def for_language(self, language: str) -> LanguageConfig:
        override = self.languages.get(language)
        if override is not None:
            return override
        return LanguageConfig(
            test_paths=self.test_paths,
            test_globs=self.test_globs,
            test_command=self.test_command,
            coverage_command=self.coverage_command,
            coverage_data_file=self.coverage_data_file,
        )

    @classmethod
    def load(cls, root: Path) -> Config:
        path = root / CONFIG_NAME
        if not path.exists():
            return cls()
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
        raw = dict(raw)
        languages = _load_languages(raw.pop("languages", {}))
        model_exclude = _load_model_exclude(raw.pop("model_exclude", []))
        golden = _load_golden(raw.pop("golden", []))
        doc_allow = _load_doc_allow(raw.pop("doc_allow", []))
        # Named, not silently dropped: a key that does nothing is how a repo
        # believes it is scoping the gate while the gate ignores it.
        nested = {"languages", "model_exclude", "golden", "doc_allow"}
        unknown = sorted(set(raw) - {f.name for f in fields(cls) if f.name not in nested})
        if unknown:
            raise GateError(
                f"{CONFIG_NAME}: unknown key(s) {', '.join(unknown)} — delete them; "
                "nothing reads them. Scope the gate with exclude_paths."
            )
        return cls(**raw, languages=languages, model_exclude=model_exclude, golden=golden,
                   doc_allow=doc_allow)

    def test_prefixes(self) -> set[str]:
        paths = set(self.test_paths)
        for lang_cfg in self.languages.values():
            paths.update(lang_cfg.test_paths)
        return paths

    def glob_patterns(self) -> set[str]:
        pats = set(self.test_globs)
        for lang_cfg in self.languages.values():
            pats.update(lang_cfg.test_globs)
        return pats


def own_namespaces(config: Config) -> tuple[str, ...]:
    from_env = tuple(ns for ns in os.environ.get(OWN_NAMESPACES_ENV, "").split(":") if ns)
    return from_env or tuple(config.own_namespaces)


def _load_model_exclude(raw: list) -> list[ModelExclude]:
    out: list[ModelExclude] = []
    for entry in raw:
        if not entry.get("path") or not entry.get("reason"):
            raise GateError(
                f"{CONFIG_NAME}: every [[model_exclude]] needs `path` and a `reason` "
                "naming why the probe hit is not model code"
            )
        out.append(ModelExclude(path=entry["path"], reason=entry["reason"]))
    return out


def _load_doc_allow(raw: list) -> list[DocAllow]:
    out: list[DocAllow] = []
    for entry in raw:
        if not entry.get("glob") or not entry.get("reason"):
            raise GateError(
                f"{CONFIG_NAME}: every [[doc_allow]] needs `glob` and a `reason` "
                "naming why these new docs are allowed"
            )
        out.append(DocAllow(glob=entry["glob"], reason=entry["reason"]))
    return out


def _load_golden(raw: list) -> list[Golden]:
    out: list[Golden] = []
    for entry in raw:
        if set(entry) != {"source", "artifact"}:
            raise GateError(
                f"{CONFIG_NAME}: every [[golden]] needs exactly `source` and `artifact`"
            )
        out.append(Golden(source=entry["source"], artifact=entry["artifact"]))
    return out


def _load_languages(raw: dict) -> dict[str, LanguageConfig]:
    known = {f.name for f in fields(LanguageConfig)}
    languages: dict[str, LanguageConfig] = {}
    for name, sub in raw.items():
        unknown = sorted(set(sub) - known)
        if unknown:
            raise GateError(
                f"{CONFIG_NAME}: languages.{name} unknown key(s) {', '.join(unknown)} — "
                "delete them; nothing reads them."
            )
        languages[name] = LanguageConfig(**sub)
    return languages


@dataclass
class Repo:
    root: Path
    origin: str
    remotes: tuple[str, ...]
    config: Config

    @property
    def key(self) -> str:
        return hashlib.sha256(str(self.root).encode()).hexdigest()[:16]

    def glob_tests(self, language: str) -> set[str]:
        return self._expand(self.config.for_language(language).test_globs)

    def is_test(self, rel: str) -> bool:
        cfg = self.config
        if any(rel.startswith(f"{tp}/") for tp in cfg.test_prefixes()):
            return True
        return rel in self._expand(cfg.glob_patterns())

    def _expand(self, patterns: Iterable[str]) -> set[str]:
        """Path.glob, never fnmatch: discovery and is_test must agree on what a
        pattern means, and fnmatch's `*` crosses directories where glob's does not."""
        return {
            str(p.relative_to(self.root))
            for pat in patterns
            for p in self.root.glob(pat)
            if p.is_file()
        }

    @property
    def fork_signal(self) -> str | None:
        """Why this checkout is not ours to gate, or None if it is."""
        namespaces = own_namespaces(self.config)
        if self.origin and namespaces and not any(ns in self.origin for ns in namespaces):
            return f"origin {self.origin} is outside your namespaces"
        for name in FORK_REMOTE_NAMES:
            if name in self.remotes:
                return f"a remote named '{name}' exists (fork of an upstream)"
        return None


def discover(cwd: Path | None = None) -> Repo:
    cwd = cwd or Path.cwd()
    root = Path(git("rev-parse", "--show-toplevel", cwd=cwd).strip())
    remotes = tuple(r for r in git("remote", cwd=root).split() if r)
    origin = ""
    if "origin" in remotes:
        origin = git("remote", "get-url", "origin", cwd=root).strip()
    return Repo(root=root, origin=origin, remotes=remotes, config=Config.load(root))


def skip_reason(repo: Repo) -> str | None:
    """Announced on every skip — a silent ungating is the only failure that hurts."""
    if not repo.config.enabled:
        return f"{repo.root.name} is opted out in {CONFIG_NAME}"
    if repo.config.force_gate:
        return None
    return repo.fork_signal
