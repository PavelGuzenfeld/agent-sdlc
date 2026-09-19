#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_script="$dir/bin/git-guardrail.sh"
home_script="${GIT_GUARDRAIL_HOME_SCRIPT:-$HOME/.claude/bin/git-guardrail.sh}"
failures=0

run() {
    payload=$(printf '%s' "$2" | jq -Rs '{tool_input: {command: .}}')
    printf '%s' "$payload" | "$1"
}

expect_block() {
    target="$1"; label="$2"; name="$3"
    set +e
    stderr=$(run "$target" "$4" 2>&1 >/dev/null)
    code=$?
    set -e
    if [ "$code" -ne 2 ]; then
        echo "FAIL: [$label] $name (expected exit 2, got $code)" >&2
        failures=$((failures + 1))
    elif [ -z "$stderr" ]; then
        echo "FAIL: [$label] $name (exit 2 but empty stderr)" >&2
        failures=$((failures + 1))
    fi
}

expect_allow() {
    target="$1"; label="$2"; name="$3"
    set +e
    stderr=$(run "$target" "$4" 2>&1 >/dev/null)
    code=$?
    set -e
    if [ "$code" -ne 0 ]; then
        echo "FAIL: [$label] $name (expected exit 0, got $code): $stderr" >&2
        failures=$((failures + 1))
    fi
}

run_case_table() {
    target="$1"; label="$2"

    expect_block "$target" "$label" "push --force"        "git push --force origin main"
    expect_block "$target" "$label" "push -f"             "git push -f origin main"
    expect_block "$target" "$label" "push + refspec"      "git push origin +main"
    expect_block "$target" "$label" "reset --hard"        "git reset --hard"
    expect_block "$target" "$label" "clean -fd"           "git clean -fd"
    expect_block "$target" "$label" "checkout ."          "git checkout ."
    expect_block "$target" "$label" "checkout -- ."       "git checkout -- ."
    expect_block "$target" "$label" "restore ."           "git restore ."
    expect_block "$target" "$label" "add -A"              "git add -A"
    expect_block "$target" "$label" "add ."               "git add ."
    expect_block "$target" "$label" "add --all"           "git add --all"
    expect_block "$target" "$label" "branch -D"           "git branch -D old-branch"
    expect_block "$target" "$label" "push --force after quoted ;"   'git push origin "feature;branch" --force'
    expect_block "$target" "$label" "push --force after quoted &"   'git push origin "feature&branch" --force'
    expect_block "$target" "$label" "push --force after quoted |"   'git push origin "feature|branch" --force'

    expect_allow "$target" "$label" "plain push"                 "git push"
    expect_allow "$target" "$label" "push --force-with-lease"    "git push --force-with-lease origin main"
}

run_case_table "$repo_script" "repo"

if [ -f "$home_script" ]; then
    run_case_table "$home_script" "installed"
else
    echo "installed $home_script not found — skipping the live-copy pass" >&2
fi

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
