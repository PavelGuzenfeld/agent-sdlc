import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mutation_gate import mutants  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_ast_grep_ready_cache():
    mutants._ast_grep_ready.cache_clear()

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
