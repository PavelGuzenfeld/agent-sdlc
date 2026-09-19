# agent-sdlc

A software development lifecycle shipped as agent config: rules, skills, slash
commands and a diff-scoped mutation gate, installable into Claude Code and
Codex. The pack came out of a private dotfiles tree and lands here one themed,
sanitized PR at a time. Files are copied, not rewritten; the
[tracker](https://github.com/PavelGuzenfeld/agent-sdlc/issues) is the roadmap.

The layout is agent-agnostic: `skills/ commands/ rules/ bin/ mutation_gate/`
at the root, no agent home baked in. This site draws the process in four ASCII
charts and includes the rule and skill text verbatim from the repo, so it never
drifts from what the agent actually reads.

## Install

```bash
git clone https://github.com/PavelGuzenfeld/agent-sdlc
cd agent-sdlc
./install.sh --target all
```

`--target claude|codex|all` picks the agent home. `install.sh` symlinks
`skills/` into `~/.claude/skills` and `~/.codex/skills`, `commands/*.md` into
`~/.claude/commands` and as `~/.codex/skills/<name>/SKILL.md`, `rules/*.md`
into `~/.claude/rules`, `bin/*` into `~/.claude/bin`, generates
`~/.codex/AGENTS.md` from `rules/`, and merges the hook lines from
`settings.example.json` into `~/.claude/settings.json`. The `mutation-gate`
Stop hook is added only when the binary is on `PATH`. A second run changes
nothing.

`--deps` installs `git gh jq docker python3 ast-grep pytest` and the gate;
`--deps=say` adds the Kokoro voice stack.
