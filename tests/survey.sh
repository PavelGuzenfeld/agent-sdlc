#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

dir="$(cd "$(dirname "$0")/.." && pwd)"
script="$dir/skills/verify-generated-diff/scripts/survey.sh"
failures=0

fail() {
    echo "FAIL: $1" >&2
    shift
    [ $# -gt 0 ] && printf '%s\n' "$@" >&2
    failures=$((failures + 1))
}

repo=$(mktemp -d)
git -C "$repo" init -q -b main
git -C "$repo" -c user.email=s -c user.name=s commit -q --allow-empty -m init
git -C "$repo" tag reviewed

printf 'void *p = malloc(4);\n' > "$repo/new.c"

out=$(cd "$repo" && bash "$script")

status="$(git -C "$repo" status --porcelain)"
[ "$status" = "?? new.c" ] || fail "survey.sh must leave the real index alone" "got status: $status"

cached="$(git -C "$repo" diff --cached --name-only)"
[ -z "$cached" ] || fail "survey.sh must stage nothing in the real index" "got: $cached"

printf '%s\n' "$out" | grep -qE 'files added +: 1' \
    || fail "survey.sh did not count the untracked file as added"

printf '%s\n' "$out" | grep -q 'new.c: void \*p = malloc(4);' \
    || fail "survey.sh dropped the untracked file's content from the hot-path scan"

rm -rf "$repo"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
