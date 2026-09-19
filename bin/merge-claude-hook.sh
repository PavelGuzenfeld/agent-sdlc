#!/usr/bin/env sh
set -eu

settings="$1"
hook_type="$2"
guard="$3"
filter="$4"
shift 4

if ! jq -e --arg t "$hook_type" --arg g "$guard" \
    '(.hooks[$t] // []) | tostring | contains($g)' "$settings" >/dev/null; then
    tmp=$(mktemp)
    jq "$@" "$filter" "$settings" > "$tmp"
    mv "$tmp" "$settings"
fi
