#!/usr/bin/env sh
# Stop hook. Writes the pane's narration pointer; starts narration only when armed.
set -eu

[ -n "${WEZTERM_PANE:-}" ] || exit 0

BIN="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/bin"
DIR="${XDG_RUNTIME_DIR:-/tmp}/claude-say"
mkdir -p "$DIR"
P="$DIR/p$WEZTERM_PANE"

TRANSCRIPT=$(jq -r '.transcript_path // empty')
[ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ] || exit 0

PAYLOAD=$(tail -n 400 "$TRANSCRIPT" | jq -s -f "$BIN/say-extract.jq" 2>/dev/null) || exit 0
[ -n "$PAYLOAD" ] || exit 0

ANSWER=$(printf '%s' "$PAYLOAD" | jq -r .answer)
[ "${#ANSWER}" -ge 80 ] || exit 0

HASH=$(printf '%s' "$ANSWER" | md5sum | cut -d' ' -f1)
[ "$HASH" = "$(cat "$P.hash" 2>/dev/null || true)" ] && exit 0

printf '%s' "$PAYLOAD" > "$P.txt"
printf '%s' "$HASH" > "$P.hash"
rm -f "$P.spoken"

if [ -f "$P.armed" ]; then
    rm -f "$P.armed"
    setsid "$BIN/say-narrate.py" "$WEZTERM_PANE" >/dev/null 2>&1 &
fi
exit 0
