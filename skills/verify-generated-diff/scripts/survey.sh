#!/usr/bin/env bash
# survey.sh — cheap orientation on a change, before reading any of it.
#
# usage: survey.sh [baseline]        (default baseline: the 'reviewed' tag)
#
# Answers what reading a diff top-to-bottom answers badly: how big is this
# really, what is new, did it reinvent something, and does it contain the
# specific constructs that compile fine and are wrong.
#
# Depends only on git and grep. Every section prints matches or "none", and
# "none" is only printed after a search that actually ran — a tool that reports
# clean because its own search binary is missing is worse than no tool.

set -uo pipefail
BASE="${1:-reviewed}"

command -v git >/dev/null || { echo "git not found" >&2; exit 2; }
echo x | grep -oE 'x' >/dev/null 2>&1 || {
  echo "grep lacks -oE support; cannot search reliably" >&2; exit 2; }

git rev-parse --verify "$BASE" >/dev/null 2>&1 || {
  echo "no such baseline: $BASE" >&2
  echo "set one with:  git tag -f reviewed <sha>" >&2
  exit 2
}

# Generated and vendored paths are noise and would dominate every count.
EX=(
  ':(exclude)**/__pycache__/**'  ':(exclude)*.pyc'
  ':(exclude)**/node_modules/**' ':(exclude)**/build/**'
  ':(exclude)**/dist/**'         ':(exclude)**/target/**'
  ':(exclude)**/vendor/**'       ':(exclude)*.lock'
  ':(exclude)**/.venv/**'
)

hr() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
# Options must precede `--`; anything after it is a pathspec, not a flag.
d()  { git diff -M "$BASE" "$@" -- "${EX[@]}"; }

# Untracked files are invisible to git diff until intent-to-add. Generated
# changes are disproportionately new files, so this is not a detail: it is
# specifically the highest-design-content part of the change that would
# otherwise not appear in the review at all.
git add -A -N >/dev/null 2>&1 || true

hr "scope"
d --stat | tail -1
printf '  files changed : %s\n' "$(d --name-only | wc -l)"
printf '  files added   : %s\n' \
  "$(git diff --name-only --diff-filter=A -M "$BASE" -- "${EX[@]}" | wc -l)"
printf '  files renamed : %s\n' \
  "$(git diff --name-only --diff-filter=R -M "$BASE" -- "${EX[@]}" | wc -l)"

hr "new files (design decisions live here)"
out=$(git diff --stat --diff-filter=A -M "$BASE" -- "${EX[@]}" | sed '$d')
[ -n "$out" ] && echo "$out" || echo "  none"

hr "logic density (highest first — pick targets from the top)"
d --numstat | grep -vE '^-' | sort -k1 -nr | head -12 \
  | awk '{printf "  %6s +  %6s -   %s\n", $1, $2, $3}'

# Each scan prints added lines matching an ERE, with the file they came from.
scan() {
  local label="$1" ere="$2" out
  out=$(d -U0 | awk -v pat="$ere" '
    /^\+\+\+ b\// { file = substr($0, 7); next }
    /^\+/ && $0 ~ pat { printf "  %s: %s\n", file, substr($0, 2) }
  ')
  hr "$label"
  if [ -n "$out" ]; then echo "$out"; else echo "  none"; fi
}

scan "swallowed exceptions (never let these through)" \
  'catch[[:space:]]*[({]|except[[:space:]]|except:|unwrap_or|\.ok\(\)|recover\(\)'

scan "hot-path hazards (allocation / locking / IO in a synchronous cycle)" \
  'malloc|calloc|realloc|make_unique|make_shared|push_back|emplace_back|lock_guard|unique_lock|mutex|sleep|printf|cout|std::string|to_string|std::vector<|[^_[:alnum:]]new[[:space:]]'

scan "silent-convention hazards (compiles fine, wrong answer)" \
  'atan2|fmod|angle|wrap|normali[sz]|[^[:alnum:]]deg[^[:alnum:]]|[^[:alnum:]]rad[^[:alnum:]]|timestamp|[^[:alnum:]]dt[^[:alnum:]]|scale|quantiz|reinterpret_cast|memcpy|packed|<<|>>'

hr "reinvention candidates"
echo "  new function-like names that already appear elsewhere in the tree:"
d | grep -E '^\+' \
  | grep -oE '[a-zA-Z_][a-zA-Z0-9_]{3,}[[:space:]]*\(' \
  | sed 's/[[:space:]]*(//' \
  | sort -u | head -60 > /tmp/survey_syms || true
hits=0
while read -r sym; do
  [ -z "$sym" ] && continue
  n=$(git grep -l -- "$sym" 2>/dev/null | wc -l)
  if [ "${n:-0}" -gt 2 ]; then
    printf '    %-32s in %s files\n' "$sym" "$n"
    hits=$((hits+1))
  fi
done < /tmp/survey_syms
[ "$hits" -eq 0 ] && echo "    (nothing above threshold, or all new names are genuinely new)"
echo "  Appearing in many files is not proof of duplication. Check whether the"
echo "  semantics differ — same name with a different error convention is the"
echo "  common case, and it is worse than an outright duplicate."

hr "tests touched"
out=$(git diff --stat -M "$BASE" -- '*test*' '*spec*' "${EX[@]}" | tail -1)
[ -n "$out" ] && echo " $out" || echo "  none"
cat <<'EOF'
  These were probably written from the implementation, so they encode what the
  code does rather than what it should do. Do not read them as a specification.
  Attack them with Pass A before trusting a single green result.
EOF

hr "next"
cat <<'EOF'
  1. Pick 3-4 target functions from "logic density" plus domain verbs
     (predict / update / gate / validate / wrap / parse / pack).
  2. Write four mutants each — boundary, constant, branch, stub — into a TSV.
  3. scripts/run_mutants.sh mutants.tsv
EOF
