# Usage

Step by step, from install to a merged PR, once for Claude Code and once for
Codex.

## Claude Code

### 1. Install

```bash
git clone https://github.com/PavelGuzenfeld/agent-sdlc
cd agent-sdlc
./install.sh --target claude --deps
```

- Links skills, commands and `bin/` into `~/.claude`, and merges the
  git-guardrail and `/say` hooks into `~/.claude/settings.json`.
- Adds the Stop-time gate hook when `mutation-gate` is on `PATH`.
- Or load it as a plugin, without installing: `claude --plugin-dir /path/to/agent-sdlc`.

### 2. Opt a repo in

Run these inside the repo you work on:

```bash
touch .mutation-gate.toml          # gate at every session Stop
mutation-gate rules sync           # rules into .claude/rules/ and AGENTS.md
mutation-gate --dry-run            # see what the gate would test
```

- To gate commits too, add the hooks to `.pre-commit-config.yaml`; see
  [Hooks and tools](tools.md#pre-commit-hooks).
- Commit the synced rules, or keep them local with `.git/info/exclude`.

### 3. Start a session

```bash
cd your-repo
claude
```

- The rules load from `.claude/rules/`.
- Type `/` to see the commands: `/kata`, `/done`, `/grill` and the rest.
- Skills load on their own when a task matches, or type one: `/diagnose`.

### 4. Turn an idea into a ticket

A design with open questions:

```text
/grill should the parser accept an empty header?
```

- One question at a time until nothing is open.
- `/grill plan` files a decision record and one step ticket per unit of work.

A well-scoped ask goes straight to the tracker:

```bash
gh issue create -t "Parser accepts an empty header" -b "Expected: rejected with a named error."
```

### 5. Approve it

```bash
gh issue edit 42 --add-label model:sonnet
```

- The `model:<name>` label is the approval and picks the model that runs it:
  `haiku`, `sonnet`, `opus` or `fable`.

### 6. Run it

```text
/kata 42
```

- A worker branches `42-slug` in its own worktree, writes a failing slice
  test, implements, and commits through the gate.
- It opens a PR with `Closes #42` and waits for green CI.
- `/kata` alone works the whole labelled queue.

### 7. Review and merge

- Read the PR. Anything you say goes back to the same worker, on the same
  branch.
- When it's right, type:

```text
LGTM
```

- Kata squash-merges, removes the worktree and deletes the branch.

### 8. Close out

```text
/done
```

- Commits any leftover coherent unit, leaves a handoff note, and offers
  follow-up issues for what was deferred.
- Then `/debrief-agent` to review the session, and `/cleanup` to free disk.

### When the gate blocks you

```text
BLOCKED: 2 mutant(s) survived with no waiver.
  age.py:2:11:operator:age >= 18 => age > 18
```

- Write the test that kills it, from the requirement.
- Or waive it in `.mutation-gate-waivers.toml` with a real reason.
- Details: [Gate](gate.md#when-it-blocks).

## Codex

### 1. Install

```bash
./install.sh --target codex --deps
```

- Links `skills/` into `~/.codex/skills` and renders each command as a skill
  there, `~/.codex/skills/<name>/SKILL.md`.
- Merges no hooks: there is no git guardrail and no Stop-time gate in a
  Codex session installed this way.
- Or add the repo as a Codex marketplace source; its plugin ships skills and
  hooks.

### 2. Opt a repo in

Same as Claude Code:

```bash
mutation-gate rules sync           # writes the AGENTS.md block Codex reads
```

- Wire the pre-commit hooks. They run at `git commit`, whichever agent made
  the change, so this is how Codex work gets gated.

### 3. Start a session and call a skill

```bash
cd your-repo
codex
```

```text
/skills
$diagnose the parser test fails only on CI
$done
```

- `/skills` lists them. `$name` invokes one explicitly.
- Every command from `commands/` is a skill here: `$kata`, `$done`, `$grill`.

### 4–8. Ticket to merge

- The flow is the same: file, label, run, review, merge, close out.
- The commands were written for Claude Code. `/kata` spawns a subagent per
  ticket, and nothing checks that Codex runs it the same way. Filing,
  labelling, the gate and `$done` don't depend on that.

## What differs

| | Claude Code | Codex |
|---|---|---|
| Install | `--target claude` or `--plugin-dir` | `--target codex` or marketplace |
| Rules read from | `.claude/rules/*.md` | `AGENTS.md` |
| Call a command | `/kata 42` | `$kata 42` |
| Call a skill | `/diagnose`, or loads on match | `$diagnose` |
| git guardrail | Yes, PreToolUse hook | Not with `install.sh` |
| Gate at session Stop | Yes, with `.mutation-gate.toml` | Not with `install.sh` |
| Gate at commit | Pre-commit hooks | Pre-commit hooks |
| `/say` voice | Yes | No: its scripts live in `~/.claude/bin` |
