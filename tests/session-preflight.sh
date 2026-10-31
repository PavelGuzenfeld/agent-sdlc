#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
script="$dir/bin/session-preflight.sh"
stubs=$(mktemp -d)
trap 'rm -rf "$stubs"' EXIT
failures=0

cat > "$stubs/df" <<'STUB'
#!/bin/sh
printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\n'
printf '/dev/stub 100 %s 0 %s%% /mnt/stub\n' "$STUB_PCT" "$STUB_PCT"
STUB
cat > "$stubs/find" <<'STUB'
#!/bin/sh
[ -z "${STUB_ROOT_FILE:-}" ] || printf '%s\n' "$STUB_ROOT_FILE"
STUB
chmod +x "$stubs/df" "$stubs/find"

run_preflight() {
    PATH="$stubs:$PATH" STUB_PCT="$1" STUB_ROOT_FILE="${2:-}" sh "$script" < /dev/null
}

expect_silent() {
    out=$(run_preflight "$1" "${2:-}")
    [ -z "$out" ] || { echo "FAIL: $3 (expected no output): $out" >&2; failures=$((failures + 1)); }
}

expect_one_line() {
    out=$(run_preflight "$1" "${2:-}")
    lines=$(printf '%s\n' "$out" | wc -l)
    [ -n "$out" ] && [ "$lines" -eq 1 ] || { echo "FAIL: $4 (expected one line): $out" >&2; failures=$((failures + 1)); return; }
    printf '%s' "$out" | grep -Fq -- "$3" || { echo "FAIL: $4 (missing '$3'): $out" >&2; failures=$((failures + 1)); }
}

expect_silent 50 "" "healthy filesystem prints nothing"
expect_silent 85 "" "exactly 85 percent prints nothing"
expect_one_line 86 "" "/mnt/stub 86%" "86 percent names mount and usage"
expect_one_line 100 "" "/mnt/stub 100%" "100 percent names mount and usage"
expect_one_line 50 "/wt/leftover" "/wt/leftover" "root-owned worktree file is named"
out=$(run_preflight 90 "")
occurrences=$(printf '%s' "$out" | grep -o '/mnt/stub 90%' | wc -l)
[ "$occurrences" -eq 1 ] || { echo "FAIL: shared mount named $occurrences times, expected once: $out" >&2; failures=$((failures + 1)); }

set +e
out=$(run_preflight - "" 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] && [ -z "$out" ] || { echo "FAIL: non-numeric usage must be silent on stdout and stderr (code $code, output '$out')" >&2; failures=$((failures + 1)); }

[ "$failures" -eq 0 ] || exit 1
echo "session-preflight: ok"
