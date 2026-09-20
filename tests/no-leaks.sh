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

rfc1918_addr() {
    printf '%s.%s.%s.%s' "$1" "$2" "$3" "$4"
}

while IFS='|' read -r name content; do
    [ -n "$name" ] || continue
    expect_leak "$name" "$content"
done < "$fixtures/leaky.txt"

expect_leak "rfc1918 10/8" "host $(rfc1918_addr 10 7 13 21)"
expect_leak "rfc1918 192.168/16" "host $(rfc1918_addr 192 168 34 55)"
expect_leak "identity near ip octets" "contact user123@$(rfc1918_addr 10 21 34 7)"

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

repo=$(mktemp -d)
git -C "$repo" init -q
printf '\000\377\376%s' "$email_content" > "$repo/fixture.bin"
git -C "$repo" add fixture.bin
scan "$repo"
if [ "$code" -ne 0 ]; then
    echo "FAIL: binary file with leak-shaped content is skipped (expected exit 0, got $code): $stderr" >&2
    failures=$((failures + 1))
fi
if printf '%s' "$stderr" | grep -qi multibyte; then
    echo "FAIL: binary file scan printed an awk multibyte warning: $stderr" >&2
    failures=$((failures + 1))
fi
rm -rf "$repo"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
