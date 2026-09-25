# Verifying a Generated Diff: Three Passes

A practical procedure for the case where an agent produced code *and* the tests
for it, so the tests cannot be trusted as a specification. C++/CMake/ctest
assumed; the shape transfers to anything with a build and a test runner.

The three passes answer three different questions:

| Pass | Question | Perturbation |
|---|---|---|
| **A. Mutation** | Do the tests test anything? | Corrupt the logic |
| **B. Subtraction** | Is this code load-bearing? | Remove the code |
| **C. Interrogation** | What does this assume? | None — you read and check |

All of A and B are the same loop:

```
perturb  →  build  →  test  →  classify  →  revert (always)
```

Run them in that order. Pass A first, because there is no point reasoning about
code whose tests are decorative.

---

## 0. Setup (once per repo)

### 0.1 Make the loop fast

Mutation is `N` rebuilds. If a rebuild is four minutes, twelve mutants is an
hour and you will not do it. Get the incremental build under ~20 seconds:

```bash
sudo apt install ccache
cmake -B build -G Ninja \
  -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo

# Find the one target you actually need, and build only that
ctest --test-dir build -N                    # list tests
cmake --build build --target trk_filter_test # not the whole tree
```

Turn off unity builds while doing this if you have them on — they make a
one-line edit rebuild the world.

### 0.2 The harness

Use this skill's `scripts/mutate.sh` and `scripts/run_mutants.sh`; the inline
copy that used to be here predated their baseline and untracked-file guards.

Mutants are worth keeping, so put them in a file rather than typing them.
`mutants.tsv`, tab-separated, `#` for comments, `<DELETE>` for a deletion —
never an empty field:

```
# file<TAB>old<TAB>new<TAB>ctest-regex
src/trk/gate.cpp	d2 < gate_sq	d2 <= gate_sq	trk_gate
src/trk/gate.cpp	d2 < gate_sq	true	trk_gate
src/trk/predict.cpp	dt * dt / 2.0	dt * dt	trk_predict
```

Baseline first — if the suite is red before you start, every result is noise:

```bash
cmake --build build && ctest --test-dir build --output-on-failure
```

---

## 1. Pass A — Mutation: do the tests test anything?

### Step 1: pick the targets (5 min)

You want the three or four functions carrying real logic, not the plumbing.
Two ways to find them:

```bash
# a) biggest logic files in the change
git diff --numstat -M reviewed -- '*.cpp' '*.h' | sort -k1 -nr | head

# b) functions with actual decisions in them — comparisons, arithmetic, loops
git diff -M reviewed | rg '^\+' | rg -c '\b(if|for|while|else)\b|[<>]=?|\*|/'
```

Then eyeball for domain verbs: `predict`, `update`, `gate`, `associate`,
`wrap`, `normalize`, `quantize`, `pack`. Those are where a wrong answer is
plausible and silent. Skip constructors, getters, logging, and anything that
just forwards.

### Step 2: write four mutants per function

One of each kind. This set is chosen because each maps to a distinct real bug:

| Mutant | Edit | Catches |
|---|---|---|
| **Boundary** | `<` → `<=`, `>` → `>=` | off-by-one, gate edges |
| **Constant** | `dt*dt/2.0` → `dt*dt`, `0.5` → `1.0` | wrong coefficient |
| **Short-circuit** | condition → `true` (or `false`) | branch never exercised |
| **Stub** | first statement of body → early return | test asserts nothing real |

The **stub** is the important one and the awkward one to express as a string
substitution. Match the line right after the signature:

```bash
BUILD_TARGET=trk_filter_test <skill-dir>/scripts/mutate.sh src/trk/gate.cpp \
  'bool Gate::accept(const Meas& m) const {' \
  'bool Gate::accept(const Meas& m) const { return true;' \
  trk_gate
```

For a `void` function, stub with a bare `return;`. For one returning a struct,
`return {};`.

### Step 3: run and classify

```bash
BUILD_TARGET=trk_filter_test <skill-dir>/scripts/run_mutants.sh
```

Four outcomes, three of which are informative:

- **KILLED** — a test went red. That test is doing real work. Good.
- **SURVIVED** — tests stayed green with wrong logic. **This is the finding.**
- **BUILD-FAIL** — the compiler caught it. No information about the tests; the
  mutant was badly chosen. Rewrite it as something type-correct.
- **SURVIVED on a stub** — the test for that function is worthless. Not "weak."
  Worthless. Delete it and write one, or drop the coverage claim.

### Step 4: act on survivors

For each survivor, in this order:

1. Write the test that would have killed it. Write it *from the spec or the ICD*,
   not from the code — otherwise you have reproduced the original problem.
2. Re-run the mutant. It must now be KILLED. If it isn't, your new test is also
   tautological.
3. Commit the test on its own, separately from any production change, so the
   history shows the test failing against the mutant.

Add the mutant to `mutants.tsv` permanently. It's now a regression check on
your test suite, which is a thing you otherwise have no regression check on.

