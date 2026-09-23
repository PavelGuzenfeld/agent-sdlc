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
  can only agree with it. The intent lines are the maintainer's.
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
- A CAS calculates. It never adjudicates sufficiency; the maintainer does.

## Layer 1 — Before editing
- Assumption inventory for the touched code, one line each: frame, units, time base, noise
  model, linearisation, discretisation. Read out of the code, never out of the request.
  Conflict with the request → stop and flag.
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
- The mutation gate enforces Layer 0 mechanically: spec present (the pinned
  issue resolves) when a `model_paths` file changes, a diff-touched model test cites an
  `MS-n` that exists and is
  untagged, and a keyword probe blocks once on model code not declared in `model_paths`. A
  declared `[[golden]]` artefact must carry its SymPy source's sha256 (Layer 3). On green, the
  Layer 0 blind pass runs over `model_paths` — code only — and reports.
- Layers 1, 2, 4 and 5 have no hook. They hold because they are read.
