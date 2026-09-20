#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
script="$dir/scripts/no-leaks.sh"
fixtures="$dir/tests/fixtures"
failures=0

fixture_repo() {
    repo=$(mktemp -d)
    git -C "$repo" init -q
    printf '%s\n' "$1" > "$repo/fixture.txt"
    git -C "$repo" add fixture.txt
    printf '%s' "$repo"
}

scan() {
    set +e
    stderr=$(cd "$1" && sh "$script" 2>&1 >/dev/null)
    code=$?
    set -e
}

expect_leak() {
    name="$1"
    repo=$(fixture_repo "$2")
    scan "$repo"
    if [ "$code" -ne 1 ]; then
        echo "FAIL: $name (expected exit 1, got $code)" >&2
        failures=$((failures + 1))
    elif [ "$stderr" != "fixture.txt:1" ]; then
        echo "FAIL: $name (expected stderr 'fixture.txt:1', got '$stderr')" >&2
        failures=$((failures + 1))
    fi
    rm -rf "$repo"
}

expect_clean() {
    name="$1"
    repo=$(fixture_repo "$2")
    scan "$repo"
    if [ "$code" -ne 0 ]; then
        echo "FAIL: $name (expected exit 0, got $code): $stderr" >&2
        failures=$((failures + 1))
    fi
    rm -rf "$repo"
}

while IFS='|' read -r name content; do
    [ -n "$name" ] || continue
    expect_leak "$name" "$content"
done < "$fixtures/leaky.txt"

while IFS='|' read -r name content; do
    [ -n "$name" ] || continue
    expect_clean "$name" "$content"
done < "$fixtures/clean.txt"

email_content=$(awk -F'|' '$1 == "email" { print $2 }' "$fixtures/leaky.txt")
[ -n "$email_content" ] || { echo "FAIL: leaky.txt has no 'email' row" >&2; exit 1; }
repo=$(fixture_repo "clean line")
printf '%s\n' "$email_content" > "$repo/untracked.txt"
scan "$repo"
if [ "$code" -ne 0 ]; then
    echo "FAIL: untracked file is ignored (expected exit 0, got $code): $stderr" >&2
    failures=$((failures + 1))
fi
rm -rf "$repo"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
