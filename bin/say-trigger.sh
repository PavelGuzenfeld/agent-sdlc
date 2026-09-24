#!/usr/bin/env sh
# /say entrypoint. Always speaks the pane's latest answer, preempting anything playing.
set -eu

BIN="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/bin"
DIR="${XDG_RUNTIME_DIR:-/tmp}/claude-say"
PANE="${WEZTERM_PANE:?not running under WezTerm}"
P="$DIR/p$PANE"

[ -f "$P.txt" ] || { echo "say: nothing to speak yet for pane $PANE" >&2; exit 1; }

[ -f "$P.pid" ] && kill -TERM -"$(cat "$P.pid")" 2>/dev/null || true
rm -f "$P.pid" "$P.armed"

setsid "$BIN/say-narrate.py" "$PANE" "${1:-af_heart}" "${2:-1.0}" "${3:-}" >/dev/null 2>&1 &
exit 0