### Realistic budget

Four functions × four mutants = 16 runs. At 20 s per run that's ~6 minutes of
machine time and ~15 minutes of yours. If it's taking an hour, the build is the
problem, not the method — go back to 0.1.

---

## 2. Pass B — Subtraction: is this code load-bearing?

Generated code accretes guards, wrappers, and defensive layers that look
prudent. Some of them are absorbing invariant violations you would rather see
fail loudly. This pass finds out which.

### Step 1: enumerate the candidates

```bash
# guards and swallowing handlers added by this change
git diff -M reviewed | rg '^\+' | rg -n \
  'if\s*\(\s*!|== nullptr|!= nullptr|\.empty\(\)|catch\s*\(|assert\(|\
std::clamp|std::max\(0|return false;|return \{\};'

# indirection added: new single-call-site wrappers
git diff --diff-filter=A -M reviewed --stat   # new files are often new layers
```

### Step 2: delete one thing, run, revert

Same harness, `new` is the empty string. Substitution must be exactly one
occurrence, so include enough surrounding text:

```bash
<skill-dir>/scripts/mutate.sh src/trk/track.cpp \
  '  if (!m.valid) return;
' \
  '' \
  trk_track
```

For a wrapper layer rather than a guard, the mechanical version is to inline it
by hand and see whether anything but line count changes. Do that one at a time.

### Step 3: classify — this is where the earlier phrasing was wrong

Survival does **not** mean the code is dead. It means the tests don't cover it.
Resolve with a second question you answer yourself: *can I construct an input
that reaches this line and misbehaves without the guard?*

| Deletion result | Can you construct a breaking input? | Verdict | Action |
|---|---|---|---|
| KILLED | — | Load-bearing, tested | Leave it |
| SURVIVED | Yes | Load-bearing, **untested** | Write that test |
| SURVIVED | No, and the invariant is guaranteed upstream | Dead defensiveness | Delete it |
| SURVIVED | No, but you're unsure | Unknown | Convert guard → assertion |
| BUILD-FAIL | — | Structural, not a guard | Not a candidate |

The fourth row is the useful trick. A guard you can't justify and can't
disprove should stop silently absorbing the case and start announcing it:

```cpp
// was: if (!m.valid) return;                 // silently drops
// now:
assert(m.valid && "caller must filter invalid measurements");
if (!m.valid) return;                        // keep for release, but now audible
```

In a 50 Hz path prefer a counter over an abort — increment a dropped-frame stat
and log at most once per second. You want to *learn* it happens in the field
without stalling the cycle.

### Step 4: the swallowed-exception sweep

Separate and non-negotiable. Any `catch (...)` or `catch (const std::exception&)`
introduced by the change that does not rethrow, log with context, or set an
error state, is removed or narrowed. There is no version of this pass where a
silent catch-all survives review.

```bash
git diff -M reviewed | rg -A4 '^\+.*catch\s*\('
```

---

## 3. Pass C — Interrogation: turning prose into checkable claims

Asking a model "explain this module" produces fluent text you will absorb as
understanding without having verified one word of it. Ask instead for
*enumerable claims*, then check them with a tool. Each question below has a
verifier; the question is worthless without it.

### 3.1 "List every assumption this function makes about its inputs that it doesn't validate."

Expect: ranges, non-null, sortedness, units, frame of reference, monotonic
timestamps, normalized angles.

**Verify:** for each claimed assumption, write the test that violates it.

```bash
# then check the assumption isn't already enforced somewhere you missed
git grep -n 'assert\|expects\|Ensure' -- src/trk/
```

Domain-specific follow-up worth asking explicitly, because it's where generated
code is reliably wrong and the compiler is silent: *what units and what frame
does each parameter use, and where is that documented?* Radians vs degrees,
body vs NED, fixed-point scale, wrap range `[0,2π)` vs `(-π,π]`.

### 3.2 "What breaks if this is called from two threads?"

**Verify with a sanitizer, not by reading.**

```bash
cmake -B build-tsan -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_CXX_FLAGS='-fsanitize=thread -g'
cmake --build build-tsan && ctest --test-dir build-tsan
```

TSan only reports races it observes, so it needs a test that actually exercises
concurrent access — write the two-thread test the answer implies, then run it
under TSan. ASan/UBSan builds are worth the same 10 minutes for the lifetime
and overflow questions.

### 3.3 "Which callers would be affected if I changed the return convention?"

**Do not trust the answer.** This is the question models get confidently wrong —
they invent call sites and mis-resolve overloads and virtual dispatch. Use it
only to generate candidates, then:

```bash
git grep -n '\bcompute_gate\b' -- '*.cpp' '*.h'   # textual, complete, dumb
```

In Emacs: `xref-find-references` via clangd, plus `lsp-find-implementation` for
virtuals. **clangd needs `compile_commands.json` regenerated on this branch** —
a stale one produces wrong references that look authoritative:

```bash
cmake -B build -G Ninja -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
ln -sf build/compile_commands.json .
```

