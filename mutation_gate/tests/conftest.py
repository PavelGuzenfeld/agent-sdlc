import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mutation_gate import mutants  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_ast_grep_ready_cache():
    mutants._ast_grep_ready.cache_clear()


@pytest.fixture(autouse=True)
def _ast_grep_version_matches_the_pin_by_default(monkeypatch):
    real_run = mutants.subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["ast-grep", "--version"]:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=f"ast-grep {mutants.PINNED_AST_GREP_VERSION}\n", stderr=""
            )
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(mutants.subprocess, "run", fake_run)


GDSCRIPT_LIB = Path.home() / ".local" / "share" / "ast-grep" / "gdscript.so"
GDSCRIPT_SGCONFIG = (
    "customLanguages:\n  gdscript:\n    libraryPath: " + str(GDSCRIPT_LIB) +
    "\n    extensions: [gd]\n    expandoChar: _\n"
)
GDSCRIPT_BROKEN_SGCONFIG = (
    "customLanguages:\n  gdscript:\n    libraryPath: /nonexistent/gdscript.so\n"
    "    extensions: [gd]\n    expandoChar: _\n"
)


def require_gdscript_parser() -> None:
    if not GDSCRIPT_LIB.exists():
        pytest.skip(f"gdscript parser not installed at {GDSCRIPT_LIB} (bin/install-gdscript-parser)")


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    record = tmp_path / "claude-argv"
    config = tmp_path / "claude-config"
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    exe = bin_dir / "claude"
    exe.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\0' \"$@\" > '{record}'\n"
        f"mkdir -p '{config}/projects/'\"$(printf '%s' \"$(pwd -P)\" | tr -c 'A-Za-z0-9' '-')\"'/memory'\n"
        "echo 'no gaps found'\n"
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    return lambda: record.read_bytes().decode().split("\0")[:-1]
