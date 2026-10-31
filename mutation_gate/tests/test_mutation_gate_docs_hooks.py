"""Intent: #423 — every hook declared in hooks/hooks.json is named in the
hooks table and the "What runs when" diagram of docs/tools.md."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
TOOLS_DOC = (ROOT / "docs" / "tools.md").read_text()
HOOK_TARGET = re.compile(r"bin/([\w.-]+\.sh)|-m (mutation_gate\.\w+)")


def declared_hooks():
    events = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    for event, groups in events.items():
        for group in groups:
            for hook in group["hooks"]:
                target = HOOK_TARGET.search(hook["command"])
                yield event, next(name for name in target.groups() if name)


HOOKS = list(declared_hooks())


def section(heading):
    start = TOOLS_DOC.index(f"## {heading}")
    return TOOLS_DOC[start:TOOLS_DOC.index("\n## ", start + 1)]


@pytest.mark.parametrize("event,script", HOOKS)
def test_hooks_table_has_a_row_for_every_declared_hook(event, script):
    assert f"| `{event}`" in section("Claude hooks")
    assert f"`{script}` | `hooks/hooks.json` |" in section("Claude hooks")


@pytest.mark.parametrize("event,script", HOOKS)
def test_diagram_names_every_declared_hook(event, script):
    assert script in section("What runs when")
