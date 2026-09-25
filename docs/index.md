# agent-sdlc

A software development lifecycle shipped as agent config for Claude Code and
Codex: rules, skills, slash commands, hooks, and a diff-scoped mutation gate.

## Why it exists

A coding agent writes the code and the tests for it. Tests written next to
the code tend to agree with it, bugs included, so a green suite can tell you
nothing.

- On a mature, well-shaped suite, **57%** of real bug-class mutants survived
  (measured 2026-09-10, see [Rules → Testing](rules.md#testing)).
- Agents drift from the ask: extra files, extra abstractions, 400-line diffs
  for a 40-line change.
- Intent gets lost. Design notes land in the tree, the ticket says one thing,
  the code another.
- Destructive git slips through: `reset --hard`, `add -A` across branches,
  force-push over someone's work.

agent-sdlc makes a hook or the gate check each of these, so the agent doesn't
have to remember them.

## What it solves, and how

| Problem | Mechanism | Where |
|---|---|---|
| Tests that pass but assert nothing | Mutation testing on the diff; a surviving mutant blocks the commit | [Gate](gate.md) |
| Tests shaped to the code, not the ask | Adversary review that sees intent and tests, never the code | [Techniques](techniques.md#adversary-review) |
| Scope creep | 40-line limit without a ticket reference; one ticket, one branch, one PR | [SDLC](sdlc.md) |
| Lost intent | Intent lives in the tracker; new `.md` files in the tree are blocked | [Rules → Tickets](rules.md#tickets) |
| Model code drifting from its spec | Model V&V: spec issue, `MS-n` citations, golden hashes, a blind pass | [Techniques](techniques.md#model-vv) |
| Vague or inconsistent names | Vocabulary dictionary, naming molds, WordNet synonym check | [Techniques](techniques.md#vocabulary-and-naming) |
| Destructive git | A PreToolUse hook that blocks `reset --hard`, `add -A`, force-push | [Hooks and tools](tools.md#git-guardrail) |
| AI tells in commits and PRs | Commit-message check for banned words and attribution trailers | [CLI](cli.md#commit-msg) |
| Leaked identity or internal names | `no-leaks` scan on the staged diff and message | [CLI](cli.md#no-leaks) |

## How the pieces fit

```text
 ticket (model:* label)
        |
        v
 /kata -> branch -> red slice test -> implement <--------------+
                                         |                      |
                                         v                      |
                                    git commit                  |
                                    |        |                  |
                        pre-commit  |        |  commit-msg      |
                                    v        v                  |
                        +---------------+  +------------------+ |
                        | mutation-gate |  | commit-msg       | |
                        +---------------+  | diff-discipline  | |
                          |         |      | no-leaks         | |
                    pass  |         |      +------------------+ |
                          v         +---- survivor -------------+
                  adversary report
                          |
                          v
                  PR, Closes #N -> LGTM -> squash merge
```

- **Rules** (`rules/`) say how to work. They sync into a repo as
  `.claude/rules/*.md` and an `AGENTS.md` block.
- **Commands** (`commands/`) are slash commands that run a workflow:
  `/kata`, `/done`, `/grill`.
- **Skills** (`skills/`) are playbooks the agent loads on demand:
  `/diagnose`, `/sol-budget`, `/verify-generated-diff`.
- **Hooks** run without asking: the gate at Stop, the git guardrail before
  every Bash call.
- **The gate** (`mutation_gate/`, the `mutation-gate` CLI) is the only part
  that can say no.

## One example

A function and two tests that look fine:

```python
def is_adult(age):
    return age >= 18


def test_adult():
    assert is_adult(30)


def test_child():
    assert not is_adult(5)
```

The gate mutates the changed lines and reruns the tests. Real output:

```text
mutation-gate: 1 changed source file(s)
  [1/2] age.py:2:11 age >= 18 => age > 18
  [2/2] age.py:2:18 18 => 19

BLOCKED: 2 mutant(s) survived with no waiver.
  age.py:2:11:operator:age >= 18 => age > 18
  age.py:2:18:literal:18 => 19
```

- Both tests pass whether the boundary is 18 or 19. Nothing pins it.
- The fix is a test from the requirement, not from the code:

```python
def test_eighteen_is_the_first_adult_age():
    assert is_adult(18)
    assert not is_adult(17)
```

```text
mutation-gate: pass
```

## Install

```bash
git clone https://github.com/PavelGuzenfeld/agent-sdlc
cd agent-sdlc
./install.sh --target all --deps
```

- `--target claude|codex|all` picks the agent home.
- `--deps` installs `git gh jq docker python3 ast-grep pytest pre-commit` and
  the gate; `--deps=say` adds the Kokoro voice stack.
- A second run changes nothing.
- Only the gate: `pip install agent-sdlc` (module `mutation_gate`, console
  script `mutation-gate`). Add `agent-sdlc[vocabulary]` for the WordNet check.

Details: [Getting started](getting-started.md) and
[Hooks and tools](tools.md#installsh).

## Where to go next

| You want to | Read |
|---|---|
| Install and see it work | [Getting started](getting-started.md) |
| Go from install to a merged PR, step by step | [Usage](usage.md) |
| Understand the ideas | [Techniques](techniques.md) |
| Follow the ticket-to-merge flow | [SDLC](sdlc.md) |
| Get unblocked by the gate | [Gate](gate.md) |
| Look up a flag or subcommand | [CLI](cli.md) |
| Configure a repo | [Config](config.md) |
| Pick a slash command | [Commands](commands.md) |
| See what runs on its own | [Hooks and tools](tools.md) |
