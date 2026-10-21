#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
failures=0

fail() {
    echo "FAIL: $1" >&2
    failures=$((failures + 1))
}

work=$(mktemp -d)
marker='^# --- STAGES'

wizard_with() {
    sed "/$marker/q" "$dir/skills/wizard/template.sh" > "$work/wizard.sh"
    printf '%s\n' "$1" >> "$work/wizard.sh"
}

run_wizard() {
    status=0
    ENV_FILE="$work/.env" bash "$work/wizard.sh" > "$work/out" 2> "$work/err" < /dev/null || status=$?
}

wizard_with '
TOTAL_STAGES=1
stage "probe"
probe LISTING bash -c "set -o pipefail; ls /nonexistent-wizard-path | sort"
probe NAME printf "%s" hello
say "reached after probe: $NAME"
summary'
run_wizard
[ "$status" -eq 0 ] || fail "failed probe aborted the run (exit $status)"
grep -q 'reached after probe: hello' "$work/out" || fail "run did not continue past a failed probe"
grep -q 'ls /nonexistent-wizard-path' "$work/out" "$work/err" || fail "failed probe was not reported"

wizard_with '
TOTAL_STAGES=1
stage "expect"
expect "docker is installed" false
say "reached after failed expect"'
run_wizard
[ "$status" -ne 0 ] || fail "failed expect did not stop the run"
grep -q 'docker is installed' "$work/out" "$work/err" || fail "failed expect did not name the precondition"
if grep -q 'reached after failed expect' "$work/out"; then fail "run continued past a failed expect"; fi

wizard_with '
TOTAL_STAGES=1
stage "expect"
expect "shell works" true
say "reached after passing expect"'
run_wizard
[ "$status" -eq 0 ] || fail "passing expect stopped the run (exit $status)"
grep -q 'reached after passing expect' "$work/out" || fail "run did not continue past a passing expect"

rm -rf "$work"
[ "$failures" -eq 0 ] || exit 1
echo "ok"
