# Getting started

From clone to a first gated commit.

[TOC]

## Clone and install

```bash
git clone https://github.com/PavelGuzenfeld/agent-sdlc
cd agent-sdlc
./install.sh --target claude --deps
```

- `--target` takes `claude`, `codex` or `all`.
- It links `skills/` into the agent's config directory and `commands/*.md`
  into `~/.claude/commands`, or renders each command as
  `~/.codex/skills/<name>/SKILL.md` for Codex.
- It merges the hook lines from `settings.example.json` into
  `~/.claude/settings.json`.
- `--deps` installs `git gh jq docker python3 ast-grep pytest pre-commit`,
  plus `mutation-gate` itself.
- Rerunning it changes nothing.

## Verify it worked

```bash
ls -la ~/.claude/skills/
```

Every entry is a symlink back into the clone, not a real directory:

```text
lrwxrwxrwx  diagnose -> /path/to/agent-sdlc/skills/diagnose
```

If `mutation-gate` was on `PATH` at install time, the Stop hook is there:

```bash
jq '.hooks.Stop' ~/.claude/settings.json
```

- `tests/install.sh` runs all of these checks, plus the Codex tree, against a
  throwaway `$HOME`. Read it if something here doesn't match.

## First real use

Start a Claude Code session and park an aside with the `ps` skill:

```text
/ps write a getting-started page
```

```text
📌 queued (1): write a getting-started page
```

- The line goes to a scratchpad file and the session carries on.
- A skill is a `SKILL.md` file Claude reads on demand, not a program it runs.

## Turn on the gate in a repo

Three steps, each independent:

| Step | Turns on | How |
|---|---|---|
| Add `.mutation-gate.toml` | Gating at every session Stop | Even an empty file works; see [Config](config.md) |
| Wire the pre-commit hooks | Gating at every commit | See [Hooks and tools](tools.md#pre-commit-hooks) |
| `mutation-gate rules sync` | The rules, as `.claude/rules/*.md` and `AGENTS.md` | Only writes files; gates nothing |

```bash
cd your-repo
touch .mutation-gate.toml
mutation-gate --dry-run
```

```text
f.py: 1 candidate test file(s), 2 mutant(s)
    test  tests/test_f.py
    mut   2:11: x > 1 => x >= 1
    mut   2:15: 1 => 2
```

- `--dry-run` lists the tests and mutants it would run, and runs nothing.
- When it blocks you, see [Gate](gate.md#when-it-blocks).
