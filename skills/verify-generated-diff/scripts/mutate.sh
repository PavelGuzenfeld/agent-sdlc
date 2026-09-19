#!/usr/bin/env bash
# mutate.sh — apply one mutant, build, test, classify, always revert.
#
# usage: mutate.sh <file> <literal-old> <literal-new> [test-filter]
#
# env:
#   BUILD_CMD     default: cmake --build "$BUILD_DIR" -j$(nproc) [--target $BUILD_TARGET]
#   TEST_CMD      default: ctest --test-dir "$BUILD_DIR" -R "<filter>"
#                 use {filter} as a placeholder for the test filter
#   BUILD_DIR     default: build
#   BUILD_TARGET  optional: build only this target (much faster)
#
# exit: 0 = classified (see stdout), 2 = refused, 3 = bad mutant spec
#
# The substitution must match exactly once. That is deliberate: an ambiguous
# mutant tells you nothing, because you don't know which site was hit.

set -uo pipefail

if [ "$#" -lt 3 ]; then
  sed -n '2,18p' "$0" >&2
  exit 2
fi

FILE="$1"; OLD="$2"; NEW="$3"; FILTER="${4:-.}"
BUILD_DIR="${BUILD_DIR:-build}"
BUILD_TARGET="${BUILD_TARGET:-}"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "REFUSED: not inside a git repository (revert would be unsafe)" >&2
  exit 2
fi

if [ ! -f "$FILE" ]; then
  echo "REFUSED: no such file: $FILE" >&2
  exit 2
fi

if ! git ls-files --error-unmatch "$FILE" >/dev/null 2>&1; then
  echo "REFUSED: $FILE is untracked — 'git checkout --' cannot restore it." >&2
  echo "         Commit it first (git add -A && git commit) so revert is safe." >&2
  exit 2
fi

if ! git diff --quiet -- "$FILE" || ! git diff --cached --quiet -- "$FILE"; then
  echo "REFUSED: $FILE has uncommitted changes; revert would destroy them." >&2
  echo "         Commit or stash, then retry." >&2
  exit 2
fi

build_of() {
  if [ -n "${BUILD_CMD:-}" ]; then echo "$BUILD_CMD"; return; fi
  local c="cmake --build $BUILD_DIR -j$(nproc 2>/dev/null || echo 4)"
  [ -n "$BUILD_TARGET" ] && c="$c --target $BUILD_TARGET"
  echo "$c"
}
test_of() {
  if [ -n "${TEST_CMD:-}" ]; then echo "${TEST_CMD//\{filter\}/$1}"; return; fi
  echo "ctest --test-dir $BUILD_DIR -R $1"
}

# Pre-flight: the unmutated tree must build and pass for this filter.
#
# Without this check a broken test command — missing runner, wrong filter
# matching zero tests, unbuilt target — makes every mutant report KILLED, and
# KILLED reads as good news. A harness whose failure mode is false reassurance
# is worse than no harness. Set MUTATE_BASELINE_OK=1 to skip when the caller
# has already verified it (run_mutants.sh does).
if [ "${MUTATE_BASELINE_OK:-0}" != "1" ]; then
  if ! eval "$(build_of)" >/tmp/mutate_baseline.log 2>&1; then
    echo "REFUSED: baseline does not build. See /tmp/mutate_baseline.log" >&2
    exit 2
  fi
  if ! eval "$(test_of "$FILTER")" >>/tmp/mutate_baseline.log 2>&1; then
    echo "REFUSED: baseline tests fail or the filter '$FILTER' matches nothing." >&2
    echo "         Every mutant would report KILLED for the wrong reason." >&2
    echo "         See /tmp/mutate_baseline.log" >&2
    exit 2
  fi
fi

# Restore on every exit path, including SIGINT/SIGTERM.
restore() { git checkout -- "$FILE" 2>/dev/null || true; }
trap restore EXIT INT TERM

python3 - "$FILE" "$OLD" "$NEW" <<'PY' || exit 3
import sys, pathlib
path, old, new = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
text = path.read_text()
n = text.count(old)
if n != 1:
    sys.exit(f"BAD MUTANT: pattern occurs {n} times in {path}, need exactly 1")
path.write_text(text.replace(old, new, 1))
PY

# --- build ---
if ! eval "$(build_of)" >/tmp/mutate_build.log 2>&1; then
  printf 'BUILD-FAIL  %-30s %s => %s\n' "$(basename "$FILE")" "$OLD" "$NEW"
  echo '            (compiler caught it — no signal about the tests; rewrite the mutant)'
  exit 0
fi

# --- test ---
if eval "$(test_of "$FILTER")" >/tmp/mutate_test.log 2>&1; then
  printf 'SURVIVED    %-30s %s => %s\n' "$(basename "$FILE")" "$OLD" "$NEW"
  echo '            (tests green with wrong logic — this is the finding)'
else
  printf 'KILLED      %-30s %s => %s\n' "$(basename "$FILE")" "$OLD" "$NEW"
fi
