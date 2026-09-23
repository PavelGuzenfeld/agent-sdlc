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
