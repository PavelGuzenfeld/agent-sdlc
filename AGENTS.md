<!-- BEGIN mutation-gate rules -->
## code-clarity

# Code clarity

Code is the documentation. It is written for humans and only incidentally for
machines. Clarity comes from naming, types, and structure — never from prose
sitting next to the code.

Reach for a better name, a smaller function, or an explicit type before reaching
for a comment. A comment that explains *what* the code does means the code is
unclear: fix the code, then delete the comment.

## Hard limits

- Comments: **zero.** No hand-written `#` or `//` comments in new code, in this
  repo. Carve-outs: pragmas (`# pyright: ignore`, `# noqa`, `NOLINT`), shebangs,
  license/SPDX headers, and vendored or generated files — their comments are
  upstream's; check with a diff against the skeleton before assuming a config is
  yours.
- Docstrings: **3 lines maximum.** They are now the only remaining prose carrier.
- Upstream trees: match the host project's pattern instead of this ban.

If it does not fit, the thing being explained belongs in a name, a type, a test,
or a design doc — not in the file.

## Docstrings: only what the code cannot say

**The bar: a docstring must carry context the code cannot.** If the code
could say it — with a name, a type, or structure — say it there and delete the docstring.

Why a non-obvious choice was made. A spec or ICD constraint. A workaround and the
bug it dodges. A unit, frame of reference, or coordinate convention. A deliberate
simplification — only when it names both the ceiling it hits and the trigger to
revisit; without the trigger it is the unowned TODO below.

Never write: a restatement of the line below it, a docstring that restates the name or
the signature, a section banner, a changelog, a commented-out block, or an unowned TODO.

If the name and the signature already say it, write no docstring. A docstring is for the
invariant, the unit, or the caller obligation you would otherwise have to read the body
to find. Where a tool demands a summary line (pydocstyle, numpydoc, Doxygen), keep it
minimal and put the real content after it.

## diff-discipline

# Diff discipline
Minimize scope, never correctness. Never trim a bounds check, validation, error
path, explicit type, named constant, assert, or a calibration constant for a
physical quantity — especially in real-time or ICD-facing code.
- Smallest change that fully satisfies the request. 200 lines where 50 would do → rewrite as 50.
- Every changed line traces to the request. No drive-by refactors or reformatting.
- Match the closest existing pattern in the surrounding code. Don't invent a second way.
- Reach for the standard library before hand-rolling it, and a native platform
  feature before a new dependency.
- About to patch around, wrap, or reimplement behaviour a third-party dependency
  owns: stop and ask the user to run `/upstream` — the fix may belong in the dependency.
- No new file, dependency, abstraction-with-one-caller, or config knob unasked.
- Before finalizing, delete every added line not required by the requirement, an
  existing test, or the safety of the code path.
- Over ~40 request-driven lines: no approved ticket → stop at ~40 lines and
  write one; ticket in hand → implement the slice it scopes.
  Smallest-change-that-satisfies still binds inside the slice. Shrinkage is
  exempt.
- Model V&V artefacts are exempt from this and the no-new-dependency rule — `model-vv.md`.
- Shrink in its own commit after the fix, same PR. Never in upstream forks,
  vendored or generated code, or test statements.
- Report the changed-line count.

## Structural edits
A multi-line or syntax-shaped edit to code goes through `ast-grep run -p ... -r ...`,
then the repo's formatter (`ruff format`, `prettier --write`): ast-grep gets the
structure right and the **layout wrong**. `sed`/`perl` only for prose, config and
single-line literals — a regex alternation matches across lines and eats them.
`sg` is ambiguous: `/usr/bin/sg` is newgrp's alias, and ast-grep-cli's shim can shadow it. Always `ast-grep`.
Use it to audit too: a structural question deserves a pattern, not a grep heuristic.

## naming

# Naming

Word order in every name follows spoken English order — the reader parses a
name the way they parse a sentence.

A name is made in three steps: pick the concept, take the dictionary's
canonical word for it, assemble the words in the mold for the declaration
kind.

Before naming anything, run `mutation-gate vocabulary lookup <word>`. It
reports canonical (use it), a rejected synonym (use the canonical word it
names), vague (follow the hint), or unknown — add the concept, with a
`meaning`, to the repo's vocabulary file in the same diff.

Once the words are picked, run `mutation-gate vocabulary lookup --kind <kind>
<name>` against the candidate. It checks the name against the mold for that
kind and prints the fix when it does not fit.

## Kinds

`--kind` takes one of: function, method, variable, field, constant, local,
parameter, property, bool, type, namespace, enumerator, event. Each kind
opens a fixed set of molds; `lookup --kind` is the grammar, this file is not.

## testing

# Testing

A suite can be green and blind at the same time. Structure cannot tell the two
apart — tight tests, real assertions, property tests and golden oracles all
survive the distinction. Only a kill rate separates them.

Measured 2026-09-10 on a mature, well-shaped suite: **57%** of real bug-class
mutants survived, four of six survivors sitting in a blind spot the tests
documented as deliberate policy.

## The gate is not optional

`mutation-gate` runs from a pre-commit hook and from the Stop hook. Whichever
runs first satisfies the other. Never `--no-verify`, never `--no-adversary`
outside debugging the pack itself.

A surviving mutant blocks. Two ways forward, no third:

- write the test that kills it — **from the intent, not from the code**, or
- record it in `.mutation-gate-waivers.toml` with a reason that names why no
  test can or should kill it.

