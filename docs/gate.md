# Gate

`mutation-gate` mutates the lines your diff changed, reruns the tests, and
blocks when a mutant survives.

## How it fires

```text
        git commit                        session Stop
            |                                  |
            v                                  v
    +---------------+                  +---------------+
    | pre-commit    |                  | Stop hook     |
    +---------------+                  +---------------+
            |                                  |
            +----------------+-----------------+
                             |   whichever runs first satisfies the other
                             v
                  +----------------------+
                  | mutation-gate        |
                  | mutates the diff,    |
                  | runs the tests       |
                  +----------------------+
                     |               |
        survivor     |               |   model_paths touched
                     v               v
    +--------------------+     +---------------------------+
    | kill it: a test    |     | spec present: MS-n lines  |
    | from the intent    |     | in the pinned issue       |
    | or waive it with   |     | each test cites an MS-n   |
    | a reason           |     | golden hash matches       |
    +--------------------+     +---------------------------+
                     |               |
                     +-------+-------+
                             |   green
                             v
                  +----------------------+
                  | adversary            |
                  | sees intent + tests, |
                  | never the code;      |
                  | reports, no block    |
                  | + model blind pass   |
                  +----------------------+
```

| Trigger | Needs | Runs |
|---|---|---|
| `git commit` | the `mutation-gate` pre-commit hook in the repo | `mutation-gate --staged` |
| Session Stop | a `.mutation-gate.toml` in the repo | `mutation-gate --worktree` |

- `mutation-gate rules sync` does not turn either one on; it only writes rule
  files.

## What it checks

| Check | Blocks? | Runs when |
|---|---|---|
| Mutants on changed lines | Yes | Always |
| No covering tests for a gated file | Yes, unless an uncovered waiver exists | Always |
| Model V&V probe: model code outside `model_paths` | Yes, unwaivable | Always |
| Golden hash: `[[golden]]` artefact vs its SymPy source | Yes, unwaivable | A `[[golden]]` entry exists |
| Spec: issue resolves, touched model tests cite a live `MS-n` | Yes | A `model_paths` file changed |
| Added comment lines | Yes | `no_comments = true` |
| Names vs the vocabulary and molds | Yes | `vocabulary` is set |
| WordNet synonym collisions | Reports; blocks with `"block"` | `vocabulary` is set |
| Adversary review | No | After a pass |
| Model blind pass | No | After a pass, if a `model_paths` file changed |

## When it blocks

A real run on a function with two tests that never touch the boundary:

```text
mutation-gate: 1 changed source file(s)
  age.py: coverage came back empty — every mutant runs against all candidate tests
  age.py: baseline 0.5s, per-mutant timeout 30s (from baseline)
  [1/2] age.py:2:11 age >= 18 => age > 18
  [2/2] age.py:2:18 18 => 19

BLOCKED: 2 mutant(s) survived with no waiver.
  age.py:2:11:operator:age >= 18 => age > 18
  age.py:2:18:literal:18 => 19
```

Two ways forward, no third:

- **Kill it.** Write the test from the requirement, not from the code:

```python
def test_eighteen_is_the_first_adult_age():
    assert is_adult(18)
    assert not is_adult(17)
```

- **Waive it.** The gate prints the entry for `.mutation-gate-waivers.toml`;
  replace the reason with why no test can or should kill it:

```toml
[[waiver]]
file = "age.py"
line = 2
column = 11
old = """age >= 18"""
new = """age > 18"""
reason = "REPLACE ME — why no test can or should kill this"
```

- "I could not think of a test" is not a reason. Neither is a restatement of
  the mutation.
- A waiver that no longer matches a mutant after an edit is reported as stale.
- A mutant that times out counts as killed; the gate says so and suggests
  setting `mutant_timeout`.

## Model paths

- Declare model code in `model_paths`; the gate never infers it.
- Name the spec issue with `model_spec = "issue:N"`. A file path is refused
  once `model_paths` is set.
- A model test touched by the diff must cite a live `MS-n` line in its
  docstring:

```python
def test_q_stays_psd_across_dt():
    """MS-7: Q stays PSD across the dt envelope."""
```

- Model V&V in full: [Techniques](techniques.md#model-vv),
  [Rules → Model V&V](rules.md#model-verification-validation).

## Adversary review

- After a pass, an isolated review gets the intent and the tests, never the
  implementation.
- It reports into the session and never blocks. The report is also saved
  under `~/.cache/mutation-gate/`.
- Intent comes from the ticket on the branch (`42-slug`), the latest user
  turn, or `--user-prompt`.

## Languages

| Language | Suffixes | Tests found by |
|---|---|---|
| Python | `.py` | `test_paths` / `test_globs`, coverage map |
| C++ | `.cpp .hpp .cc .h .cu .cuh` | `.cpp` files under `test_paths` |
| TypeScript | `.ts`, `.tsx` | `*.test.ts` |
| GDScript | `.gd` | `test_paths`; needs `install-gdscript-parser` |

- A repo with more than one language sets `[languages.<name>]` tables. See
  [Config](config.md).

## Tests in Docker

- A docker `test_command` or `coverage_command` should pass
  `-u "$(id -u):$(id -g)"` to its inner `docker run`, as this repo's own
  [`.mutation-gate.toml`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/.mutation-gate.toml)
  does.
- The gate doesn't add the flag, since some images need root. Without it,
  coverage data and other outputs land root-owned in your tree.

```toml
test_command = 'docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/repo -w /repo my-image python -m pytest -q {tests}'
```

Source: [`rules/testing.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/testing.md), [`rules/model-vv.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/model-vv.md), [`mutation_gate/`](https://github.com/PavelGuzenfeld/agent-sdlc/tree/main/mutation_gate).
