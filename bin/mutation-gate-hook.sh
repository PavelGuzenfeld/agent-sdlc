#!/usr/bin/env sh
set -eu

payload=$(cat)
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty')
[ -n "$cwd" ] || cwd=$PWD

root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -f "$root/.mutation-gate.toml" ] || exit 0

if ! command -v mutation-gate >/dev/null 2>&1; then
    echo "mutation-gate-hook: $root/.mutation-gate.toml present but mutation-gate is not on PATH — pip install agent-sdlc" >&2
    exit 0
fi

printf '%s' "$payload" | mutation-gate --worktree
