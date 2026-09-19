# Pass C — Interrogation

Goal: convert vague familiarity into claims that a tool can confirm or refute.

The failure mode this pass exists to avoid: asking for an explanation, receiving
fluent accurate-sounding prose, and absorbing it as understanding without a
single claim having been checked. That is worse than not asking, because it
removes the sense that anything remains to be checked.

So: **never ask for an explanation. Ask for an enumeration, then verify each
item with a tool.** A question without its verifier is not part of this pass.

## The question set

### 1. "List every assumption this function makes about its inputs that it does not validate."

Expect: ranges, non-null, non-empty, sortedness, units, frame of reference,
monotonic timestamps, normalized angles, alignment, ownership.

**Verify:** for each claimed assumption, write the test that violates it. An
assumption you can't violate in a test either isn't real or is enforced
somewhere you haven't found — check which:

```bash
git grep -n 'assert\|require\|expects\|static_assert' -- <dir>
```

### 2. "What units, frame, scale, and wrap range does each parameter use, and where is that documented?"

Ask this explicitly and separately. It is the highest-yield question on
generated code in numerical, embedded, or protocol work, because the model
produces the plausible shape and gets the convention wrong, and the compiler is
silent: radians vs degrees, body vs world frame, fixed-point scale factor,
`[0, 2π)` vs `(-π, π]`, milliseconds vs microseconds, big vs little endian,
row vs column major.

**Verify against the spec or ICD, not against other code.** Other code may share
the same wrong assumption. If the convention is undocumented, that is the finding
— document it and add a test that pins it.

### 3. "What breaks if this is called from two threads?"

**Verify with a sanitizer, not by reading.** Note that a sanitizer only reports
races it actually observes, so the answer's value is in telling you which
two-thread test to write:

```bash
# C/C++
cmake -B build-tsan -DCMAKE_BUILD_TYPE=RelWithDebInfo \
      -DCMAKE_CXX_FLAGS='-fsanitize=thread -g'
cmake --build build-tsan && ctest --test-dir build-tsan

# Go
go test -race ./...

# Rust
cargo +nightly test -Zsanitizer=thread
```

ASan/UBSan builds are worth the same ten minutes for the lifetime, aliasing, and
overflow questions.

### 4. "Which callers are affected if the return convention changes?"

**Do not trust the answer.** This is the question models get confidently wrong:
they invent call sites, miss macro and template instantiations, and mis-resolve
virtual dispatch and overloads. Use it only to generate candidates, then:

```bash
git grep -n '\bcompute_gate\b' -- '*.cpp' '*.h'   # textual, complete, dumb
```

Then an index-aware tool for the cases grep misses (indirect calls, overrides):
`xref-find-references` / LSP references. **Regenerate the compile database on
this branch first** — a stale one produces wrong references that look
authoritative:

```bash
cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON && ln -sf build/compile_commands.json .
```

### 5. "What in this file is dead?"

**Verify with the compiler and a coverage report.**

```bash
cmake --build build 2>&1 | grep -iE 'unused|never used|set but not'

cmake -B build-cov -DCMAKE_CXX_FLAGS='--coverage -O0 -g'
cmake --build build-cov && ctest --test-dir build-cov
gcovr --filter src/ --txt | sort -k4 -n | head -20
```

Zero-coverage lines in a brand-new file are the honest version of the answer.
Cross-check them against the Pass B survivor list; the overlap is where the
remaining time should go.

### 6. "What did you choose not to do, and what were you unsure about?"

Only useful when asked of the session that produced the code, and only partially
reliable — but non-empty, and it points somewhere. It's a partial substitute for
the hesitation texture that generated code otherwise lacks: in human code, an
awkward name, a defensive check, or a comment marks where the author was
uncertain, and experienced reviewers navigate by that gradient without noticing.
Generated code is uniformly confident, so the surface offers no gradient.

## Question hygiene

**Open, not leading.** "What does this function assume about its inputs?" not "is
this correct?" The second reliably gets agreement, from a model and from a
colleague.

**Interrogate from a fresh context.** Give it the diff without saying it was
generated. A fresh context has only the code to reason from — the same position
the reviewer is in. If it cannot justify a line from the code alone, that is a
fact about the code, not about the model.

**Ask for the negative case.** "What input would make this return the wrong
answer?" outperforms "are there bugs?" because it demands a constructible
artifact you can turn into a test.

**Treat every answer as a candidate list.** Items are findings only once their
verifier has run. Report verified items as findings and unverified ones as open
questions; never merge the two.

## What to do with the results

Each verified item becomes one of: a new test, a documentation line, a code fix,
or an entry in the "not established" section of the report. Nothing verified
should end up only in your own head — the durable artifact is the written
convention (`ARCHITECTURE.md`, `CLAUDE.md`, the header comment), because it is
simultaneously your retained model and the context that stops the next session
reinventing the same helper with different error semantics.
