#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

dir="$(cd "$(dirname "$0")/.." && pwd)"
script="$dir/tests/no-leaks.sh"
failures=0

work=$(mktemp -d)
main="$work/main"
wt="$work/wt"
mkdir -p "$main"
git -C "$main" init -q
git -C "$main" -c user.email=sentinel -c user.name=sentinel commit --allow-empty -q -m sentinel
git -C "$main" worktree add -q "$wt" -b sentinel-wt >/dev/null 2>&1
gitdir=$(sed 's/^gitdir: //' "$wt/.git")

bare_before=$(git -C "$main" config core.bare)
head_before=$(git -C "$main" rev-parse HEAD)
main_status_before=$(git -C "$main" status --porcelain)
wt_status_before=$(git -C "$wt" status --porcelain)

GIT_DIR="$gitdir" GIT_INDEX_FILE="$gitdir/index" sh "$script" >/dev/null 2>&1 || true

bare_after=$(git -C "$main" config core.bare 2>&1) || true
head_after=$(git -C "$main" rev-parse HEAD 2>&1) || true
main_status_after=$(git -C "$main" status --porcelain 2>&1) || true
wt_status_after=$(git -C "$wt" status --porcelain 2>&1) || true

if [ "$bare_before" != "$bare_after" ]; then
    echo "FAIL: no-leaks.sh flipped core.bare on the sentinel (was $bare_before, now $bare_after)" >&2
    failures=$((failures + 1))
fi
if [ "$head_before" != "$head_after" ]; then
    echo "FAIL: no-leaks.sh moved the sentinel's HEAD (was $head_before, now $head_after)" >&2
    failures=$((failures + 1))
fi
if [ "$main_status_before" != "$main_status_after" ]; then
    echo "FAIL: no-leaks.sh dirtied the sentinel's main worktree (status now: $main_status_after)" >&2
    failures=$((failures + 1))
fi
if [ "$wt_status_before" != "$wt_status_after" ]; then
    echo "FAIL: no-leaks.sh dirtied the sentinel's linked worktree (status now: $wt_status_after)" >&2
    failures=$((failures + 1))
fi

git -C "$main" worktree remove --force "$wt" >/dev/null 2>&1 || true
rm -rf "$work"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
