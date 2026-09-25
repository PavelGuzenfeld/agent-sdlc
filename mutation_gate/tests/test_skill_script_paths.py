"""Intent: #291 — every skills/*/SKILL.md and skills/*/references/*.md resolves
its own scripts through `<skill-dir>` instead of a hardcoded ~/.claude/skills
(or ~/.codex/skills) path, or a bare `scripts/...` invocation that only works
when the consumer repo happens to sit under the skill's own directory."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_FILES = sorted((REPO_ROOT / "skills").glob("*/SKILL.md"))
REFERENCE_FILES = sorted((REPO_ROOT / "skills").glob("*/references/*.md"))
SCANNED_FILES = SKILL_FILES + REFERENCE_FILES

HARDCODED_SKILL_PATH = re.compile(r"~/\.(?:claude|codex)/skills")
FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
PLACEHOLDER = "<skill-dir>"


def _hardcoded_path_hits(text: str) -> list[str]:
    return HARDCODED_SKILL_PATH.findall(text)


def _bare_script_tokens(text: str) -> list[str]:
    hits = []
    for block in FENCE.findall(text):
        for line in block.splitlines():
            for token in line.split():
                if "scripts/" in token and not token.startswith(PLACEHOLDER):
                    hits.append(token)
    return hits


def _offenders(finder) -> dict[str, list[str]]:
    offenders = {}
    for path in SCANNED_FILES:
        hits = finder(path.read_text())
        if hits:
            offenders[str(path.relative_to(REPO_ROOT))] = hits
    return offenders


def test_no_skill_file_hardcodes_a_home_skills_path():
    assert _offenders(_hardcoded_path_hits) == {}


def test_no_skill_file_invokes_a_bare_scripts_path():
    assert _offenders(_bare_script_tokens) == {}
