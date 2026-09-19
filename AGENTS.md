## code-clarity

# Code clarity

Code is the documentation. It is written for humans and only incidentally for
machines. Clarity comes from naming, types, and structure — never from prose
sitting next to the code.

Reach for a better name, a smaller function, or an explicit type before reaching
for a comment. A comment that explains *what* the code does means the code is
unclear: fix the code, then delete the comment.

## Hard limits

- Comments: **zero.** No hand-written `#` or `//` comments in new code, in repos I
  own. Carve-outs: pragmas (`# pyright: ignore`, `# noqa`, `NOLINT`), shebangs,
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
  owns: stop and run `/upstream` — the fix may belong in the dependency.
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
`sg` is NOT ast-grep here; it is the `setgroup` binary. Always `ast-grep`.
Use it to audit too: a structural question deserves a pattern, not a grep heuristic.

## model-vv

# Model verification & validation

Fires on any change to estimation or filter math, coordinate or frame transforms, angle
handling, timestamps/dt, sensor or observation models, noise parameters, physical constants,
or the model spec.

**Tiered.** Layers 1, 2 and 4 on any trigger. Layers 0, 3 and 5 only when the model itself
moves — F/Q, h(x), noise parameters, calibration constants, envelope. Symbolic and order-of-
magnitude work runs in a container, never in-head. Commit the script.

## Layer 0 — Spec
- `model_spec = "issue:N"` in `.mutation-gate.toml`, lines numbered `MS-n`: phenomena
  modelled; effects deliberately neglected, with justification; validity envelope (state
  ranges, dt, manoeuvre intensity); required accuracy per envelope region; noise assumptions.
  The file path is not an option.
- Absent → draft the skeleton from the code as the body of a new tracking issue, tag every
  line `(reconstructed)` or `(needs intent)`, **stop**. A spec derived from the implementation
  can only agree with it. The intent lines are Pavel's.
- Every test under this file cites its spec line in its one-line docstring: `"""MS-7: Q stays
  PSD across the dt envelope."""`. No traceable line means the spec is incomplete (propose the
  line) or the test is unrequested (drop it).
- Neglected-effects audit on any envelope or model change: enumerate every physical effect
  plausibly relevant inside the envelope, order-of-magnitude estimate with units at the worst
  envelope point, one verdict each — included, negligible (show the margin), or flagged
  (within 10× of the noise floor). Flagged goes in the spec as an open assumption.
- Literature grounding: cite the canonical reference per modelling choice, put its stated
  validity conditions next to our envelope. Mismatches are flagged, never resolved silently.
- Blind pass before merge: subagent, code only — no spec, no conversation — reconstructs
  intent, neglected effects and envelope, diffed against the spec. Divergence means the intent
  is not in the code. This file authorises the subagent; it reports, never blocks. It is not
  testing.md's adversary — opposite blindfold. Run both.
- A CAS calculates. It never adjudicates sufficiency; Pavel does.

## Layer 1 — Before editing
- Assumption inventory for the touched code, one line each: frame, units, time base, noise
  model, linearisation, discretisation. Read out of the code, never out of the request.
  Conflict with what Pavel said → stop and flag.
- Derive every numeric tolerance (float precision, dt order) and state the derivation. Never
  tune one until it goes green.

## Layer 2 — Units at every boundary
- Dimensioned quantities never cross a function boundary as raw scalars. Distinct type per
  quantity kind — bearing and elevation are different types, both in radians. Retrofit
  boundaries first (parsers, transforms, sensor models); interiors only when already touched.
- C++: `strong-types`, or the project's own units library. Python: `NewType` under pyright.
- Conversions are explicit named calls — no implicit conversion, no bare literal. Angle types
  carry their wrap convention.
- Mixing kinds must fail the checker. One negative check per new kind: compile-fail test in
  C++, pyright type-error test in Python.

## Layer 3 — Symbolic golden
- Continuous-time model (A, G, Qc, state ordering) lives as SymPy source in the repo. F and Q
  are a generated artefact carrying the source hash, regenerated in CI. Never hand-transcribed.
