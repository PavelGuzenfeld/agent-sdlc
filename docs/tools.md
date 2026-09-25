# Hooks and tools

What runs without you asking, and the scripts behind it.

## What runs when

```text
 agent runs a Bash command ----> PreToolUse: git-guardrail.sh  (can deny)

 git commit
   |-- pre-commit stage ----> rules-check, mutation-gate, no-new-docs
   '-- commit-msg stage ----> commit-msg, diff-discipline, no-leaks

 agent finishes a turn  ----> Stop: mutation-gate-hook.sh      (repos with .mutation-gate.toml)
                        ----> Stop: say-hook.sh                (speaks when armed)
```

## Claude hooks

| Event | Script | Plugin install | `install.sh` install |
|---|---|---|---|
| `PreToolUse` (Bash) | `git-guardrail.sh` | `hooks/hooks.json` | merged from `settings.example.json` |
| `Stop` | `mutation-gate-hook.sh` | `hooks/hooks.json` | added when `mutation-gate` is on `PATH` |
| `Stop` | `say-hook.sh` | `hooks/hooks.json` | merged from `settings.example.json` |

- `mutation-gate-hook.sh` exits quietly unless the repo has a
  `.mutation-gate.toml`, then runs `mutation-gate --worktree`.
- Adding that file is all a repo needs for Stop-time gating.

## git-guardrail

A PreToolUse hook on every Bash call the agent makes. It denies:

| Command | Why |
|---|---|
| `git add -A`, `git add .`, `git add --all` | Uncommitted edits ride along across branches |
| `git reset --hard` | Throws away work |
| `git clean -f…` | Deletes untracked files |
| `git checkout .`, `git checkout -- .`, `git restore .` | Discards every edit |
| `git push --force` / `-f` without `--force-with-lease` | Overwrites a shared branch |
| `git push` with a `+refspec` | Same, by another spelling |
| `git branch -D <b>` | Deletes unmerged work |

- `branch -D` is allowed when `gh` finds a merged PR for the branch and the
  branch tip is that PR's head, or an ancestor of it.
- A denial names the rule and how to run it yourself:

```text
git-guardrail: blocks git reset --hard
  git safety protocol: never reset --hard without explicit request
  run it yourself with: ! git ...
```

- It matches command text, so the pattern inside a heredoc or `sed` script
  also trips it. Edit files with the editor tool instead.

## Pre-commit hooks

Wire the gate into a consuming repo's `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/PavelGuzenfeld/agent-sdlc
    rev: v0.2.1
    hooks:
      - id: rules-check
      - id: mutation-gate
      - id: no-new-docs
      - id: commit-msg
      - id: diff-discipline
      - id: no-leaks
```

```bash
pre-commit install
pre-commit install --hook-type commit-msg
```

| Hook id | Stage | Runs |
|---|---|---|
| `rules-check` | pre-commit | `mutation-gate rules check` |
| `mutation-gate` | pre-commit | `mutation-gate --staged` |
| `no-new-docs` | pre-commit | `mutation-gate no-new-docs` |
| `commit-msg` | commit-msg | `mutation-gate commit-msg` |
| `diff-discipline` | commit-msg | `mutation-gate diff-discipline` |
| `no-leaks` | commit-msg | `mutation-gate no-leaks` |

- The three commit-msg hooks need the second `pre-commit install` line, unless
  the repo's config sets `default_install_hook_types`.

## bin/ scripts

| Script | What it does |
|---|---|
| `git-guardrail.sh` | The PreToolUse hook above |
| `mutation-gate-hook.sh` | Stop hook: finds the repo root from the hook payload, runs the gate if opted in |
| `mutation-gate` | Runs the gate from this checkout without `pip install` |
| `merge-claude-hook.sh` | Adds one hook to `settings.json` if it isn't there already; `install.sh` uses it |
| `install-gdscript-parser` | Builds the tree-sitter GDScript parser in Docker so ast-grep can read `.gd` files |
| `say.sh`, `ksay.py` | Speak a text file through Kokoro |
| `say-trigger.sh`, `say-narrate.py`, `say-prompt.md`, `say-extract.jq` | The `/say` pipeline: pick the last answer, rewrite it for listening, speak it |
| `say-key.sh` | Terminal key binding: stop, arm, or speak |
| `say-hook.sh` | Stop hook that speaks the answer when armed |

```bash
install-gdscript-parser                 # writes ~/.local/share/ast-grep/gdscript.so
bin/mutation-gate --dry-run             # run the gate from a checkout
```

## install.sh

```text
usage: ./install.sh [--target claude|codex|all] [--deps | --deps=say] [--uninstall-legacy]
```

| Flag | Effect |
|---|---|
| `--target claude` | Link `skills/`, `commands/`, `bin/` into `~/.claude`; merge hooks |
| `--target codex` | Link `skills/` into `~/.codex/skills`; render each command as a Codex skill |
| `--target all` | Both |
| `--deps` | Install `git gh jq docker python3 ast-grep pytest pre-commit` and the gate |
| `--deps=say` | Also the Kokoro voice stack |
| `--uninstall-legacy` | Remove the `~/.claude` links and hooks this script added, then exit |

- Rerunning changes nothing.
- `ast-grep-cli` also installs an `sg` shim. If `~/.local/bin` comes before
  `/usr/bin`, it shadows the system `sg`. Always call `ast-grep`.

## Plugins

| Agent | Manifest | Load it |
|---|---|---|
| Claude Code | `.claude-plugin/plugin.json` | `claude --plugin-dir /path/to/agent-sdlc` |
| Codex | `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json` | Add the repo as a marketplace source |

- The Claude plugin ships skills, commands and hooks. The Codex plugin ships
  skills and hooks; commands reach Codex only through `install.sh`.
