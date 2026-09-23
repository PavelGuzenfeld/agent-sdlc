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

add_lines() {
    path=$1
    count=$2
    mkdir -p "$consumer/$(dirname "$path")"
    i=0
    while [ "$i" -lt "$count" ]; do
        i=$((i + 1))
        echo "line_$i = $i" >> "$consumer/$path"
    done
    cgit add "$path"
}

git -C "$consumer" init -q -b main
printf 'test_paths = ["tests"]\n' > "$consumer/.mutation-gate.toml"
cgit add .mutation-gate.toml
cgit commit -q -m init

cgit checkout -q -b feature
add_lines src/a.py 20
cgit commit -q -m "first half"
add_lines src/b.py 21
cgit commit -q -m "second half"

set +e
range_out=$(cd "$consumer" && mutation-gate diff-discipline --range main..HEAD --branch feature 2>&1)
range_code=$?
set -e
[ "$range_code" -eq 1 ] || fail "--range should block 41 production lines on branch feature (got $range_code)" "$range_out"
printf '%s' "$range_out" | grep -qF "41" || fail "--range block did not report the count 41" "$range_out"
printf '%s' "$range_out" | grep -qF "40" || fail "--range block did not report the limit 40" "$range_out"
(cd "$consumer" && mutation-gate diff-discipline --range main..HEAD --branch 12-feature) \
    || fail "--range should pass the same 41 lines under branch 12-feature"

cat > "$consumer/.pre-commit-config.yaml" <<YAML
repos:
  - repo: $dir
    rev: $rev
    hooks:
      - id: diff-discipline
YAML
(cd "$consumer" && pre-commit install --hook-type commit-msg >/dev/null)

cgit checkout -q -b feature-hooked main
add_lines src/c.py 20
cgit commit -q -m "first half" || fail "20 production lines on branch feature-hooked should pass"
add_lines src/d.py 21
set +e
hook_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "second half" 2>&1)
hook_code=$?
set -e
[ "$hook_code" -ne 0 ] || fail "commit-msg hook should reject the commit that brings branch feature-hooked to 41 production lines"
printf '%s' "$hook_out" | grep -qF "41" || fail "hook rejection did not report the count 41" "$hook_out"
printf '%s' "$hook_out" | grep -qF "40" || fail "hook rejection did not report the limit 40" "$hook_out"
printf '%s' "$hook_out" | grep -qiF "ticket" || fail "hook rejection did not say how to pass" "$hook_out"

cgit branch -m 12-feature-hooked
cgit commit -q -m "second half" || fail "the same 41 lines should pass under branch 12-feature-hooked"

cgit checkout -q -b referenced main
add_lines src/e.py 41
cgit commit -q -m "big change for #12" || fail "41 production lines should pass with #12 in the commit message"

cgit checkout -q -b tests-only main
add_lines tests/test_e.py 41
cgit commit -q -m "tests" || fail "41 added lines under test_paths should pass"

cgit checkout -q -b forty main
add_lines src/f.py 20
cgit commit -q -m "first half"
add_lines src/g.py 20
cgit commit -q -m "second half" || fail "40 production lines should pass"

cgit checkout -q -b merge-sync main
add_lines src/h.py 20
cgit commit -q -m "own lines before syncing main"

cgit checkout -q main
add_lines src/on-main.py 41
cgit commit -q -m "main grows past the limit (#77)" || fail "41 lines landing on main itself should pass with #77 in the message"

cgit checkout -q merge-sync
merge_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel merge --no-edit main 2>&1) \
    || fail "merging main's 41 new lines into ticketless branch merge-sync (20 of its own) should pass" "$merge_out"

cgit checkout -q -b merge-blocked main
add_lines src/i.py 41
cgit commit -q -m "too many lines of its own"

cgit checkout -q main
add_lines src/on-main-2.py 41
cgit commit -q -m "main grows again (#77)" || fail "41 lines landing on main itself should pass with #77 in the message"

cgit checkout -q merge-blocked
set +e
merge_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel merge --no-edit main 2>&1)
merge_code=$?
set -e
[ "$merge_code" -ne 0 ] || fail "merging main into ticketless branch merge-blocked (41 of its own) should still block"
printf '%s' "$merge_out" | grep -qF "41 added production line(s)" \
    || fail "merge block did not report the branch's own count 41" "$merge_out"
if printf '%s' "$merge_out" | grep -qF "src/on-main-2.py"; then
    fail "merge block wrongly attributed main's own lines to the branch" "$merge_out"
fi

rm -rf "$consumer"
echo "all cases passed"