### 3.4 "What in this file is dead?"

**Verify with the linker and the coverage report, not the answer.**

```bash
# compiler's own opinion
cmake --build build -- -k0 2>&1 | rg -i 'unused|never used|set but not'

# what the tests actually reach
cmake -B build-cov -DCMAKE_CXX_FLAGS='--coverage -O0 -g'
cmake --build build-cov && ctest --test-dir build-cov
gcovr --filter src/trk --txt | sort -k4 -n | head -20
```

Zero-coverage lines in a brand-new file are the honest version of "what's dead."
Cross-check them against your Pass B survivor list — the overlap is where to
spend the rest of your time.

### 3.5 Question hygiene

- **Open, not leading.** "What does this assume about its inputs?" not "is this
  correct?" The second gets you agreement.
- **From a fresh session**, given the diff, not told it was generated. It then
  has only the code to reason from, same as you. If it can't justify a line from
  the code alone, that's a fact about the code.
- **Answers are candidate lists.** Every item gets a verifier from above or it
  doesn't count.

---

## 4. Worked example

Agent adds `src/trk/gate.cpp` — Mahalanobis gating for measurement
association — plus `tests/trk_gate_test.cpp`. 140 lines. Tests green.

```bash
git tag -f reviewed HEAD~1
export BUILD_TARGET=trk_gate_test
cmake --build build && ctest --test-dir build -R trk_gate     # baseline green
```

**Pass A.** Four mutants on `Gate::accept`:

```
KILLED      src/trk/gate.cpp   d2 < gate_sq -> d2 <= gate_sq
SURVIVED    src/trk/gate.cpp   d2 < gate_sq -> true
SURVIVED    src/trk/gate.cpp   chi2_thresh(dof) -> 9.21
SURVIVED    src/trk/gate.cpp   <stub: return true;>
```

Read: the boundary is pinned, but nothing tests *rejection*. A stub that accepts
everything passes the suite. So the tests assert that valid measurements are
accepted and never that invalid ones are rejected — half the function is
unverified, and it's the half that matters. Write the rejection test from the
chi-square table, re-run, confirm KILLED.

**Pass B.** Three candidates:

```
KILLED      if (!S.llt().info() == Eigen::Success) return false;
SURVIVED    if (dof < 1 || dof > 6) dof = 3;
SURVIVED    try { ... } catch (...) { return false; }
```

Row 2: can I construct a breaking input? `dof` comes from measurement
dimension, which the ICD fixes at 3 — so silently clamping is masking a
condition that means something upstream is broken. Convert to assertion plus a
counter. Row 3: catch-all in a 50 Hz path swallowing an Eigen throw. Narrow it
or remove it.

**Pass C.** Fresh session, given the file: "what does `accept` assume about `S`
that it doesn't check?" → *symmetric, positive-definite, in the same frame as
the residual, residual angle already wrapped to `(-π,π]`*. The wrapping claim
is checkable and turns out to be assumed and undocumented, with the caller
wrapping to `[0,2π)`. That's the actual bug in the change, and no test would
ever have found it.

Total: ~45 minutes. Three real findings, none of which came from reading the
diff top to bottom.

---

## 5. When to stop, and when not to start

**Stop when** the mutants on the logic functions are all KILLED, the Pass B
survivors are each resolved to a row of the table, and the Pass C claims are
each verified or refuted. That's a defensible "I understand this."

**Don't bother if** the change is under ~50 lines and you read it fully — the
passes cost more than the reading.

**Don't start if** the diff is over a few hundred lines of unfamiliar generated
logic. The passes assume you can already name the four functions that matter.
If you can't, the problem is upstream: split it, or regenerate it in reviewable
increments. `git diff --stat -M reviewed | tail -1` before you type `y`.

---

## 6. Cheat sheet

```bash
git tag -f reviewed                          # read pointer
git diff --stat -M reviewed | tail -1        # comprehension debt

# Pass A — do the tests test anything?
BUILD_TARGET=x_test <skill-dir>/scripts/run_mutants.sh     # boundary / constant / branch / stub
#   SURVIVED on a stub  = test is worthless
#   SURVIVED otherwise  = write the killing test, from the spec

# Pass B — is it load-bearing?
<skill-dir>/scripts/mutate.sh <file> '<guard>' '' <tests>
#   SURVIVED + breaking input exists  = untested, write the test
#   SURVIVED + invariant guaranteed   = delete
#   SURVIVED + unsure                 = assert + counter
git diff -M reviewed | rg -A4 '^\+.*catch\s*\('   # never let these through

# Pass C — verify, don't read
ctest --test-dir build-tsan                  # threads
git grep -n '\bsym\b'                        # callers (not the model's answer)
gcovr --filter src/ --txt | sort -k4 -n      # dead code
cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON  # or clangd lies to you
```

Invariant across all of it: **the tests are evidence only after you have
attacked them.** Green on code that was generated together with its own tests
is a statement about internal consistency, not about correctness.
