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

text_file_head_probe_size=8000
padding_past_head_probe=$(awk -v n="$text_file_head_probe_size" 'BEGIN { for (i = 0; i < n + 500; i++) printf "a" }')
repo=$(mktemp -d)
git -C "$repo" init -q
printf '%s\000%s' "$padding_past_head_probe" "$email_content" > "$repo/fixture.bin"
git -C "$repo" add fixture.bin
scan "$repo"
if [ "$code" -ne 0 ]; then
    echo "FAIL: binary file with a NUL past the text-file head probe is skipped (expected exit 0, got $code): $stderr" >&2
    failures=$((failures + 1))
fi
if printf '%s' "$stderr" | grep -qi 'binary file'; then
    echo "FAIL: binary file scan printed a grep binary-file notice: $stderr" >&2
    failures=$((failures + 1))
fi
rm -rf "$repo"

adjacent_identity_user='alice'
adjacent_identity_host='internal.example'
adjacent_identity="${adjacent_identity_user}@${adjacent_identity_host}"

carveout_sample() {
    case "$1" in
        public_git_ssh_clone_url) printf '%s' 'git@github.com:' ;;
        npm_version_specifier) printf '%s' 'pkg@1.2.3 ' ;;
        *)
            echo "FAIL: no boundary sample declared for carve-out: $1" >&2
            failures=$((failures + 1))
            printf '%s' ''
            ;;
    esac
}

carveout_expected_output() {
    case "$1" in
        public_git_ssh_clone_url) printf '%s%s' 'public-git-ssh-clone-url' "$adjacent_identity" ;;
        npm_version_specifier) printf '%s %s' 'npm-package-version' "$adjacent_identity" ;;
        *)
            echo "FAIL: no expected boundary output declared for carve-out: $1" >&2
            failures=$((failures + 1))
            printf '%s' ''
            ;;
    esac
}

eval "$(grep -E '^(identity_carve_outs|[a-z_]+_(pattern|replacement))=' "$script")"

for carve_out in $identity_carve_outs; do
    eval "pattern=\$${carve_out}_pattern"
    eval "replacement=\$${carve_out}_replacement"
    sample=$(carveout_sample "$carve_out")
    boundary_output=$(printf '%s%s' "$sample" "$adjacent_identity" | sed -E "s#$pattern#$replacement#g")
    expected_output=$(carveout_expected_output "$carve_out")
    if [ "$boundary_output" != "$expected_output" ]; then
        echo "FAIL: carve-out boundary ($carve_out): expected '$expected_output', got '$boundary_output'" >&2
        failures=$((failures + 1))
    fi
done

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
