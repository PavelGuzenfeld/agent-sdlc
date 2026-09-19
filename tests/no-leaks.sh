#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
script="$dir/scripts/no-leaks.sh"
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

expect_leak "email"                        "contact a@b.com for access"
expect_leak "ssh user@host"                "ssh deploy@build-box"
expect_leak "rfc1918 10/8"                 "host ***REMOVED***"
expect_leak "rfc1918 192.168/16"           "host ***REMOVED***"
expect_leak "rfc1918 172.16/12 low edge"   "host 172.16.0.1"
expect_leak "rfc1918 172.16/12 high edge"  "host 172.31.255.254"
expect_leak "home path"                    "see /home/someone/.claude/rules"
expect_leak "foreign ghcr namespace"       "image ghcr.io/other-org/tool:latest"

expect_clean "plain prose"                 "rotate the API token before the access token expires"
expect_clean "tilde path"                  "edit ~/.claude/settings.json"
expect_clean "public ip"                   "host 8.8.8.8"
expect_clean "172.15 is public"            "host 172.15.0.1"
expect_clean "172.32 is public"            "host 172.32.0.1"
expect_clean "personal ghcr namespace"     "image ghcr.io/PavelGuzenfeld/agent-sdlc:latest"
expect_clean "decorator is not a host"     "@pytest.mark.parametrize"
expect_clean "actions ref is not a host"   "uses: actions/checkout@v4"

repo=$(fixture_repo "clean line")
printf '%s\n' "a@b.com" > "$repo/untracked.txt"
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
