"""Per-file lazy coverage (decisions 25, 26).

No whole-repo map: for each changed file, the transitive import closure gives
candidate tests, one instrumented run narrows them to real coverers, and the
result is cached under the candidate-set blob hashes.
"""

from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path

from . import mutants, runner
from .repo import CACHE_ROOT, Repo, git


def _module_names(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except (SyntaxError, OSError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def _module_path(root: Path, module: str, extra_roots: tuple[Path, ...] = ()) -> Path | None:
    rel = module.replace(".", "/")
    search = (root, *extra_roots)
    for base in search:
        for candidate in (base / f"{rel}.py", base / rel / "__init__.py"):
            if candidate.exists():
                return candidate
    return None


def _resolve_path_expr(node: ast.AST, file_path: Path, names: dict[str, Path]) -> Path | None:
    """`Path(__file__).resolve().parent...`, `.parents[N]`, `NAME / "sub"` chains
    and a `str(...)` wrapper — the shapes a sys.path.insert argument actually
    takes. Anything else is not resolvable statically and yields None, same as
    never having seen the hop."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str":
        return _resolve_path_expr(node.args[0], file_path, names) if node.args else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _resolve_path_expr(node.left, file_path, names)
        if left is None or not (
            isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)
        ):
            return None
        return left / node.right.value
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        owner = _resolve_path_expr(node.value, file_path, names)
        return None if owner is None else owner.parent
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "parents"
    ):
        owner = _resolve_path_expr(node.value.value, file_path, names)
        idx = node.slice
        if owner is None or not (isinstance(idx, ast.Constant) and isinstance(idx.value, int)):
            return None
        for _ in range(idx.value + 1):
            owner = owner.parent
        return owner
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "resolve":
        return _resolve_path_expr(node.func.value, file_path, names)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Path":
        if len(node.args) == 1 and isinstance(node.args[0], ast.Name) and node.args[0].id == "__file__":
            return file_path
        return None
    return None


def _sys_path_roots(path: Path) -> list[Path]:
    """Directories a test adds to sys.path before a bare import, e.g.
    `sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))` then
    `from geo_frame import ...`. Without this the import-closure hop below never
    sees the module — the test imports `geo_frame`, not `tools.geo_frame`."""
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except (SyntaxError, OSError):
        return []
    file_path = path.resolve()
    names: dict[str, Path] = {}
    roots: list[Path] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            resolved = _resolve_path_expr(node.value, file_path, names)
            if resolved is not None:
                names[node.targets[0].id] = resolved
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "insert"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "path"
            and len(node.args) == 2
        ):
            resolved = _resolve_path_expr(node.args[1], file_path, names)
            if resolved is not None:
                roots.append(resolved)
    return roots


def _test_files(repo: Repo, language: str, suffix: str) -> list[Path]:
    out: list[Path] = []
    for tp in repo.config.for_language(language).test_paths:
        base = repo.root / tp
        if base.exists():
            out.extend(sorted(base.rglob(f"test_*{suffix}")))
            out.extend(sorted(base.rglob(f"*_test{suffix}")))
    out.extend(_globbed(repo, language, (suffix,)))
    return sorted(set(out))


def _globbed(repo: Repo, language: str, suffixes: tuple[str, ...]) -> list[Path]:
    return [
        repo.root / rel for rel in repo.glob_tests(language) if rel.endswith(suffixes)
    ]


CPP_SUFFIXES = (".cpp", ".hpp", ".cc", ".h", ".cu", ".cuh")
TS_SUFFIXES = (".ts", ".tsx")


def _ts_test_files(repo: Repo) -> list[Path]:
    """Vitest names tests `*.test.ts(x)`, not `test_*`/`*_test`, so `_test_files`'s
    glob doesn't apply."""
    out: list[Path] = []
    for tp in repo.config.for_language("typescript").test_paths:
        base = repo.root / tp
        if base.exists():
            out.extend(sorted(base.rglob("*.test.ts")))
            out.extend(sorted(base.rglob("*.test.tsx")))
    out.extend(_globbed(repo, "typescript", TS_SUFFIXES))
    return sorted(set(out))


def _by_name(repo: Repo, target: str) -> list[Path]:
    """GDScript has no coverage tool, so the name convention is the only signal
    narrower than the whole suite."""
    tests = _test_files(repo, "gdscript", ".gd")
    stem = Path(target).stem
    named = [t for t in tests if t.stem in (f"{stem}_test", f"test_{stem}")]
    return named or tests


def candidates(repo: Repo, target: str) -> list[Path]:
    """Test files reaching `target` within `closure_depth` import hops.

    Depth 1 (direct import) is the default because unbounded closure selects
    almost the whole suite: a module importing a common `core` is reachable from
    nearly every test, and the instrumented run then costs what the whole-repo
    map of decision 25 exists to avoid. Measured on naval-planner's geometry.py, the 5
    direct importers gave verdicts identical to the full 1318-test tier on all
    14 ground-truth mutants.

    Misses tests that reach code without importing it — subprocess and spawn
    tests. Documented caveat of decision 26, not a defect.
    """
    if target.endswith(".gd"):
        return _by_name(repo, target)
    if target.endswith(CPP_SUFFIXES):
        # Whole suite, no narrowing: a compiled C++ suite runs in seconds, so a
        # name or include heuristic buys nothing and a miss is a false SURVIVED.
        return _test_files(repo, "cpp", ".cpp")
    if target.endswith(TS_SUFFIXES):
        # Same reasoning as C++: a vitest suite this fast (debris-scatter's 125
        # tests run in well under a second) makes narrowing not worth building,
        # and `covering_tests` already treats every non-.py target this way.
        return _ts_test_files(repo)
    target_path = (repo.root / target).resolve()
    config_roots = tuple(repo.root / r for r in repo.config.import_roots)
    hits: list[Path] = []
    for test in _test_files(repo, mutants.language_of(target) or "python", ".py"):
        seen: set[Path] = {test.resolve()}
        frontier, found_it = [test], False
        for _ in range(max(1, repo.config.closure_depth)):
            nxt: list[Path] = []
            for current in frontier:
                extra_roots = (*config_roots, *_sys_path_roots(current))
                for module in _module_names(current):
                    hop = _module_path(repo.root, module, extra_roots)
                    if hop is None or hop.resolve() in seen:
                        continue
                    if hop.resolve() == target_path:
                        found_it = True
                        break
                    seen.add(hop.resolve())
                    nxt.append(hop)
                if found_it:
                    break
            if found_it or not nxt:
                break
            frontier = nxt
        if found_it:
            hits.append(test)
    return hits


def blob_hashes(repo: Repo, paths: list[Path]) -> list[str]:
    rels = [str(p.relative_to(repo.root)) for p in paths]
    if not rels:
        return []
    out = git("hash-object", *rels, cwd=repo.root)
    return sorted(out.split())


def _cache_path(repo: Repo, target: str, fingerprint: str) -> Path:
    safe = target.replace("/", "__")
    return CACHE_ROOT / repo.key / "coverage" / f"{safe}.{fingerprint}.json"


def covering_tests(
    repo: Repo, target: str, cands: list[Path], fingerprint: str
) -> dict[int, list[str]]:
    """line -> test ids that executed it, cached by the candidate-set fingerprint."""
    if not target.endswith(".py"):
        return {}  # coverage.py contexts are the only per-line source there is
    cache = _cache_path(repo, target, fingerprint)
    if cache.exists():
        return {int(k): v for k, v in json.loads(cache.read_text()).items()}

    if not cands:
        return {}
    lang_cfg = repo.config.for_language("python")
    rels = " ".join(str(p.relative_to(repo.root)) for p in cands)
    cmd = lang_cfg.coverage_command.format(file=target, tests=rels)
    # Same suite plus instrumentation, so the baseline cap is the honest bound.
    # Overrunning leaves no contexts, which widens selection to the whole suite.
    runner.run_capped(repo, cmd, repo.config.baseline_timeout)

    mapping = _read_contexts(repo, target, lang_cfg.coverage_data_file)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({str(k): v for k, v in mapping.items()}))
    return mapping


def _numbits_to_lines(numbits: bytes) -> list[int]:
    """Decode coverage.py's per-context line bitmap: byte i, bit j -> source
    line i * 8 + j + 1. Read directly so the host needs no `coverage` install —
    the container that ran the instrumented tests is the only place that
    package belongs (decision behind #49)."""
    return [
        i * 8 + j + 1
        for i, byte in enumerate(numbits)
        for j in range(8)
        if byte & (1 << j)
    ]


def _read_contexts(repo: Repo, target: str, coverage_data_file: str) -> dict[int, list[str]]:
    data_file = repo.root / coverage_data_file
    if not data_file.exists():
        return {}
    target_path = (repo.root / target).resolve()
    con = sqlite3.connect(f"file:{data_file}?mode=ro", uri=True)
    try:
        file_id = next(
            (
                fid
                for fid, path in con.execute("SELECT id, path FROM file")
                if Path(path).resolve() == target_path
            ),
            None,
        )
        if file_id is None:
            return {}
        rows = con.execute(
            "SELECT line_bits.numbits, context.context FROM line_bits "
            "JOIN context ON context.id = line_bits.context_id "
            "WHERE line_bits.file_id = ?",
            (file_id,),
        ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    finally:
        con.close()
    result: dict[int, list[str]] = {}
    for numbits, context in rows:
        if not context:
            continue
        for line in _numbits_to_lines(numbits):
            result.setdefault(line, []).append(context)
    return result
