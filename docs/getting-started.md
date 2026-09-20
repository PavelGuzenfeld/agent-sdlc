# Getting started

## Clone and install

```bash
git clone https://github.com/PavelGuzenfeld/agent-sdlc
cd agent-sdlc
./install.sh --target claude
```

`--target` takes `claude`, `codex`, or `all`. It symlinks `skills/` and
`rules/*.md` into the agent's config directory, `commands/*.md` into
`~/.claude/commands` (or renders each as `~/.codex/skills/<name>/SKILL.md`),
and merges the hook lines from `settings.example.json` into
`~/.claude/settings.json`. Rerunning it is a no-op.

Add `--deps` to install the tools the pack expects on `PATH`:
`git gh jq docker python3 ast-grep pytest`, plus `mutation-gate` itself.

```bash
./install.sh --target claude --deps
```

## Verify it worked

```bash
ls -la ~/.claude/skills/
```

Every entry should be a symlink back into the cloned repo, not a real
directory:

```text
lrwxrwxrwx  diagnose -> /path/to/agent-sdlc/skills/diagnose
```

If you ran `--deps` and had `mutation-gate` on `PATH` at install time, confirm
the Stop hook landed:

```bash
jq '.hooks.Stop' ~/.claude/settings.json
```

`tests/install.sh` runs the full set of these checks, plus the Codex tree,
against a throwaway `$HOME` — read it if a check here doesn't match what you
see.

## First real use

Start a Claude Code session in the repo and park a tangential idea with the
`ps` skill:

```
/ps write a getting-started page
```

It appends the line to a scratchpad file and replies `📌 queued (1): write a
getting-started page`, then returns to whatever you were doing — nothing else
happens until you ask for the list back. That round trip is the whole
contract: a skill is a `SKILL.md` file Claude reads on demand, not a program
it runs.

## The gate

Every commit and every session Stop also runs `mutation-gate`: it mutates
your diff and blocks on any mutant your tests don't kill. That's a separate
component (`mutation_gate/`, tracked in
[#8](https://github.com/PavelGuzenfeld/agent-sdlc/issues/8)) with its own
waiver file. See [Gate](gate.md) for how it fires and what to do when it
blocks you.
