# Getting started

From clone to a first gated commit.

## Install

```bash
claude plugin marketplace add PavelGuzenfeld/agent-sdlc
claude plugin install agent-sdlc@agent-sdlc
git clone https://github.com/PavelGuzenfeld/agent-sdlc
cd agent-sdlc
./install.sh --deps
```

- The plugin ships the skills, commands and hooks. `--scope user` is the
  default; `--scope project` or `--scope local` limits it to one repo.
- To turn a user-scope install off in one repo, put
  `{"enabledPlugins": {"agent-sdlc@agent-sdlc": false}}` in that repo's
  `.claude/settings.local.json`. Other repos keep it. Checked with
  `claude plugin list` on Claude Code 2.1.283: it holds from every
  subdirectory. The same line in `.claude/settings.json` held only when run
  from the directory holding `.claude/`, so don't rely on it.
- `--deps` installs `git gh jq docker python3 ast-grep pytest pre-commit`,
  plus `mutation-gate` itself.
- `install.sh` also renders the commands as Codex skills under
  `~/.codex/skills`. It installs nothing into `~/.claude`; `--target claude`
  exits and prints the plugin commands above.
- An older `install.sh` linked into `~/.claude` and merged hooks into
  `~/.claude/settings.json`. Alongside the plugin those hooks fire twice.
  `./install.sh --uninstall-legacy` removes only what it added.
- Rerunning it changes nothing.

## Verify it worked

```bash
claude plugin list
```

```text
  ❯ agent-sdlc@agent-sdlc
    Status: ✔ enabled
```

- `tests/install.sh` checks the Codex tree and the legacy uninstall against a
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
