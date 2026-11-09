#!/usr/bin/env sh
set -eu

cmd=$(jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

cmd_unquoted=$(printf '%s' "$cmd" | tr '\n' ';' | sed -E -e 's/"[^"]*"/Q/g' -e "s/'[^']*'/Q/g")

bare=$(printf '%s' "$cmd_unquoted" | grep -Eo -- '(^|[;&|({]|[;[:space:]](then|do|else))[[:space:]]*(rm|cp|mv)([[:space:]]|$)' | head -n1 | grep -Eo -- '(rm|cp|mv)' | head -n1 || true)
[ -n "$bare" ] || exit 0

echo "bare-rm-guard: blocks bare $bare" >&2
echo "  the shell aliases $bare to $bare -i and waits on a prompt nobody answers" >&2
echo "  run it as: command $bare ..." >&2
exit 2
