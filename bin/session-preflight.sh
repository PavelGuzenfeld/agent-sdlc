#!/usr/bin/env sh
set -eu

threshold=85
warnings=""

add() {
    warnings="${warnings:+$warnings; }$1"
}

for target in "${TMPDIR:-/tmp}" "$HOME"; do
    usage=$(df -P "$target" 2>/dev/null | awk 'NR==2 {gsub(/%/, "", $5); print $5, $6}') || continue
    pct=${usage%% *}
    mount=${usage#* }
    case "$pct" in ''|*[!0-9]*) continue ;; esac
    [ "$pct" -gt "$threshold" ] || continue
    case "$warnings" in *"$mount $pct%"*) continue ;; esac
    add "$mount $pct% used"
done

worktrees=$(git worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p' || true)
while IFS= read -r wt; do
    [ -n "$wt" ] || continue
    found=$(find "$wt" -user root -print -quit 2>/dev/null || true)
    [ -z "$found" ] || { add "root-owned file in worktree: $found"; break; }
done <<WORKTREES
$worktrees
WORKTREES

[ -z "$warnings" ] || printf 'preflight: %s\n' "$warnings"
