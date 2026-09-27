# agent-sdlc

[![CI](https://github.com/PavelGuzenfeld/agent-sdlc/actions/workflows/ci.yml/badge.svg)](https://github.com/PavelGuzenfeld/agent-sdlc/actions/workflows/ci.yml)

A software development lifecycle shipped as agent config for Claude Code and
Codex: rules, skills, slash commands, hooks, and a diff-scoped mutation gate.

Docs: <https://pavelguzenfeld.com/agent-sdlc/>

## Why

A coding agent writes the code and the tests for it, and tests written next
to the code tend to agree with it, bugs included. On a mature suite, 57% of
real bug-class mutants survived. agent-sdlc puts that check, plus scope,
intent and git safety, into hooks and a gate instead of leaving them to the
agent's memory.

| Problem | What catches it |
|---|---|
| Tests that pass but assert nothing | `mutation-gate`: a surviving mutant blocks the commit |
| Tests shaped to the code | An adversary review that sees intent and tests, never the code |
| Scope creep | 40-line limit without a ticket; one ticket, one branch, one PR |
| Design notes rotting in the tree | New `.md` files are blocked; intent lives in the tracker |
| Destructive git | A hook that denies `reset --hard`, `add -A`, force-push |
| AI tells and leaked identity in commits | `commit-msg` and `no-leaks` hooks |

## Example

```python
def is_adult(age):
    return age >= 18

def test_adult():
    assert is_adult(30)

def test_child():
    assert not is_adult(5)
```

```text
BLOCKED: 2 mutant(s) survived with no waiver.
  age.py:2:11:operator:age >= 18 => age > 18
  age.py:2:18:literal:18 => 19
```

Add `assert is_adult(18)` and `assert not is_adult(17)`, and the gate passes.

## Install

Claude Code:

```bash
claude plugin marketplace add PavelGuzenfeld/agent-sdlc
claude plugin install agent-sdlc@agent-sdlc
```

Tools the gate needs, and Codex:

```bash
git clone https://github.com/PavelGuzenfeld/agent-sdlc
cd agent-sdlc
./install.sh --deps
```

| Want | Do |
|---|---|
| Claude Code | The plugin above; `--scope local` or `--scope project` keeps it to one repo |
| Codex | `./install.sh --target codex`, or add the repo as a Codex marketplace source |
| Gate dependencies | `./install.sh --deps` (`--deps=say` adds voice) |
| Only the gate | `pip install agent-sdlc` (WordNet check: `agent-sdlc[vocabulary]`) |
| The gate on a repo | Add `.mutation-gate.toml`, wire the pre-commit hooks |

- `install.sh` links `skills/` into `~/.codex` and renders `commands/` as
  Codex skills. It installs nothing into `~/.claude`. A second run changes
  nothing.
- Installed an older `install.sh` into `~/.claude`? `./install.sh
  --uninstall-legacy` removes those links and hooks, or every hook fires twice.
- `ast-grep-cli` adds an `sg` shim that can shadow the system `sg`; call
  `ast-grep`.

## Use it

In Claude Code (Codex: `$name` instead of `/name`):

1. Install the plugin and `./install.sh --deps`
2. In your repo: `touch .mutation-gate.toml && mutation-gate rules sync`
3. `claude`, then `/grill <idea>` or `gh issue create …`
4. Approve the ticket: `gh issue edit 42 --add-label model:sonnet`
5. `/kata 42`: a worker writes the failing test, implements, gates, opens the PR
6. Review, then type `LGTM`: it squash-merges and cleans up
7. `/done` to close out the session

Full walkthrough, and what differs in Codex:
<https://pavelguzenfeld.com/agent-sdlc/usage/>

## What's inside

| Path | What |
|---|---|
| `rules/` | How to work; synced into a repo with `mutation-gate rules sync` |
| `commands/` | Slash commands: `/kata`, `/done`, `/grill`, `/rectify` … |
| `skills/` | On-demand playbooks: `/diagnose`, `/sol-budget`, `/verify-generated-diff` … |
| `bin/` | Hooks and helpers: `git-guardrail.sh`, the `/say` stack |
| `mutation_gate/` | The gate and the `mutation-gate` CLI |

CI runs `scripts/no-leaks.sh` on every PR. It flags emails, RFC1918
addresses, user-at-host references, `/home/<user>/` paths and non-personal
`ghcr.io/` paths, and prints only `file:line`.

MIT, see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) for one vendored
third-party skill. Contributions: [CONTRIBUTING.md](CONTRIBUTING.md), bound
by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Security: [SECURITY.md](SECURITY.md).
