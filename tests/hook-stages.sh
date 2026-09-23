#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

dir="$(cd "$(dirname "$0")/.." && pwd)"
rev=$(git -C "$dir" rev-parse HEAD)
consumer=$(mktemp -d)

fail() {
    echo "FAIL: $1" >&2
    shift
    [ $# -gt 0 ] && printf '%s\n' "$@" >&2
    rm -rf "$consumer"
    exit 1
}

cgit() {
    git -C "$consumer" -c user.email=sentinel -c user.name=sentinel "$@"
}

git -C "$consumer" init -q -b main
: > "$consumer/.mutation-gate.toml"
cat > "$consumer/.pre-commit-config.yaml" <<YAML
default_install_hook_types: [pre-commit, commit-msg]
repos:
  - repo: $dir
    rev: $rev
    hooks:
      - id: rules-check
      - id: mutation-gate
      - id: no-new-docs
      - id: commit-msg
      - id: diff-discipline
      - id: no-leaks
YAML
cgit add .mutation-gate.toml .pre-commit-config.yaml
cgit commit -q -m init

(cd "$consumer" && mutation-gate rules sync)
git -C "$consumer" add .claude/rules AGENTS.md
cgit commit -q -m "sync rules"

(cd "$consumer" && pre-commit install >/dev/null)

echo "line" > "$consumer/a.txt"
cgit add a.txt
set +e
out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add a.txt" 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] || fail "the commit should pass with both hook types installed and no default_stages" "$out"

check_once() {
    needle=$1
    count=$(printf '%s\n' "$out" | grep -cF "$needle")
    [ "$count" -eq 1 ] || fail "expected '$needle' to run exactly once per commit, ran $count times" "$out"
}

check_once "rules check (.claude/rules drift)"
check_once "mutation gate (diff-scoped)"
check_once "no new docs (newly added .md files must be allowlisted)"
check_once "commit message check (voice.md banned words, attribution, sign-off)"
check_once "diff discipline (branch line limit without a ticket reference)"
check_once "no-leaks (identity/RFC1918/home-path scan plus optional banned_names_file)"

rm -rf "$consumer"
echo "all cases passed"
