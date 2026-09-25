---
name: verify-generated-diff
description: "Verify a diff whose tests were written alongside it, so tests can't be trusted as spec. Use to review, audit, or sanity-check AI-generated code, when tests pass but aren't trusted, or a diff is too large or unfamiliar to read."
---

# Verifying a Generated Diff

`<skill-dir>` is `${CLAUDE_SKILL_DIR}`, the directory this SKILL.md was read from.
Every command below runs with the reviewed repo as cwd and reaches this skill's
own scripts through `<skill-dir>`.

Code written together with its own tests has a specific failure mode: the tests
encode what the code *does* rather than what it *should* do. Green means the two
agree, which they always will. So the normal reviewer heuristic — read the
changed assertions, they're the spec — inverts and becomes actively misleading.

This skill replaces reading with perturbation. Three passes, run in order:

| Pass | Question it answers | Perturbation |
|---|---|---|
| **A. Mutation** | Do the tests test anything? | Corrupt the logic |
| **B. Subtraction** | Is this code load-bearing? | Remove the code |
| **C. Interrogation** | What does this assume? | None — claims + verifiers |

A and B are the same loop: `perturb → build → test → classify → revert`. The
revert must be automatic, which is what `scripts/mutate.sh` is for.

Run A first. There is no point reasoning carefully about code whose tests turn
out to be decorative.

## Before starting: is this the right tool?

Skip the passes and just read the diff if it's under ~50 lines. The passes cost
more than the reading.

Stop and say so if the diff is more than a few hundred lines of unfamiliar
generated logic. These passes assume you can already name the three or four
functions that carry the real logic. If nobody can, the problem is upstream —
the change needs splitting or regenerating in reviewable increments, and no
amount of verification rigor substitutes for that. Say this plainly rather than
performing a review that can't work.

## Step 0 — Establish the ground

Do these four things before any perturbation. Skipping any of them makes every
later result uninterpretable.

**1. Find the review baseline.** Everything is diffed against the last point the
user actually understood, not against `HEAD` (which moves when an agent commits).

```bash
git tag -f reviewed <sha>          # or HEAD~N, or the branch point
git diff --stat -M reviewed | tail -1
```

If the user doesn't know the baseline, ask — it's a one-line question and
guessing wrong wastes the whole session.

**2. Confirm the baseline is green.** A red suite before you start turns every
result into noise.

**3. Get the loop fast.** Mutation is N rebuilds. Under ~20 s incremental and
this works; at four minutes it doesn't and the user won't run it again.
Find the single test target rather than building the tree. See
`references/languages.md` for per-toolchain setup.

**4. Recover the real intent.** The agent's summary of its own diff is circular —
it's derived from the diff, so it can only agree with it. The non-circular
artifacts are, in order of preference: a spec, an ICD, a ticket, or the user's
original prompt. Ask which exists. If none does, say so explicitly: the passes
can then only establish internal consistency, not correctness, and that's a
weaker result the user should know they're getting.

Then **use it**, before any perturbation. Read the diff against that artifact and
report three things, quoting the line each came from:

- requirements it asks for that are **missing or partial**
- behaviour in the diff that **nobody asked for**
- requirements that look implemented but **look wrong**

This is cheap, it runs before the first build, and it is the only pass that can
catch a change that is internally consistent and answers the wrong question.
Report it separately from the mutation findings and never merge the two into one
ranked list: a suite that kills every mutant while missing a requirement is
exactly what the separation exists to expose.

## Step 1 — Pick the targets

Three or four functions, not the whole diff. Want: real decisions —
comparisons, arithmetic, loops, state transitions. Skip constructors, getters,
logging, forwarding.

```bash
git diff --numstat -M reviewed | sort -k1 -nr | head
git diff -M reviewed | rg '^\+' | rg -c '\b(if|for|while)\b|[<>]=?|\*|/'
```

Then read for domain verbs in the changed names — `predict`, `update`, `gate`,
`validate`, `wrap`, `normalize`, `quantize`, `parse`, `pack`, `merge`. Those are
where a wrong answer is plausible and silent.

Also run the orientation survey, which is cheap and catches things reading
misses:

```bash
<skill-dir>/scripts/survey.sh reviewed
```

