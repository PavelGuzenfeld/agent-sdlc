# Techniques

The ideas the pack is built on, one section each: what it is, why it is here,
and a small example.

[TOC]

## Mutation testing

- Seed small deliberate bugs (mutants) into the code and rerun the tests.
- A mutant the tests don't catch is a bug the tests wouldn't catch either.
- A kill rate is the only number that separates a green suite from a blind one.

The gate makes two kinds of mutant:

| Kind | Example | What a survivor means |
|---|---|---|
| `operator` | `age >= 18` → `age > 18` | No test sits on the boundary |
| `literal` | `18` → `19` | No test pins the value |

```text
BLOCKED: 2 mutant(s) survived with no waiver.
  age.py:2:11:operator:age >= 18 => age > 18
  age.py:2:18:literal:18 => 19
```

- Kill it with a test written from the requirement, or waive it with a reason
  that says why no test should. See [Gate](gate.md#when-it-blocks).

## Diff-scoped mutants

- Mutating a whole repo takes hours. The gate mutates only the lines the diff
  changed.
- It runs per commit (`--staged`) and per session Stop (`--worktree`); a token
  lets whichever runs first satisfy the other.
- `--file PATH` gates every line of one file, for an on-demand check.

```bash
mutation-gate --dry-run      # list candidate tests and mutants, run nothing
mutation-gate --file age.py  # gate the whole file
```

## Covering-test map

- Running every test for every mutant is slow. The gate first runs the tests
  under coverage with per-test contexts and maps each line to the tests that
  touch it.
- Each mutant then runs only its covering tests.
- `closure_depth` sets how many import hops from a test to the mutated file
  still count as covering it.
- When coverage comes back empty the gate says so and falls back to every
  candidate test:

```text
age.py: coverage came back empty — every mutant runs against all candidate tests
```

## Adversary review

- After the gate passes, an isolated review gets the intent (ticket, spec or
  your own words) and the tests. It never sees the implementation.
- It asks whether the tests assert the requirement or just echo the code.
- It reports into the session and never blocks. Answer each finding: fix it,
  or say why it is wrong.

| | Adversary | Model blind pass |
|---|---|---|
| Sees | intent + tests | code only |
| Never sees | the implementation | the spec, the conversation |
| Runs when | the gate passes | a `model_paths` file changed |
| Blocks | no | no |
| Catches | tests shaped to the code | intent that never made it into the code |

## Model V&V

For estimation and filter math, frames, angles, timestamps, sensor models and
noise parameters. The layers:

| Layer | What it checks |
|---|---|
| 0 — Spec | `MS-n` lines in one pinned issue; every model test cites one |
| 1 — Before editing | assumption inventory: frame, units, time base, noise |
| 2 — Units | a distinct type per quantity; mixing kinds fails the checker |
| 3 — Symbolic golden | F and Q generated from SymPy source, hash-checked |
| 4 — Tests | Jacobians vs finite differences, metamorphic properties |
| 5 — Consistency | Monte Carlo NEES/NIS against chi-square bands |

- The gate enforces Layer 0 and the golden hash; the rest hold because the
  rule is read.
- A repo declares `model_paths` and names the spec issue:

```toml
model_paths = ["filters/"]
model_spec = "issue:19"
```

- Once `model_paths` is set, a file-form spec is refused:

```text
mutation-gate rules refused: .mutation-gate.toml: model_spec must be "issue:N"
naming a pinned issue once model_paths is set; a file path, including the
default, is refused
```

Full rule: [Rules → Model V&V](rules.md#model-verification-validation).

## Vocabulary and naming

- A name uses the dictionary's canonical word for its concept, in the word
  order of spoken English.
- `vocabulary lookup` gives one of four verdicts: canonical, rejected synonym,
  vague, or unknown.
- `--kind` checks a whole name against the mold for its declaration kind.

```text
$ mutation-gate vocabulary lookup candidate
vocabulary lookup: `candidate` is not in the dictionary

$ mutation-gate vocabulary lookup --kind function compute_total
compute_total: fits the function mold
```

- The WordNet check flags a new dictionary word that shares a sense with an
  existing one. It reports by default; `vocabulary_synonyms = "block"` makes
  it fail. It needs `pip install agent-sdlc[vocabulary]`.

## Vertical slice first

- Every ticket starts with one slice test that enters where a real consumer
  enters: a CLI subcommand, an exported header, a published API.
- It asserts the outcome the ticket's acceptance line names, and it fails
  before any implementation.
- Unit tests fill in what the slice can't reach: edge values, error paths.

| Slice test | Unit test |
|---|---|
| `mutation-gate --staged` on a toy repo prints `BLOCKED` | `changed_lines()` returns the right line set |
| Enters through the CLI | Enters through a function |
| One per ticket | As many as the edges need |

## Ticket-driven flow

- One ticket, one branch, one PR, with `Closes #N` in the body.
- A `model:<name>` label on the ticket is the approval and names the model
  that runs it.
- Over 40 added production lines with no ticket reference, `diff-discipline`
  blocks the commit.
- `/kata` works the labelled queue. See [SDLC](sdlc.md).

## Speed-of-light budgeting

- Measure what the hardware can do (the speed of light, SOL) before tuning
  code, then compare each stage against it.
- `ratio = SOL ÷ measured`.

| Ratio | Verdict |
|---|---|
| ≥ 0.7 | Within 30% of the machine; refuse to tune the code, change the graph |
| 0.3 – 0.7 | Report both options, ask |
| ≤ 0.3 | Proceed, overhead first |
| > 1.0 | `MODEL_DEFECT`: a stage cannot beat its own floor |

Skill: `/sol-budget`, see [Skills](skills.md).

## Blind hypothesis testing

- Two rankings of the same evidence: one informed by everything you know, one
  from a process that sees only the evidence and the code at a pinned commit.
- The informed pass runs first, so its ranking can't be anchored by the
  blind one.
- The difference between the two rankings is the finding.

Skill: `/blind`, see [Skills](skills.md).