- Validate the golden before trusting it: van Loan and the direct integral agree symbolically;
  scipy `expm` matches at sampled dt; CV/CA blocks match closed form exactly; F→I and Q→0 as
  dt→0; Q symmetric PSD at every sampled dt; LTI exactly F(2dt)=F(dt)² and Q(2dt)=F Q Fᵀ + Q;
  `sympy.physics.units` on every symbol, each Q entry carrying the state-pair product units;
  Euler–Maruyama at dt/1000 on the continuous SDE, increment sample covariance inside the CI.
- Implementation matrices match the golden across a dt sweep at the derived tolerance.
- No continuous-time model (learned gain, empirical process noise) → one line in the spec
  saying so, and Layers 4 and 5 carry the load. The analytic baseline a learned filter is
  benchmarked against is model code; Layer 3 applies to it.

## Layer 4 — Tests for the change
- Jacobians: analytic vs central differences over random states, sampled deliberately near
  singularities and angle wraps.
- Metamorphic (RapidCheck, hypothesis) wherever the kernel is callable in isolation: rotation
  invariance, +2π invariance, measurement-order independence, irregular vs regular timestamps
  on one trajectory. Semigroup predict(dt)∘predict(dt)==predict(2dt) for linear submodels only;
  nonlinear get a tolerance scaling with dt².
- Numerics: Joseph form, symmetrise P, check cond(S) before inverting, run one trajectory in
  float and in double and report the divergence.
- h(x) or a calibration constant changed → residual test: residuals zero-mean and uncorrelated
  with the measurement coordinates and the sensor pose.

## Layer 5 — Consistency harness
- Monte Carlo NEES/NIS against chi-square bands, innovation autocorrelation lags 1–5,
  innovation bias regressed on velocity — report the slope as a latency estimate.
- The truth generator shares no code and no model with the filter. At least one
  deliberate-mismatch case; report the degradation, not pass/fail.
- Chi-square bands assume Gaussian innovations — say so. Where the repo has an empirical error
  distribution, use that instead.
- Higher-fidelity generator available → sweep the spec envelope, report where the model breaks,
  compare against the spec boundary.

## Reporting
- One row per group of tests sharing a spec line and an oracle (symbolic, metamorphic,
  statistical, ground truth, literature), with the tolerance and its derivation. A standalone
  test is its own group.
- Verification, not validation, unless real ground truth was used. None → say so in one line.
- Flags from the audit, literature pass and blind pass: listed individually, last, never buried.

## Carve-outs
- V&V artefacts — spec, SymPy source, golden, harness, tests — are exempt from
  diff-discipline's 40-line stop and its no-new-dependency rule; this file is the ask that
  authorises them. The production diff stays bound. Report the counts split.
- Runtime asserts (Cholesky success, P symmetry, trace monotonicity): hard in debug, counter
  plus periodic report in release. Never add allocation, locking or logging to the real-time
  path. Existing real-time carve-outs still apply.
- The mutation gate enforces Layer 0 mechanically (dotfiles#56): spec present (the pinned
  issue resolves) when a `model_paths` file changes, a diff-touched model test cites an
  `MS-n` that exists and is
  untagged, and a keyword probe blocks once on model code not declared in `model_paths`. A
  declared `[[golden]]` artefact must carry its SymPy source's sha256 (Layer 3). On green, the
  Layer 0 blind pass runs over `model_paths` — code only — and reports.
- Layers 1, 2, 4 and 5 have no hook. They hold because they are read.

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

Spec and all 29 decisions: `PavelGuzenfeld/dotfiles#9`.

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

This binds repos I own. An upstream tree keeps its own doc conventions.

## Model spec

model-vv.md Layer 0 no longer defaults to a file. Its `MS-n` lines live in one
pinned ticket, named by `model_spec = "issue:N"` in the repo's own gate config.
Where the tracker itself lives is that repo's business, never named in a rule
file.

## One ticket, one branch, one PR

An approved ticket is the plan, and satisfies diff-discipline's stop on its own
— no ticket, no change past the line-count limit; open one first. A ticket maps
to exactly one branch and one PR, and the PR body carries `Closes #N`. Every
repo I own defaults to squash-only merges with delete-branch-on-merge.

At work the same ticket-and-slice discipline applies; nothing here changes for
that context.

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
