#!/usr/bin/env bash
# run_mutants.sh — run a whole mutant set and summarise.
#
# usage: run_mutants.sh [mutants.tsv]
#
# TSV format, tab-separated, '#' comments and blank lines ignored:
#   file<TAB>literal-old<TAB>literal-new<TAB>test-filter
#
# Multi-line mutants: write \n in the old/new fields; it is expanded to a real
# newline before substitution. Leading spaces are significant — keep them.
#
# Deletion mutants (Pass B): write the literal token <DELETE> as the
# replacement. Do NOT leave the field empty — an empty field is indistinguishable
# from a missing one to most TSV readers, and getting it wrong yields a
# confident, wrong classification.
#
# test-filter is optional; it defaults to '.' (all tests).
#
# Keep this file in the repo. It is a regression check on the test suite, which
# nothing else in the toolchain provides.

set -uo pipefail

TSV="${1:-mutants.tsv}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ -f "$TSV" ] || { echo "no such file: $TSV" >&2; exit 2; }

# Baseline must be green or every result below is noise.
echo "== baseline"
if [ -n "${TEST_CMD:-}" ]; then
  base_cmd="${TEST_CMD//\{filter\}/.}"
else
  base_cmd="ctest --test-dir ${BUILD_DIR:-build} --output-on-failure"
fi
if ! eval "$base_cmd" >/tmp/mutate_baseline.log 2>&1; then
  echo "ABORT: baseline suite is RED. Fix that first — mutant results would be" >&2
  echo "       meaningless. See /tmp/mutate_baseline.log" >&2
  exit 2
fi
echo "   green"
echo
# Baseline verified here; per-mutant re-checks would double the cost.
export MUTATE_BASELINE_OK=1

killed=0; survived=0; buildfail=0; bad=0
declare -a survivors=()

echo "== mutants"
# Parse with python rather than `read -r ... ` with IFS=$'\t'. Tab is IFS
# whitespace, so bash collapses runs of tabs into one delimiter — an empty
# replacement field silently shifts every later column and produces a
# confidently wrong classification. Deletion mutants therefore use the explicit
# sentinel <DELETE> rather than an empty field.
# Records are NUL-separated because field values legitimately contain newlines
# (multi-line mutants), and both `mapfile -t` and `read` split on newlines.
mapfile -d '' ROWS < <(python3 - "$TSV" <<'PY'
import sys, pathlib
for lineno, raw in enumerate(pathlib.Path(sys.argv[1]).read_text().splitlines(), 1):
    if not raw.strip() or raw.lstrip().startswith("#"):
        continue
    parts = raw.split("\t")
    if len(parts) < 3:
        sys.stderr.write(f"line {lineno}: need at least 3 tab-separated fields\n")
        continue
    f, old, new = parts[0], parts[1], parts[2]
    filt = parts[3] if len(parts) > 3 and parts[3] else "."
    new = "" if new.strip() == "<DELETE>" else new
    # \n in the TSV means a real newline in the source.
    old = old.replace("\\n", "\n")
    new = new.replace("\\n", "\n")
    sys.stdout.write("\x1f".join((f, old, new, filt)) + "\0")
PY
)

for row in "${ROWS[@]}"; do
  [ -z "$row" ] && continue
  # Parameter expansion, not `read`: read stops at the first newline.
  f="${row%%$'\x1f'*}";      rest="${row#*$'\x1f'}"
  old_x="${rest%%$'\x1f'*}"; rest="${rest#*$'\x1f'}"
  new_x="${rest%%$'\x1f'*}"; filter="${rest#*$'\x1f'}"

  out=$("$HERE/mutate.sh" "$f" "$old_x" "$new_x" "$filter" 2>&1)
  echo "$out"

  case "$out" in
    *KILLED*)     killed=$((killed+1)) ;;
    *SURVIVED*)   survived=$((survived+1))
                  o1="${old_x%%$'\n'*}"; n1="${new_x%%$'\n'*}"
                  [ "$o1" != "$old_x" ] && o1="$o1…"
                  [ "$n1" != "$new_x" ] && n1="$n1…"
                  survivors+=("$f: $o1 => ${n1:-<deleted>}") ;;
    *BUILD-FAIL*) buildfail=$((buildfail+1)) ;;
    *)            bad=$((bad+1)) ;;
  esac
done

echo
echo "== summary"
printf '  killed      %3d\n' "$killed"
printf '  SURVIVED    %3d\n' "$survived"
printf '  build-fail  %3d  (no signal — rewrite these mutants type-correct)\n' "$buildfail"
printf '  refused     %3d\n' "$bad"

if [ "$survived" -gt 0 ]; then
  echo
  echo "  Survivors — for each, write the test that kills it, from the spec"
  echo "  (not from the code), then re-run to confirm KILLED:"
  for s in "${survivors[@]}"; do echo "    - $s"; done
fi

# Non-zero when there is something to act on, so this can gate a hook.
[ "$survived" -eq 0 ]