It reports scope (files, new files), reinvention candidates (new symbols whose
names already exist elsewhere), swallowed exceptions, and hot-path hazards.

## Step 2 — Pass A: mutation

Full detail in `references/mutation.md`. The core:

Write four mutants per target function, one of each kind:

| Mutant | Edit | Catches |
|---|---|---|
| **Boundary** | `<` → `<=`, `>` → `>=` | off-by-one, edge conditions |
| **Constant** | `dt*dt/2` → `dt*dt`, `0.5` → `1.0` | wrong coefficient |
| **Branch** | condition → `true` (or `false`) | branch never exercised |
| **Stub** | inject an early return at the top of the body | test asserts nothing real |

Put them in a TSV and run:

```bash
<skill-dir>/scripts/mutate.sh <file> '<literal-old>' '<literal-new>' [test-filter]
<skill-dir>/scripts/run_mutants.sh mutants.tsv
```

Classify:

- **KILLED** — a test went red. That test does real work.
- **KILLED, oracle-dependent** — a test went red, but its expected value is
  *computed* rather than stated: derived in the test body, taken from a snapshot
  generated by accepting current output, or read through the same helper the code
  uses. Report this as its own finding, not as a pass.
- **SURVIVED** — green with wrong logic. This is the finding.
- **SURVIVED on a stub** — the test for that function is worthless, not weak.
- **BUILD-FAIL** — the compiler caught it; no information about the tests. The
  mutant was badly chosen. Rewrite it type-correct.

A KILLED verdict establishes that the test is **sensitive** to that mutation. It
does not establish that the test's expected value came from anywhere but the
code's own logic, and mutation cannot establish it: perturb the code and a
computed oracle disagrees exactly as a real one would. So a test that encodes the
same wrong formula as the implementation kills every mutant and still cannot
catch a wrong formula. That is what the second verdict is for.

For each survivor: write the test that would have killed it, **from the spec,
not from the code** — writing it from the code reproduces the original problem.
Re-run the mutant to confirm it's now KILLED. If it isn't, the new test is also
tautological. Commit tests separately from production changes.

For each oracle-dependent kill: replace the computed expected value with an
independent one — a literal from the spec or ICD, a worked example, a capture from
known-good hardware. If no independent source exists, say so; the test then pins
behaviour against regression and nothing more, which is worth having and worth
labelling.

Keep the TSV in the repo. It's a regression check on the test suite, which
nothing else provides.

## Step 3 — Pass B: subtraction

Full detail in `references/subtraction.md`. Same harness, `new` is empty.

The important correction to the naive version of this idea: **survival does not
mean the code is dead.** It means the tests don't cover it. Those are different
findings with different fixes. Resolve each survivor with a second question you
answer yourself — *can I construct an input that reaches this line and
misbehaves without the guard?*

| Deletion | Breaking input constructible? | Verdict | Action |
|---|---|---|---|
| KILLED | — | Load-bearing, tested | Leave it |
| SURVIVED | Yes | Load-bearing, **untested** | Write that test |
| SURVIVED | No, invariant guaranteed upstream | Dead defensiveness | Delete it |
| SURVIVED | Unsure | Unknown | Guard → assertion + counter |

The last row is the most useful outcome. A guard that can't be justified or
disproved should stop silently absorbing the case and start announcing it, so
the truth arrives from the field instead of never.

Separately and non-negotiably: any catch-all introduced by the change that
doesn't rethrow, log with context, or set an error state gets removed or
narrowed. `scripts/survey.sh` lists them.

## Step 4 — Pass C: interrogation

Full detail in `references/interrogation.md`.

Never ask for an explanation of the code; fluent prose gets absorbed as
understanding without a single claim being checked, which is the worst outcome
because it removes the sense that anything remains to be checked. Ask for
**enumerable claims**, then verify each with a tool. The question is worthless
without its verifier.

| Question | Verifier |
|---|---|
| What does this assume about its inputs that it doesn't validate? | Write the test that violates each assumption |
| What units / frame / scale / wrap range does each parameter use, and where is that documented? | The spec or ICD — this is where generated code is reliably wrong and the compiler silent |
| What breaks if this is called from two threads? | A two-thread test under a thread sanitizer |
| Which callers are affected if the return convention changes? | `git grep`, then LSP references — **not** the model's answer; it invents call sites |
| What in this file is dead? | Coverage report; zero-coverage lines in new files |

