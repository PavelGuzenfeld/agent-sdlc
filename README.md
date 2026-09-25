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

```bash
git clone https://github.com/PavelGuzenfeld/agent-sdlc
cd agent-sdlc
./install.sh --target all --deps
```

| Want | Do |
|---|---|
| The whole pack | `./install.sh --target all --deps` (targets: `claude`, `codex`, `all`; `--deps=say` adds voice) |
| Only the gate | `pip install agent-sdlc` (WordNet check: `agent-sdlc[vocabulary]`) |
| A plugin | `claude --plugin-dir /path/to/agent-sdlc`, or add the repo as a Codex marketplace source |
| The gate on a repo | Add `.mutation-gate.toml`, wire the pre-commit hooks |

- `install.sh` links `skills/` into `~/.claude` and `~/.codex`, links
  `commands/` and `bin/` into `~/.claude`, renders `commands/` as Codex
  skills and merges the hooks. A second run changes nothing.
- `ast-grep-cli` adds an `sg` shim that can shadow the system `sg`; call
  `ast-grep`.

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
