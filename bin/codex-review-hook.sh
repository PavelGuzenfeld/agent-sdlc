#!/usr/bin/env sh
set -eu

payload=$(cat)
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty')
[ -n "$cwd" ] || cwd=$PWD

root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ "$(git -C "$root" config --bool agent-sdlc.codexReview 2>/dev/null)" = true ] || exit 0

if ! command -v codex >/dev/null 2>&1; then
    echo "codex-review-hook: agent-sdlc.codexReview is set in $root but codex is not on PATH" >&2
    exit 0
fi

head=$(git -C "$root" rev-parse --verify -q HEAD) || exit 0
state=$(git -C "$root" rev-parse --path-format=absolute --git-path agent-sdlc-codex-review)
reviewed_head=""
reviewed_tree=""
accepted_tree=""
[ -f "$state" ] && read -r reviewed_head reviewed_tree accepted_tree < "$state"

work=$(mktemp -d)
cleanup() {
    git -C "$root" worktree remove --force "$work/baseline" >/dev/null 2>&1 || true
    git -C "$root" worktree remove --force "$work/candidate" >/dev/null 2>&1 || true
    rm -rf "$work"
    git -C "$root" worktree prune
}
trap cleanup EXIT
trap 'exit 1' INT TERM

GIT_INDEX_FILE="$work/index" git -C "$root" read-tree HEAD
GIT_INDEX_FILE="$work/index" git -C "$root" add -A
tree=$(GIT_INDEX_FILE="$work/index" git -C "$root" write-tree)

[ "$head $tree" = "$reviewed_head $reviewed_tree" ] && exit 0

record_review() {
    printf '%s %s %s\n' "$head" "$tree" "$1" > "$state"
}

head_tree=$(git -C "$root" rev-parse "HEAD^{tree}")
baseline=$head_tree
if [ -n "$accepted_tree" ] && git -C "$root" cat-file -e "$accepted_tree^{tree}" 2>/dev/null \
    && git -C "$root" merge-base --is-ancestor "$reviewed_head" "$head" 2>/dev/null; then
    baseline=$accepted_tree
elif [ -z "$reviewed_head" ] && [ "$tree" = "$head_tree" ]; then
    baseline=$(git -C "$root" rev-parse --verify -q "HEAD~1^{tree}") || baseline=$head_tree
fi

if [ "$baseline" = "$tree" ]; then
    record_review "$tree"
    exit 0
fi

git -C "$root" worktree add -q --detach "$work/baseline" "$head"
git -C "$work/baseline" read-tree -u --reset "$baseline"
git -C "$root" worktree add -q --detach "$work/candidate" "$head"
git -C "$work/candidate" read-tree -u --reset "$tree"

prompt="$(cat "$(dirname "$0")/codex-review-prompt.md")

baseline: $work/baseline (tree $baseline)
candidate: $work/candidate (tree $tree)

Previous assistant response:
$(printf '%s' "$payload" | jq -r '.last_assistant_message // empty')"

if ! timeout 840 codex exec --ephemeral --skip-git-repo-check -s danger-full-access \
    -C "$work" -o "$work/verdict" "$prompt" >/dev/null 2>"$work/log"; then
    echo "codex-review-hook: codex exec failed, the change was not reviewed" >&2
    head -n 20 "$work/log" >&2
    exit 0
fi

verdict=$(cat "$work/verdict" 2>/dev/null || true)
debt=$(printf '%s\n' "$verdict" | grep '^DEBT:' || true)

block() {
    jq -n --arg reason "$1" '{decision: "block", reason: $reason}'
}

case "$(printf '%s\n' "$verdict" | head -n 1)" in
    BLOCK:*)
        record_review "$baseline"
        block "Codex reproduced a regression in this turn's change (fails on the change, passes on the last accepted tree). Fix it before stopping.

$verdict"
        ;;
    ALLOW:*)
        record_review "$tree"
        [ -z "$debt" ] || block "Codex found issues that fail on the last accepted tree too, so this turn did not introduce them. File each as a follow-up issue (tickets.md) in this repo's own tracker, never in an upstream project's.

$debt"
        ;;
    *)
        echo "codex-review-hook: codex returned no ALLOW or BLOCK line, the change was not reviewed" >&2
        ;;
esac
