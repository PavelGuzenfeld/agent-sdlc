"""Intent: a test importing its target via sys.path.insert + a bare name — the
pattern every live-action Python test uses — must still be found as a
candidate.

Also: _read_contexts must read a coverage.py SQLite data file with stdlib
sqlite3 alone — the host running the gate has no `coverage` install by design
(Docker-only host). dotfiles#49.

Also: a src-layout repo whose PYTHONPATH comes from pytest.ini rather than a
test file's own sys.path.insert needs `import_roots` in .mutation-gate.toml
to resolve the same bare import. PavelGuzenfeld/debris-scatter#48."""

import shlex
import sqlite3
import sys

from mutation_gate import coverage_map
from mutation_gate.repo import Config, LanguageConfig, Repo


def _write_coverage_db(path, file_path, context_lines):
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE file (id integer primary key, path text, unique(path))")
    con.execute("CREATE TABLE context (id integer primary key, context text, unique(context))")
    con.execute(
        "CREATE TABLE line_bits (file_id integer, context_id integer, numbits blob, "
        "unique(file_id, context_id))"
    )
    con.execute("INSERT INTO file (path) VALUES (?)", (file_path,))
    file_id = con.execute("SELECT id FROM file WHERE path = ?", (file_path,)).fetchone()[0]
    for context, lines in context_lines.items():
        con.execute("INSERT INTO context (context) VALUES (?)", (context,))
        context_id = con.execute(
            "SELECT id FROM context WHERE context = ?", (context,)
        ).fetchone()[0]
        numbits = bytearray((max(lines) // 8) + 1) if lines else bytearray()
        for line in lines:
            numbits[line // 8] |= 1 << (line % 8)
        con.execute(
            "INSERT INTO line_bits (file_id, context_id, numbits) VALUES (?, ?, ?)",
            (file_id, context_id, bytes(numbits)),
        )
    con.commit()
    con.close()


def test_sys_path_roots_resolves_parent_chain_and_literal_join(tmp_path):
    test_file = tmp_path / "tests" / "test_geo_frame.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        'import sys\n'
        'from pathlib import Path\n'
        'sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))\n'
    )
    assert coverage_map._sys_path_roots(test_file) == [tmp_path / "tools"]


def test_sys_path_roots_resolves_named_variable_and_parents_subscript(tmp_path):
    test_file = tmp_path / "tests" / "test_config.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        'import sys\n'
        'from pathlib import Path\n'
        'REPO = Path(__file__).resolve().parents[1]\n'
        'sys.path.insert(0, str(REPO / "tools" / "px4_sitl"))\n'
    )
    assert coverage_map._sys_path_roots(test_file) == [tmp_path / "tools" / "px4_sitl"]


def test_module_path_without_extra_root_misses_a_bare_sys_path_import(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "geo_frame.py").write_text("")
    assert coverage_map._module_path(tmp_path, "geo_frame") is None
    assert (
        coverage_map._module_path(tmp_path, "geo_frame", (tmp_path / "tools",))
        == tmp_path / "tools" / "geo_frame.py"
    )


def test_candidates_finds_a_test_that_imports_via_sys_path_hack(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "geo_frame.py").write_text("def geo_to_local(): pass\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_geo_frame.py"
    test_file.write_text(
        'import sys\n'
        'from pathlib import Path\n'
        'sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))\n'
        'from geo_frame import geo_to_local\n'
    )
    (tmp_path / ".git").mkdir()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())

    assert coverage_map.candidates(repo, "tools/geo_frame.py") == [test_file]


def test_candidates_finds_a_colocated_vitest_test_declared_only_by_glob(tmp_path):
    lib = tmp_path / "web" / "lib"
    lib.mkdir(parents=True)
    (lib / "decimate.ts").write_text("export function decimate() {}\n")
    colocated = lib / "decimate.test.ts"
    colocated.write_text("import { decimate } from './decimate';\n")
    (tmp_path / ".git").mkdir()
    config = Config(
        languages={"typescript": LanguageConfig(test_paths=[], test_globs=["web/lib/*.test.ts"])}
    )
    repo = Repo(root=tmp_path, origin="", remotes=(), config=config)

    assert coverage_map.candidates(repo, "web/lib/decimate.ts") == [colocated]


def test_candidates_for_a_ts_target_is_the_whole_vitest_suite_unnarrowed(tmp_path):
    web = tmp_path / "web"
    (web / "lib").mkdir(parents=True)
    (web / "lib" / "decimate.ts").write_text("export function decimate() {}\n")
    tests_dir = web / "tests"
    tests_dir.mkdir()
    matching = tests_dir / "decimate.test.ts"
    matching.write_text("import { decimate } from '../lib/decimate';\n")
    unrelated = tests_dir / "format.test.ts"
    unrelated.write_text("test('unrelated', () => {});\n")
    (tmp_path / ".git").mkdir()
    config = Config(languages={"typescript": LanguageConfig(test_paths=["web/tests"])})
    repo = Repo(root=tmp_path, origin="", remotes=(), config=config)

    assert coverage_map.candidates(repo, "web/lib/decimate.ts") == [matching, unrelated]


def test_candidates_finds_a_test_via_a_configured_import_root(tmp_path):
    (tmp_path / "sim" / "debris_scatter").mkdir(parents=True)
    target = tmp_path / "sim" / "debris_scatter" / "wind.py"
    target.write_text("def band_vector(): pass\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_wind.py"
    test_file.write_text("from debris_scatter import wind\n")
    (tmp_path / ".git").mkdir()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config(import_roots=["sim"]))

    assert coverage_map.candidates(repo, "sim/debris_scatter/wind.py") == [test_file]


def test_read_contexts_maps_lines_to_test_ids_and_drops_the_empty_context(tmp_path):
    target = tmp_path / "geo_frame.py"
    target.write_text("def geo_to_local():\n    pass\n")
    (tmp_path / ".git").mkdir()
    _write_coverage_db(
        tmp_path / ".coverage",
        str(target.resolve()),
        {"tests/test_geo_frame.py::test_a": [1, 2], "": [1]},
    )
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())

    result = coverage_map._read_contexts(repo, "geo_frame.py", ".coverage")

    assert result == {
        1: ["tests/test_geo_frame.py::test_a"],
        2: ["tests/test_geo_frame.py::test_a"],
    }