"I could not think of a test" is not a reason. A waiver whose reason restates
the mutation is not a reason.

A slice test counts as a covering test for the diff, same standing as any unit
test — the gate does not care which kind killed the mutant.

## Writing tests the gate will not embarrass

**Assert the tight bound.** `assert x > 0` where the spec says `x == 4.5` passes
on every wrong answer above zero. Pin the value the requirement names.

**Test the contact boundary, do not avoid it.** Float error at a boundary is a
reason to choose exact-representable inputs, not a reason to test only the
"clearly separated" and "clearly overlapping" regimes. Coordinates and sizes
that are exact in binary floating point make `<=` versus `<` observable. Every
boundary you skip is a mutant that will survive.

**No tolerance without a stated reason.** `pytest.approx` and `ASSERT_NEAR` need
the epsilon justified — a unit, an accumulated-error budget, a spec clause. An
unexplained tolerance is a hole sized to whatever the implementation happened to
produce.

**Name the failure mode, not the function.** A test called
`test_obb_circle_overlap` asserts whatever the code does. One called
`test_circle_touching_corner_at_zero_heading_overlaps` asserts a requirement.

**One failure mode per test.** Volume is not the problem — 1044 tests at a median
of 12 lines is fine. Many tests pointed at one failure mode is the problem, and
the waiver file will show you where that happened.

## Vertical slice first

**One slice test per ticket.** Enter where a real consumer enters — an exported
header, a CLI subcommand, a topic, a published API — and assert the
user-visible outcome named in the ticket's acceptance line, not the function
that happens to implement it.

**Unit tests fill in behind it.** Reserve them for what the slice cannot
reach: numeric kernels, boundary values, error paths, property tests. A unit
test that only re-exercises what the slice already covers earns nothing.

**Red first, always.** Write the slice test before the implementation and
watch it fail for the right reason. A test that was never red proves nothing —
it could pass against the unmodified tree.

## Adversary protocol

When the gate goes green, the pack spawns an isolated review that sees the
intent and the tests but **never the implementation**. It reports into the
session; it never blocks.

Take its findings seriously — it is the only reader in the loop that was not
anchored by the code. Respond to each one: fix it, or say why it is wrong. Do
not silently skip them because the gate already passed; green is exactly when
nothing else is looking.

Never feed it your own summary of the diff. That summary is derived from the
diff and can only agree with it. Intent comes from a ticket, a spec, or the
user's own words.

Model changes also run `model-vv.md` — its blind pass is the opposite blindfold: code, no spec.

## tickets

# Tickets

Intent-bearing prose lives in the repo's own tracker, never in the tree. A file
survives only if something other than a human reads it — CI config, lint config,
a gate config — or it is README, LICENSE, or CONTRIBUTING. Never write a design
doc, an RFC, or a decision log as a file in the repo; open a ticket and point to
it instead.

This binds this repo. An upstream tree keeps its own doc conventions.

## Model spec

model-vv.md Layer 0 no longer defaults to a file. Its `MS-n` lines live in one
pinned ticket, named by `model_spec = "issue:N"` in the repo's own gate config.
Where the tracker itself lives is that repo's business, never named in a rule
file.

## One ticket, one branch, one PR

An approved ticket is the plan, and satisfies diff-discipline's stop on its own
— no ticket, no change past the line-count limit; open one first. A ticket maps
to exactly one branch and one PR, and the PR body carries `Closes #N`. This
repo defaults to squash-only merges with delete-branch-on-merge.

The one carve-out: a batch of confirmed `size:tiny` follow-ups may share one
worker, one branch and one PR, with a `Closes #N` line per ticket.

Every ticket and its PR name one responsible person as assignee. Triage
sets it alongside the `model:*` label — the label approves, the assignee
names who works it. An agent works only tickets assigned to the `gh` user
it runs as, `@me`, and its PR carries that same assignee.

## Follow-ups

A follow-up starts from `/done`, a kata worker, any agent mid-task, or the
maintainer — this section binds all of them, and nowhere else restates it.

Every follow-up carries `follow-up` and exactly one category: `correctness`,
`clarity`, `security`, `performance`, or `scope`. `scope` covers work deferred
with nothing broken — a deferred scope, an added `TODO`/`FIXME`, a waiver, a
parked idea. `bug` never goes on a follow-up; it stays the outside-reporter
form's label.

The filer proposes `size:tiny` when the ticket is tiny: its evidence names
one location, it leaves no design choice open, and it needs no new file,
dependency or config key. The maintainer confirms the proposal by adding its
model label. A follow-up is never born with a `model:<name>` label or an
assignee — triage sets both — and a label-creation step must never add the
label to an untriaged follow-up.

Labels are created if missing; if creation is refused, file without them
rather than drop the item.

## voice

# Voice

No fluff. No preamble, no restating the question, no praise-framing, no closing
summary unless asked.

Answer first. Detail only if it changes the next action.

Short sentences. Plain words. Never use: delve, robust, comprehensive,
straightforward, leverage, furthermore, "it's worth noting".

No hedging unless the uncertainty is real and material.

No confident figure without a measured baseline. A savings or speedup number for
code that was never written or benchmarked is invented, not reported.

Lists and code over paragraphs.

Private docs, issues and PR bodies: no preamble, no restating the brief, no Overview
section, no "This PR introduces…", no closing summary. Defect in the title, then
repro, expected/actual, evidence. Tighten the section you edit; design docs and
ICD notes keep their rationale.

<!-- END mutation-gate rules -->
