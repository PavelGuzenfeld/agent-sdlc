# Pass A — Mutation

Goal: find out whether the tests test anything, before spending attention on
whether the code is right.

Contents:
- [The four mutants](#the-four-mutants)
- [Writing a stub mutant](#writing-a-stub-mutant)
- [Choosing targets](#choosing-targets)
- [Classifying results](#classifying-results)
- [Acting on survivors](#acting-on-survivors)
- [Traps](#traps)
- [Slow and flaky suites](#slow-and-flaky-suites)

## The four mutants

One of each per target function. They are chosen because each maps to a distinct
real-world bug class, and because between them they cover the ways a test can be
vacuous.

| Mutant | Edit | Bug it stands for | If it survives |
|---|---|---|---|
| **Boundary** | `<`↔`<=`, `>`↔`>=`, `n`↔`n-1` | off-by-one, gate edges, buffer bounds | no test pins the edge |
| **Constant** | `dt*dt/2`→`dt*dt`, `0.5`→`1.0`, `2`→`3` | wrong coefficient, wrong scale | no test checks a computed value |
| **Branch** | condition → `true`, then → `false` | branch never exercised | one whole path is unverified |
| **Stub** | inject an early return at the top of the body | — | **the test is worthless, not weak** |

Run boundary and constant first (cheap, specific), then branch, then stub. The
stub is the one that changes your assessment: a function whose body can be
replaced by `return true` while the suite stays green has no test at all,
whatever the coverage report says.

## Writing a stub mutant

The substitution must match exactly once, so anchor on the signature line and
re-emit it with an injected return.

```bash
# C++
scripts/mutate.sh src/trk/gate.cpp \
  'bool Gate::accept(const Meas& m) const {' \
  'bool Gate::accept(const Meas& m) const { return true;' \
  trk_gate

# Python
scripts/mutate.sh gate.py \
  'def accept(self, d2, thresh):' \
  'def accept(self, d2, thresh):\n        return True' \
  test_gate.py

# Rust
scripts/mutate.sh src/gate.rs \
  'pub fn accept(&self, d2: f64) -> bool {' \
  'pub fn accept(&self, d2: f64) -> bool { return true;' \
  gate

# Go
scripts/mutate.sh gate.go \
  'func (g *Gate) Accept(d2 float64) bool {' \
  'func (g *Gate) Accept(d2 float64) bool { return true;' \
  TestGate
```

Return value by type: `bool` → both `true` and `false` (they can differ);
numeric → `0` and a plausible non-zero; struct/object → the zero value
(`{}`, `None`, `Default::default()`); `void` → a bare `return`.

For `void` functions with side effects, stubbing the body is the *only*
meaningful mutant — there's no return value to corrupt — so don't skip it there.

Compilers will warn about unreachable code after the injected return. That's
cosmetic; the harness only cares whether the build succeeds. If warnings are
errors in this project, inject the return via a condition the compiler can't
fold: `if (m.id >= 0) return true;`.

## Choosing targets

Three or four functions. Want real decisions; skip plumbing.

```bash
git diff --numstat -M reviewed | sort -k1 -nr | head
git diff -M reviewed | grep -E '^\+' | grep -cE '\b(if|for|while)\b|[<>]=?|\*|/'
```

Then read the changed names for domain verbs — `predict`, `update`, `gate`,
`associate`, `validate`, `wrap`, `normalize`, `quantize`, `parse`, `pack`,
`merge`, `resolve`. Those are where a wrong answer is plausible and silent.

Deprioritize: constructors, getters/setters, logging, pure forwarding, anything
whose body is a single call.

If the diff is large enough that you can't identify targets, stop. That's a
finding about the change, not a reason to mutate randomly.

## Classifying results

| Result | Meaning | Next |
|---|---|---|
| **KILLED** | a test went red | that test does real work; move on |
| **SURVIVED** | green with wrong logic | **the finding** — write the killing test |
| **SURVIVED on a stub** | the function's test asserts nothing real | rewrite the test from the spec, or drop the coverage claim |
| **BUILD-FAIL** | compiler caught it | no information about the tests; rewrite type-correct |
| **REFUSED** | dirty file, untracked file, or baseline red/filter matches nothing | fix the setup; do not interpret |

`BUILD-FAIL` is not a pass. It means the mutant was badly chosen — the type
system, not the test suite, rejected it. Rewrite so the mutant compiles.

## Acting on survivors

In this order, for each survivor:

1. **Write the test that would have killed it — from the spec, ICD, datasheet,
   or ticket.** Writing it from the code reproduces exactly the problem you are
   trying to detect. If no spec exists, say so; the best available result is then
   "internally consistent," which is weaker and the user should know it.
2. **Re-run the mutant.** It must now be KILLED. If it isn't, the new test is
   also tautological — a common outcome when the test was written while looking
   at the implementation.
3. **Commit the test alone**, separately from any production fix, so the history
   shows a test that fails against the mutant and passes against correct code.
4. **Add the mutant to the TSV permanently.** It is now a regression check on
   the test suite, which nothing else in the toolchain provides.

## Traps

**Equivalent mutants.** Some mutants produce semantically identical code
(`i <= n-1` vs `i < n`; `x*1`; reordering commutative operands). These survive
for a legitimate reason and are not findings. When a survivor looks surprising,
first check whether the mutant actually changed behavior.

**Mutants outside the tested surface.** A mutant in code the filter's tests never
reach will always survive and tells you nothing about the tests you're auditing.
Match the filter to the target.

**Coverage is not mutation.** 100% line coverage coexists comfortably with a
surviving stub mutant: the lines execute, nothing asserts on the result. When
coverage and mutation disagree, mutation is measuring the thing you care about.

**Mutating the tests.** Never mutate test files. Mutate production code and
observe the tests. Mutating a test only tells you whether the test file compiles.

**Don't fix the code from the mutant.** A survivor is evidence about the *tests*.
Whether the original code is also wrong is a separate question, answered by
Pass C and the spec.

## Slow and flaky suites

Budget is roughly `4 mutants × 4 functions = 16` runs. At 20 s each that's ~6
minutes of machine time. If the build dominates:

- build a single test target, never the tree (`BUILD_TARGET`)
- enable a compiler cache; disable unity builds while doing this
- narrow the filter to the tests that touch the target

If the suite is flaky, mutation is unusable — every result is coin-flip noise.
Establish stability first: run the baseline five times and confirm five greens.
Report flakiness as a blocking finding rather than working around it, because a
flaky suite cannot support any verification claim at all.
