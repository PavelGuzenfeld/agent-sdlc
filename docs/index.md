# agent-sdlc

A software development lifecycle shipped as agent config: rules, skills, slash
commands and a diff-scoped mutation gate, installable into Claude Code and
Codex.

The layout is agent-agnostic: `skills/ commands/ rules/ bin/ mutation_gate/`
at the root, no agent home baked in.

## Install

```bash
git clone https://github.com/PavelGuzenfeld/agent-sdlc
cd agent-sdlc
./install.sh --target all
```

`--target claude|codex|all` picks the agent home. `install.sh` symlinks
`skills/` into `~/.claude/skills` and `~/.codex/skills`, `commands/*.md` into
`~/.claude/commands` and as `~/.codex/skills/<name>/SKILL.md`, `bin/*` into
`~/.claude/bin`, and merges the hook lines from `settings.example.json` into
`~/.claude/settings.json`. The `mutation-gate` Stop hook is added only when
the binary is on `PATH`. A second run changes nothing.

Rules load per repo, not globally: run `mutation-gate rules sync` inside a
repo that opts in, which writes `.claude/rules/*.md` and the `AGENTS.md`
block there.

`--deps` installs `git gh jq docker python3 ast-grep pytest` and the gate;
`--deps=say` adds the Kokoro voice stack.

The `mutation-gate` CLI alone, without the rest of the pack, installs with
`pip install agent-sdlc` (the importable module stays `mutation_gate`, the
console script stays `mutation-gate`).
