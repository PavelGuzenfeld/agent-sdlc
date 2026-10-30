"""Intent: a test importing its target via sys.path.insert + a bare name — the
pattern every live-action Python test uses — must still be found as a
candidate.

Also: _read_contexts must read a coverage.py SQLite data file with stdlib
sqlite3 alone — the host running the gate has no `coverage` install by design
(Docker-only host). dotfiles#49.

Also: a src-layout repo whose PYTHONPATH comes from pytest.ini rather than a
test file's own sys.path.insert needs `import_roots` in .mutation-gate.toml
to resolve the same bare import. PavelGuzenfeld/debris-scatter#48."""

import os
import shlex
import sqlite3
import sys
import time
from types import SimpleNamespace

import pytest

from mutation_gate import cli, coverage_map, runner, token
from mutation_gate.repo import Config, LanguageConfig, Repo


def _write_coverage_db(path, file_path, context_lines):
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE IF NOT EXISTS file (id integer primary key, path text, unique(path))"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS context (id integer primary key, context text, unique(context))"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS line_bits (file_id integer, context_id integer, numbits blob, "
        "unique(file_id, context_id))"
    )
    con.execute("INSERT INTO file (path) VALUES (?)", (file_path,))
    file_id = con.execute("SELECT id FROM file WHERE path = ?", (file_path,)).fetchone()[0]
    for context, lines in context_lines.items():
        con.execute("INSERT OR IGNORE INTO context (context) VALUES (?)", (context,))
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

    with pytest.raises(coverage_map.EmptyCoverageError, match=r"^no row in the data file matches geo_frame\.py$"):
        coverage_map._read_contexts(repo, "geo_frame.py", ".coverage")


def test_read_contexts_maps_a_mount_path_row_whose_components_end_in_the_target(tmp_path):
    (tmp_path / ".git").mkdir()
    _write_coverage_db(tmp_path / ".coverage", "/repo/xpkg/mod.py", {"t::wrong": [1]})
    _write_coverage_db(tmp_path / ".coverage", "/repo/pkg/mod.py", {"t::right": [2]})
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())

    assert coverage_map._read_contexts(repo, "pkg/mod.py", ".coverage") == {2: ["t::right"]}


def test_read_contexts_prefers_the_host_row_over_a_mount_path_row(tmp_path):
    (tmp_path / ".git").mkdir()
    host = str((tmp_path / "pkg" / "mod.py").resolve())
    _write_coverage_db(tmp_path / ".coverage", "/repo/pkg/mod.py", {"t::mount": [1]})
    _write_coverage_db(tmp_path / ".coverage", host, {"t::host": [2]})
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())

    assert coverage_map._read_contexts(repo, "pkg/mod.py", ".coverage") == {2: ["t::host"]}


def test_read_contexts_returns_empty_when_two_mount_path_rows_end_in_the_target(tmp_path):
    (tmp_path / ".git").mkdir()
    _write_coverage_db(tmp_path / ".coverage", "/repo/mod.py", {"t::root": [1]})
    _write_coverage_db(tmp_path / ".coverage", "/repo/pkg/mod.py", {"t::pkg": [2]})
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())

    with pytest.raises(coverage_map.EmptyCoverageError, match=r"^2 rows in the data file end in mod\.py$"):
        coverage_map._read_contexts(repo, "mod.py", ".coverage")


def test_read_contexts_returns_empty_when_data_file_is_missing(tmp_path):
    (tmp_path / ".git").mkdir()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())

    with pytest.raises(coverage_map.EmptyCoverageError, match=r"^no data file at \.coverage$"):
        coverage_map._read_contexts(repo, "geo_frame.py", ".coverage")


def test_read_contexts_names_a_data_file_that_is_not_a_coverage_database(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".coverage").write_text("not sqlite\n")
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())

    with pytest.raises(
        coverage_map.EmptyCoverageError, match=r"^\.coverage is not a readable coverage database$"
    ):
        coverage_map._read_contexts(repo, "geo_frame.py", ".coverage")


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

    with pytest.raises(coverage_map.EmptyCoverageError, match=r"^no data file at \.coverage$"):
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


