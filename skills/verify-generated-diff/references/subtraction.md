# Pass B — Subtraction

Goal: find out which of the defensive code the change added is actually
load-bearing, and which is absorbing violated invariants in silence.

Generated code accretes guards, wrappers, clamps, and catch-alls that read as
prudent. Some are load-bearing. Some are dead. The dangerous middle case is a
guard that quietly swallows a condition meaning something upstream is broken —
turning a loud bug into a mystery three weeks later.

## The important correction

The naive version of this idea is "delete it; if nothing breaks it wasn't
needed." That is wrong, and stating it that way produces bad deletions.

**Survival means the tests don't cover it.** Whether the code is *also*
unnecessary is a separate question that no test run can answer. Resolve each
survivor with a question you answer yourself:

> Can I construct an input that reaches this line and misbehaves without the
> guard?

| Deletion | Breaking input constructible? | Verdict | Action |
|---|---|---|---|
| KILLED | — | load-bearing, tested | leave it |
| SURVIVED | yes | load-bearing, **untested** | write that test |
| SURVIVED | no — invariant guaranteed upstream, and you can point to where | dead defensiveness | delete it |
| SURVIVED | unsure | unknown | guard → assertion + counter |
| BUILD-FAIL | — | structural, not a guard | not a candidate |

Row 3 requires *pointing at the guarantee* — a type, a validated boundary, an ICD
constraint. "I couldn't think of one" is row 4, not row 3.

## Enumerating candidates

```bash
scripts/survey.sh reviewed          # swallowed-exception section is exactly this
```

Or directly:

```bash
git diff -M reviewed | grep -E '^\+' | grep -nE \
  'if[[:space:]]*\([[:space:]]*!|== *nullptr|!= *nullptr|\.empty\(\)|is None|\
catch|except|assert|clamp|max\(0|return false;|return \{\};|return None'
```

Layers rather than guards — a new wrapper with one call site, a new file that
only forwards — show up in the new-files section of the survey. Those get
inlined by hand rather than deleted by substitution.

## Running a deletion

Same harness; the replacement is the `<DELETE>` sentinel in a TSV, or an empty
string on the command line. Include enough surrounding text that the match is
unique, and keep the trailing newline so you don't leave a blank line behind.

```bash
scripts/mutate.sh src/trk/track.cpp '  if (!m.valid) return;
' '' trk_track
```

In a TSV — note the sentinel, because an empty field is ambiguous and a
mis-parsed row yields a confident wrong answer:

```
src/trk/track.cpp	  if (!m.valid) return;\n	<DELETE>	trk_track
src/trk/gate.cpp	  if (dof < 1 || dof > 6) dof = 3;\n	<DELETE>	trk_gate
```

## The guard → assertion conversion

The most useful outcome of this pass. A guard you can neither justify nor
disprove should stop silently absorbing the case and start announcing it:

```cpp
// was:  if (!m.valid) return;                    // silently drops
// now:
assert(m.valid && "caller must filter invalid measurements");
if (!m.valid) { ++stats_.dropped_invalid; return; }
```

Two properties worth having: the assertion catches it in debug and test builds,
and the counter means you learn it happens in production instead of never.

**In a real-time or hot path, prefer a counter to an abort.** A 50 Hz cycle must
not stall on a diagnostic. Increment a stat, and log at most once per second or
once per N occurrences. The goal is audibility without a deadline miss.

**Rate-limit the log, not just the check.** An unthrottled log on a per-frame
condition is itself a hot-path hazard — it allocates, formats, and may block on
IO. That's how a diagnostic becomes the outage.

## Swallowed exceptions

Separate and non-negotiable. Any catch-all introduced by the change that does not
rethrow, log with context, or set an error state is removed or narrowed. There is
no version of this pass where a silent catch-all survives.

```bash
git diff -M reviewed | grep -E -A4 '^\+.*(catch|except)'
```

Common generated forms to reject: `catch (...) { return false; }`,
`except Exception: pass`, `.unwrap_or(default)` on a fallible parse,
`if err != nil { return nil }`. Each converts a diagnosable failure into a wrong
answer.

## Layers

For a wrapper rather than a guard, the mechanical test is: inline it by hand and
see whether anything but the line count changes. One at a time. A layer that
survives inlining unchanged was indirection without abstraction.

Resist deleting a layer that has one call site *today* but is named for a
plausible second one — check whether the second caller exists in the change's
intent. Sometimes the layer is right and the missing caller is the bug.

## A limitation to check for on every KILLED deletion

Deleting a guard can leave syntactically invalid code — a `try:` with no
`except`, an `if` with no body, an unbalanced brace. In a compiled language the
harness reports that honestly as BUILD-FAIL. In a language with no separate build
step it fails at test time and is reported as **KILLED**, which is
indistinguishable from a real kill and reads as reassuring.

So for every KILLED deletion, confirm the mutant was actually valid code:

```bash
export BUILD_CMD='python -m compileall -q .'   # Python
export BUILD_CMD='npx tsc --noEmit'            # TypeScript
export BUILD_CMD='ruby -c gate.rb'             # Ruby
```

Setting a real syntax check as `BUILD_CMD` moves these into the BUILD-FAIL bucket
where they belong. Without it, deleting a lone `except` branch looks like proof
the guard was load-bearing when it only proves the file stopped parsing.

The general rule, and the reason this matters more than it sounds: a deletion is
only informative if the resulting program is one the language would accept.
Otherwise you have tested the parser.

## Hygiene

Never leave a deletion in place. The harness reverts on every exit path, but if a
run is interrupted, check `git status` and `git diff` before doing anything else.

Do the deletions one at a time, not in batches. Two simultaneous deletions can
mask each other, and you can't tell which one the test result refers to.
