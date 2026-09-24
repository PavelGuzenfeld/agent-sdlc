#!/usr/bin/env sh
# WezTerm toggle key. speaking -> stop; armed -> disarm; fresh -> speak; already spoken -> arm.
set -eu

BIN="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/bin"
DIR="${XDG_RUNTIME_DIR:-/tmp}/claude-say"
P="$DIR/p${1:?usage: say-key.sh <wezterm-pane-id>}"

tone() { cat "$BIN/say-tones/$1.raw" | aplay -q -r 24000 -f S16_LE -t raw -c 1 - 2>/dev/null || true; }

if [ -f "$P.pid" ] && kill -0 -"$(cat "$P.pid")" 2>/dev/null; then
    kill -TERM -"$(cat "$P.pid")" 2>/dev/null || true
    rm -f "$P.pid"
    tone stop
    exit 0
fi
rm -f "$P.pid"

if [ -f "$P.armed" ]; then
    rm -f "$P.armed"
    tone stop
    exit 0
fi

if [ ! -f "$P.txt" ]; then
    tone error
    exit 0
fi

if [ -f "$P.spoken" ]; then
    : > "$P.armed"
    tone arm
    exit 0
fi

setsid "$BIN/say-narrate.py" "$1" >/dev/null 2>&1 &
exit 0