def test_file_run_narrows_coverage_recorded_under_a_container_mount_path(
    tmp_path, monkeypatch
):
    root = tmp_path / "host"
    mount = tmp_path / "mount"
    ran = tmp_path / "ran.log"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "mod.py").write_text("def f():\n    return 1\n\n\ndef g():\n    return 2\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_mod.py").write_text(
        "from pkg.mod import f, g\n\n\ndef test_f():\n    assert f() == 1\n\n\n"
        "def test_g():\n    assert g() == 2\n"
    )
    python = shlex.quote(sys.executable)
    (root / ".mutation-gate.toml").write_text(
        "force_gate = true\n"
        f"test_command = 'echo {{tests}} >> {ran} && "
        f"{python} -m pytest -q -p no:cacheprovider {{tests}}'\n"
        f"coverage_command = 'rm -rf {mount} && cp -r . {mount} && cd {mount} && "
        f"COVERAGE_FILE={root}/.coverage {python} -m pytest -q -p no:cacheprovider "
        "--cov={file} --cov-context=test --cov-report= {tests}'\n"
    )
    (root / ".git").mkdir()
    repo = Repo(root=root, origin="", remotes=(), config=Config.load(root))
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(coverage_map, "git", lambda cmd, *rels, cwd: "\n".join(rels))
    for mod in (cli, coverage_map, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")

    code = cli.main(["--file", "pkg/mod.py", "--lines", "2", "--no-adversary"])

    baseline, *per_mutant = ran.read_text().splitlines()
    assert code == 0
    assert baseline == "tests/test_mod.py"
    assert per_mutant and set(per_mutant) == {"tests/test_mod.py::test_f"}


def test_file_run_widens_to_all_candidates_when_the_coverage_run_fails_over_a_stale_data_file(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "host"
    ran = tmp_path / "ran.log"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "mod.py").write_text("def f():\n    return 1\n\n\ndef g():\n    return 2\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_mod.py").write_text(
        "from pkg.mod import f, g\n\n\ndef test_f():\n    assert f() == 1\n\n\n"
        "def test_g():\n    assert g() == 2\n"
    )
    python = shlex.quote(sys.executable)
    (root / ".mutation-gate.toml").write_text(
        "force_gate = true\n"
        f"test_command = 'echo {{tests}} >> {ran} && "
        f"{python} -m pytest -q -p no:cacheprovider {{tests}}'\n"
        "coverage_command = 'false {file} {tests}'\n"
    )
    _write_coverage_db(root / ".coverage", "/repo/pkg/mod.py", {"tests/test_mod.py::test_g|run": [2]})
    (root / ".git").mkdir()
    repo = Repo(root=root, origin="", remotes=(), config=Config.load(root))
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(coverage_map, "git", lambda cmd, *rels, cwd: "\n".join(rels))
    for mod in (cli, coverage_map, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")

    code = cli.main(["--file", "pkg/mod.py", "--lines", "2", "--no-adversary"])

    _, *per_mutant = ran.read_text().splitlines()
    assert per_mutant and set(per_mutant) == {"tests/test_mod.py"}
    assert code == 0
    assert (
        "pkg/mod.py: coverage came back empty (the coverage run failed)" in capsys.readouterr().err
    )
    coverage_cache = coverage_map._cache_path(repo, "pkg/mod.py", "any").parent
    assert not coverage_cache.exists() or not any(coverage_cache.iterdir())


def test_file_run_names_a_path_mismatch_as_the_reason_coverage_came_back_empty(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "host"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "mod.py").write_text("def f():\n    return 1\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_mod.py").write_text(
        "from pkg.mod import f\n\n\ndef test_f():\n    assert f() == 1\n"
    )
    python = shlex.quote(sys.executable)
    (root / ".mutation-gate.toml").write_text(
        "force_gate = true\n"
        f"test_command = '{python} -m pytest -q -p no:cacheprovider {{tests}}'\n"
        "coverage_command = 'true {file} {tests}'\n"
    )
    _write_coverage_db(root / ".coverage", "/repo/lib/mod.py", {"tests/test_mod.py::test_f|run": [2]})
    (root / ".git").mkdir()
    repo = Repo(root=root, origin="", remotes=(), config=Config.load(root))
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(coverage_map, "git", lambda cmd, *rels, cwd: "\n".join(rels))
    for mod in (cli, coverage_map, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")

    cli.main(["--file", "pkg/mod.py", "--lines", "2", "--no-adversary"])

    notices = [line for line in capsys.readouterr().err.splitlines() if "coverage came back empty" in line]
    assert notices == [
        "  pkg/mod.py: coverage came back empty (no row in the data file matches pkg/mod.py)"
        " — every mutant runs against all candidate tests"
    ]


def test_file_run_widens_to_all_candidates_when_a_passing_coverage_run_leaves_a_stale_data_file(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "host"
    ran = tmp_path / "ran.log"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "mod.py").write_text("def f():\n    return 1\n\n\ndef g():\n    return 2\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_mod.py").write_text(
        "from pkg.mod import f, g\n\n\ndef test_f():\n    assert f() == 1\n\n\n"
        "def test_g():\n    assert g() == 2\n"
    )
    python = shlex.quote(sys.executable)
    (root / ".mutation-gate.toml").write_text(
        "force_gate = true\n"
        f"test_command = 'echo {{tests}} >> {ran} && "
        f"{python} -m pytest -q -p no:cacheprovider {{tests}}'\n"
        "coverage_command = 'true {file} {tests}'\n"
    )
    _write_coverage_db(root / ".coverage", "/repo/pkg/mod.py", {"tests/test_mod.py::test_g|run": [2]})
    an_hour_ago = time.time() - 3600
    os.utime(root / ".coverage", (an_hour_ago, an_hour_ago))
    (root / ".git").mkdir()
    repo = Repo(root=root, origin="", remotes=(), config=Config.load(root))
    monkeypatch.setattr(cli, "discover", lambda cwd=None: repo)
    monkeypatch.setattr(coverage_map, "git", lambda cmd, *rels, cwd: "\n".join(rels))
    for mod in (cli, coverage_map, runner, token):
        monkeypatch.setattr(mod, "CACHE_ROOT", tmp_path / "cache")

    code = cli.main(["--file", "pkg/mod.py", "--lines", "2", "--no-adversary"])

    _, *per_mutant = ran.read_text().splitlines()
    assert per_mutant and set(per_mutant) == {"tests/test_mod.py"}
    assert code == 0
    notices = [line for line in capsys.readouterr().err.splitlines() if "coverage came back empty" in line]
    assert notices == [
        "  pkg/mod.py: coverage came back empty (.coverage predates this coverage run)"
        " — every mutant runs against all candidate tests"
    ]
    coverage_cache = coverage_map._cache_path(repo, "pkg/mod.py", "any").parent
    assert not coverage_cache.exists() or not any(coverage_cache.iterdir())


def test_numbits_to_lines_decodes_the_coveragepy_bit_layout_across_bytes():
    assert coverage_map._numbits_to_lines(b"\x02\x04") == [1, 10]


def test_covering_tests_recomputes_after_the_cache_version_bumps(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "mod.py"
    target.write_text("def f():\n    pass\n")
    test_file = tmp_path / "tests" / "test_mod.py"
    test_file.parent.mkdir()
    test_file.write_text("from pkg import mod\n")
    (tmp_path / ".git").mkdir()
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    monkeypatch.setattr(coverage_map, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(coverage_map, "_CACHE_VERSION", "1")
    monkeypatch.setattr(
        coverage_map.runner, "run_capped", lambda repo, cmd, timeout: coverage_map.runner.PASSED
    )
    monkeypatch.setattr(
        coverage_map, "_read_contexts",
        lambda repo, target, data_file: {1: ["tests/test_mod.py::test_old"]},
    )
    coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")

    monkeypatch.setattr(coverage_map, "_CACHE_VERSION", "2")
    monkeypatch.setattr(
        coverage_map, "_read_contexts",
        lambda repo, target, data_file: {2: ["tests/test_mod.py::test_new"]},
    )
    mapping = coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")

    assert mapping == {2: ["tests/test_mod.py::test_new"]}


def test_covering_tests_retries_a_run_that_came_back_empty(tmp_path, monkeypatch):
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
    monkeypatch.setattr(coverage_map, "_read_contexts", lambda repo, target, data_file: {})

    for _ in range(2):
        with pytest.raises(
            coverage_map.EmptyCoverageError, match=r"^no test recorded a line of pkg/mod\.py$"
        ):
            coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")

    assert len(calls) == 2
    cache_dir = tmp_path / "cache" / repo.key / "coverage"
    assert not cache_dir.exists() or not any(cache_dir.iterdir())


def test_covering_tests_retries_a_run_that_timed_out(tmp_path, monkeypatch):
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
        lambda repo, cmd, timeout: calls.append(1) or coverage_map.runner.TIMED_OUT,
    )
    monkeypatch.setattr(
        coverage_map, "_read_contexts",
        lambda repo, target, data_file: {2: ["tests/test_mod.py::test_f"]},
    )

    for _ in range(2):
        with pytest.raises(coverage_map.EmptyCoverageError, match=r"^the coverage run timed out$"):
            coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")

    assert len(calls) == 2
    cache_dir = tmp_path / "cache" / repo.key / "coverage"
    assert not cache_dir.exists() or not any(cache_dir.iterdir())


def _covering_tests_over_a_data_file_last_written_at(tmp_path, monkeypatch, mtime):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "mod.py"
    target.write_text("def f():\n    return 1\n")
    test_file = tmp_path / "tests" / "test_mod.py"
    test_file.parent.mkdir()
    test_file.write_text("from pkg import mod\n")
    (tmp_path / ".git").mkdir()
    _write_coverage_db(tmp_path / ".coverage", str(target), {"tests/test_mod.py::test_f|run": [2]})
    os.utime(tmp_path / ".coverage", (mtime, mtime))
    repo = Repo(root=tmp_path, origin="", remotes=(), config=Config())
    monkeypatch.setattr(coverage_map, "CACHE_ROOT", tmp_path / "cache")
    clock = SimpleNamespace(now=1000.0)

    def run_lasting_a_hundred_seconds(repo, cmd, timeout):
        clock.now += 100.0
        return runner.PASSED

    monkeypatch.setattr(coverage_map.runner, "run_capped", run_lasting_a_hundred_seconds)
    monkeypatch.setattr(coverage_map, "time", SimpleNamespace(time=lambda: clock.now))
    return coverage_map.covering_tests(repo, "pkg/mod.py", [test_file], "fp")


def test_covering_tests_reads_a_data_file_stamped_two_seconds_before_the_run_start(
    tmp_path, monkeypatch
):
    """FAT stamps mtime in 2 s steps and Linux from a clock that trails time.time(), so a
    file the run wrote can read up to 2 s older than the run start; the cost is that a
    stale file written under 2 s before the run is read as this run's."""
    mapping = _covering_tests_over_a_data_file_last_written_at(tmp_path, monkeypatch, 998.0)

    assert mapping == {2: ["tests/test_mod.py::test_f|run"]}


def test_covering_tests_names_a_data_file_stamped_over_two_seconds_before_the_run_start(
    tmp_path, monkeypatch
):
    with pytest.raises(
        coverage_map.EmptyCoverageError, match=r"^\.coverage predates this coverage run$"
    ):
        _covering_tests_over_a_data_file_last_written_at(tmp_path, monkeypatch, 997.984375)

    assert not list((tmp_path / "cache").rglob("*.json"))


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


@pytest.mark.parametrize(
    "payload",
    ["; touch injected", "$(touch injected)", "`touch injected`", " && touch injected", "'; touch injected"],
)
def test_a_candidate_path_with_shell_syntax_reaches_the_coverage_run_as_one_word(
    tmp_path, monkeypatch, payload
):
    monkeypatch.setattr(coverage_map, "CACHE_ROOT", tmp_path / "cache")
    candidate = tmp_path / "tests" / f"test_a{payload}.py"
    argv = tmp_path / "argv"
    repo = Repo(
        root=tmp_path, origin="", remotes=(),
        config=Config(coverage_command=f"printf '%s\\n' {{tests}} > {argv}"),
    )
    with pytest.raises(coverage_map.EmptyCoverageError):
        coverage_map.covering_tests(repo, "pkg/mod.py", [candidate], "fp")
    assert not (tmp_path / "injected").exists()
    assert argv.read_text() == f"tests/test_a{payload}.py\n"