def test_read_contexts_returns_empty_for_a_file_the_data_never_measured(tmp_path):
    target = tmp_path / "geo_frame.py"
    target.write_text("def geo_to_local():\n    pass\n")
    (tmp_path / ".git").mkdir()
    _write_coverage_db(
        tmp_path / ".coverage", str((tmp_path / "other.py").resolve()), {"t": [1]}
    )
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())

    assert coverage_map._read_contexts(repo, "geo_frame.py", ".coverage") == {}


def test_read_contexts_returns_empty_when_data_file_is_missing(tmp_path):
    (tmp_path / ".git").mkdir()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())

    assert coverage_map._read_contexts(repo, "geo_frame.py", ".coverage") == {}


def test_covering_tests_scopes_cov_to_the_targets_directory_not_the_file(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "mod.py"
    target.write_text("def f():\n    pass\n")
    test_file = tmp_path / "tests" / "test_mod.py"
    test_file.parent.mkdir()
    test_file.write_text("from pkg import mod\n")
    (tmp_path / ".git").mkdir()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    monkeypatch.setattr(coverage_map, "CACHE_ROOT", tmp_path / "cache")
    seen = {}
    monkeypatch.setattr(
        coverage_map.runner, "run_capped", lambda repo, cmd, timeout: seen.setdefault("cmd", cmd)
    )

    coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")

    assert "--cov=pkg " in seen["cmd"]
    assert "--cov=pkg/mod.py" not in seen["cmd"]


def test_covering_tests_collects_a_real_per_test_context_for_the_target(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    target = tmp_path / "pkg" / "mod.py"
    target.write_text("def f():\n    return 1\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_mod.py"
    test_file.write_text("from pkg.mod import f\n\n\ndef test_f():\n    assert f() == 1\n")
    (tmp_path / ".git").mkdir()
    config = Config(
        coverage_command=(
            f"{shlex.quote(sys.executable)} -m pytest -q -p no:cacheprovider --cov={{file}} "
            "--cov-context=test --cov-report= {tests}"
        )
    )
    repo = Repo(root=tmp_path, origin="", remotes=(), config=config)
    monkeypatch.setattr(coverage_map, "CACHE_ROOT", tmp_path / "cache")

    mapping = coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")

    assert mapping == {2: ["tests/test_mod.py::test_f|run"]}


def test_numbits_to_lines_decodes_the_coveragepy_bit_layout_across_bytes():
    assert coverage_map._numbits_to_lines(b"\x02\x04") == [1, 10]


def test_covering_tests_ignores_a_stale_version_cache_entry(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "mod.py"
    target.write_text("def f():\n    pass\n")
    test_file = tmp_path / "tests" / "test_mod.py"
    test_file.parent.mkdir()
    test_file.write_text("from pkg import mod\n")
    (tmp_path / ".git").mkdir()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    monkeypatch.setattr(coverage_map, "CACHE_ROOT", tmp_path / "cache")
    stale = tmp_path / "cache" / repo.key / "coverage" / "pkg__mod.py.fp.json"
    stale.parent.mkdir(parents=True)
    stale.write_text('{"1": ["stale::test"]}')
    monkeypatch.setattr(
        coverage_map.runner, "run_capped", lambda repo, cmd, timeout: coverage_map.runner.PASSED
    )
    monkeypatch.setattr(
        coverage_map, "_read_contexts",
        lambda repo, target, data_file: {2: ["tests/test_mod.py::test_f"]},
    )

    mapping = coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")

    assert mapping == {2: ["tests/test_mod.py::test_f"]}


def test_covering_tests_does_not_persist_an_empty_mapping(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "mod.py"
    target.write_text("def f():\n    pass\n")
    test_file = tmp_path / "tests" / "test_mod.py"
    test_file.parent.mkdir()
    test_file.write_text("from pkg import mod\n")
    (tmp_path / ".git").mkdir()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    monkeypatch.setattr(coverage_map, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(
        coverage_map.runner, "run_capped", lambda repo, cmd, timeout: coverage_map.runner.PASSED
    )
    monkeypatch.setattr(coverage_map, "_read_contexts", lambda repo, target, data_file: {})

    mapping = coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")

    assert mapping == {}
    cache_dir = tmp_path / "cache" / repo.key / "coverage"
    assert not cache_dir.exists() or not any(cache_dir.iterdir())


def test_covering_tests_does_not_persist_a_timed_out_run(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "mod.py"
    target.write_text("def f():\n    pass\n")
    test_file = tmp_path / "tests" / "test_mod.py"
    test_file.parent.mkdir()
    test_file.write_text("from pkg import mod\n")
    (tmp_path / ".git").mkdir()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    monkeypatch.setattr(coverage_map, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(
        coverage_map.runner, "run_capped", lambda repo, cmd, timeout: coverage_map.runner.TIMED_OUT
    )
    monkeypatch.setattr(
        coverage_map, "_read_contexts",
        lambda repo, target, data_file: {2: ["tests/test_mod.py::test_f"]},
    )

    coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")

    cache_dir = tmp_path / "cache" / repo.key / "coverage"
    assert not cache_dir.exists() or not any(cache_dir.iterdir())


def test_covering_tests_hits_the_cache_on_a_repeat_call(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "mod.py"
    target.write_text("def f():\n    pass\n")
    test_file = tmp_path / "tests" / "test_mod.py"
    test_file.parent.mkdir()
    test_file.write_text("from pkg import mod\n")
    (tmp_path / ".git").mkdir()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    monkeypatch.setattr(coverage_map, "CACHE_ROOT", tmp_path / "cache")
    calls = []
    monkeypatch.setattr(
        coverage_map.runner,
        "run_capped",
        lambda repo, cmd, timeout: calls.append(1) or coverage_map.runner.PASSED,
    )
    monkeypatch.setattr(
        coverage_map, "_read_contexts",
        lambda repo, target, data_file: {2: ["tests/test_mod.py::test_f"]},
    )

    first = coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")
    second = coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")

    assert first == second == {2: ["tests/test_mod.py::test_f"]}
    assert len(calls) == 1
