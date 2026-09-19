# Toolchain setup per language

The harness needs three things: a build command, a test command that accepts a
filter, and a fast incremental loop. Configure via environment variables.

```bash
export BUILD_CMD='...'     # anything; `true` if there is no build step
export TEST_CMD='...'      # use {filter} as the placeholder for the test filter
export BUILD_DIR=build     # used by the CMake defaults
export BUILD_TARGET=x_test # build only this target — usually the biggest win
```

`{filter}` is substituted literally. If a stack has no filter concept, ignore it
and the filter argument becomes inert.

**The loop speed decides whether this gets used.** Mutation is N rebuilds; at
20 s each it works, at four minutes it doesn't and nobody runs it twice. Getting
under ~20 s is worth doing before writing a single mutant.

---

## C / C++ (CMake + ctest) — the default

```bash
cmake -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

ctest --test-dir build -N          # list tests, pick the filter
export BUILD_TARGET=trk_gate_test  # not the whole tree
```

Defaults if unset: `cmake --build $BUILD_DIR -j$(nproc) [--target $BUILD_TARGET]`
and `ctest --test-dir $BUILD_DIR -R {filter}`.

Notes that matter here specifically:
- **Disable unity builds** while mutating; a one-line edit otherwise rebuilds a
  whole translation-unit blob.
- `ccache` helps most on revert (the restored file is a cache hit).
- Injected `return` statements produce unreachable-code warnings. Harmless unless
  warnings are errors — in that case inject behind a condition the compiler can't
  fold: `if (m.id >= 0) return true;`.
- Regenerate `compile_commands.json` after switching branches or worktrees, or
  clangd will confidently report wrong call sites.

### Meson / Bazel / plain make

```bash
export BUILD_CMD='meson compile -C build'
export TEST_CMD='meson test -C build {filter}'

export BUILD_CMD='true'   # bazel builds as part of test
export TEST_CMD='bazel test //...:{filter}'

export BUILD_CMD='make -j$(nproc) unit_tests'
export TEST_CMD='./unit_tests --gtest_filter={filter}'
```

---

## Python

```bash
export BUILD_CMD='python -m compileall -q .'
export TEST_CMD='python -m pytest -q -x {filter}'
```

Use a real syntax check rather than `true` as `BUILD_CMD`. Interpreted languages
have no build step, so a mutant that leaves invalid syntax — a `try` with no
`except`, an `if` with no body — fails at test time and gets reported as KILLED,
which is indistinguishable from a real kill and reads as reassuring.
`compileall` moves those into the BUILD-FAIL bucket where they belong.

Filters: a path (`tests/test_gate.py`), a node id
(`tests/test_gate.py::test_reject`), or `-k` expression — put `-k` in the
command if you prefer: `python -m pytest -q -k "{filter}"`.

Stub mutants need the indentation to match the file, and `\n` in a TSV expands to
a real newline:

```
gate.py	    def accept(self, d2):	    def accept(self, d2):\n        return True	tests/test_gate.py
```

`-x` (stop on first failure) speeds up KILLED cases considerably.

---

## Rust

```bash
export BUILD_CMD='cargo build --tests'
export TEST_CMD='cargo test {filter} -- --quiet'
```

Rust's type system converts many mutants into BUILD-FAIL, which is not a result.
Prefer mutants that stay type-correct: boundary flips, constant changes,
`unwrap_or` defaults, and stubs returning `Default::default()` or `true`/`false`.

`cargo-mutants` is the mature tool here and does this properly — if it's
available, use it for Pass A and keep this harness for Pass B deletions, which
`cargo-mutants` doesn't do.

---

## Go

```bash
export BUILD_CMD='go build ./...'
export TEST_CMD='go test -run {filter} ./...'
```

Filter is a regex over test names (`TestGate`). `go vet` catches some badly
chosen mutants before the build does.

---

## TypeScript / JavaScript

```bash
export BUILD_CMD='npx tsc --noEmit'      # or 'true' for plain JS
export TEST_CMD='npx vitest run {filter}'
# or: export TEST_CMD='npx jest {filter} --silent'
```

Type-check as the build step so type-invalid mutants are correctly reported as
BUILD-FAIL rather than as spurious KILLED.

---

## Existing mutation-testing tools

Where a mature tool exists, it will do Pass A better and more exhaustively than
this harness: `cargo-mutants` (Rust), `mutmut` / `cosmic-ray` (Python),
`Stryker` (JS/TS/C#), `PIT` (JVM), `mull` (C/C++ via LLVM).

Prefer them for Pass A when available. Two reasons to still use this harness:

1. **Pass B has no tool.** Deleting guards and classifying against the
   constructible-input question is manual by nature, and it produces the
   guard→assertion findings that matter most.
2. **Targeted beats exhaustive under time pressure.** Four hand-chosen mutants on
   the function you suspect answers the question in six minutes. A full mutation
   run on a C++ tree can take hours and buries the answer in noise.

Report it honestly if a mature tool exists and wasn't used, and say why.

---

## Real-time and embedded targets

When the code runs on a target that isn't the build host — Jetson, MCU, DSP —
mutation runs on host tests and therefore cannot establish timing, accelerator
behavior, or hardware-specific numerics. Say so explicitly in the "not
established" section. The hot-path hazards `survey.sh` reports are the things
that pass every host test and fail on the target: an allocation, a lock, an
unthrottled log, or a `std::string` construction inside a synchronous cycle.
