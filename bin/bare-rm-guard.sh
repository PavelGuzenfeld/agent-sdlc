#!/usr/bin/env sh
set -eu

cmd=$(jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

without_heredocs=$(printf '%s\n' "$cmd" | awk '
    word != "" { line = $0; sub(/^\t+/, "", line); if (line == word) word = ""; next }
    { print }
    match($0, /<<-?[ \t]*[\047\042]?[A-Za-z_][A-Za-z_0-9]*/) {
        word = substr($0, RSTART, RLENGTH)
        gsub(/^<<-?[ \t]*[\047\042]?/, "", word)
    }
')

cmd_unquoted=$(printf '%s' "$without_heredocs" | tr '\n' ';' | sed -E -e 's/"[^"]*"/Q/g' -e "s/'[^']*'/Q/g")

bare=$(printf '%s' "$cmd_unquoted" | grep -Eo -- '(^|[;&|({`]|[;[:space:]](then|do|else))[[:space:]]*([A-Za-z_][A-Za-z_0-9]*=[^[:space:]]*[[:space:]]+)*(rm|cp|mv)([[:space:]]|$)' | head -n1 | grep -Eo -- '(rm|cp|mv)([[:space:]]|$)' | tail -n1 | grep -Eo -- '(rm|cp|mv)' || true)
[ -n "$bare" ] || exit 0

echo "bare-rm-guard: blocks bare $bare" >&2
echo "  the shell aliases $bare to $bare -i and waits on a prompt nobody answers" >&2
echo "  run it as: command $bare ..." >&2
exit 2