Question hygiene: open rather than leading ("what does this assume about its
inputs?" not "is this correct?" — the second gets agreement). Interrogate from a
fresh context given only the diff, not told it was generated, so it reasons from
the code alone as the reviewer must. Treat every answer as a candidate list.

## Step 4b — Performance, when the repo has a budget

If `perf/budget.md` exists and the diff touches a file the budget names, these three
passes say nothing about whether it is still fast enough. Run the performance gate:

```
python3 <skill-dir>/../sol-budget/scripts/budget_check.py --perf perf
```

`PERF_GATE: fail` is a finding like any other — report it with the node and the
overrun. `PERF_GATE: pass` goes in the report too, because a silent pass and a gate
nobody ran look identical.

No `perf/budget.md` means no performance claim either way; say that under "Not
established" rather than implying the diff is neutral. The `sol-budget` skill builds
the budget.

## Step 5 — Report

Report findings, not activity. Structure:

```
## Verdict
<one sentence: what is now trustworthy and what isn't>

## Spec
<missing or partial requirements, unasked-for behaviour, requirements
implemented wrong — each quoting the artifact. "No spec available" if none
existed. Never merged with Findings below.>

## Findings
<each: what, how it was established, what it means, suggested fix>

## Test suite assessment
<mutants run / killed / survived / killed-but-oracle-dependent, and specifically
which functions have worthless tests>

## Not established
<what these passes could not check — usually: correctness against a spec that
doesn't exist, behavior under real hardware/load, anything outside the target
functions>
```

The "Not established" section is required. The failure mode of a verification
pass is leaving the user with unearned confidence, and the honest scope of the
result is part of the result.

## Reference files

- `references/mutation.md` — mutant catalogue, how to write a stub mutant per
  language, handling flaky and slow suites, equivalent-mutant traps
- `references/subtraction.md` — candidate enumeration, the guard→assertion
  conversion, hot-path considerations
- `references/interrogation.md` — the question set with verifiers, sanitizer and
  coverage setup, what models get reliably wrong
- `references/languages.md` — fast-loop setup and test-filter syntax for
  C/C++/CMake, Python, Rust, Go, TypeScript
- `references/verifying-generated-diffs.md` — the same three-pass procedure as
  long-form prose, worked end to end on a C++/CMake example; read it to
  understand the reasoning, not as a lookup table

## Scripts

- `scripts/mutate.sh` — one mutant: refuses on a dirty file, substitutes,
  builds, tests, classifies, reverts on every exit path including Ctrl-C
- `scripts/run_mutants.sh` — batch runner over a TSV
- `scripts/survey.sh` — orientation: scope, reinvention, swallowed exceptions,
  hot-path hazards

- `mutants.tsv.example` — annotated starting set covering all four mutant kinds
  plus a Pass B deletion

Configure via environment: `BUILD_CMD`, `TEST_CMD`, `BUILD_DIR`, `BUILD_TARGET`.
Defaults are CMake/ctest; see `references/languages.md` for other stacks.

Two harness details that exist because getting them wrong produces *confidently
wrong* results rather than errors:

- `mutate.sh` runs a **baseline build and test first** unless
  `MUTATE_BASELINE_OK=1`. Without it, a missing test runner or a filter matching
  zero tests makes every mutant report KILLED — and KILLED reads as good news. A
  harness whose failure mode is false reassurance is worse than none.
- Deletion mutants in a TSV use the literal token `<DELETE>`, never an empty
  field. Tab is IFS whitespace, so an empty field silently shifts every later
  column.

## Safety

These scripts edit source files. They refuse to run on a file with uncommitted
changes and restore via `git checkout --` on every exit path — but that means a
crash between write and restore leaves a mutated file. Before starting, confirm
the working tree is clean and committed, and tell the user that's why. If they
have uncommitted work they care about, have them commit or stash it first rather
than working around the check.

Never leave a mutant in place. If a run is interrupted, verify with
`git status` and `git diff` before doing anything else.
