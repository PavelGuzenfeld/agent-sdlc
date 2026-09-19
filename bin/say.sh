#!/usr/bin/env sh
# Speaks a UTF-8 text file through Kokoro. Installed by ./install.sh --deps=say
set -eu

PYTHON="$HOME/.local/share/kokoro-venv/bin/python"
KSAY="$HOME/.claude/bin/ksay.py"
SAMPLE_RATE=24000

usage() {
    echo "usage: sh ~/.claude/bin/say.sh <text-file> [voice] [speed]  # default af_heart 1.0, higher speed is faster" >&2
    exit 2
}

[ $# -ge 1 ] && [ $# -le 3 ] || usage
[ -f "$1" ] || { echo "say.sh: no such file: $1" >&2; exit 2; }

VOICE="${2:-af_heart}"
SPEED="${3:-1.0}"

case "$VOICE" in
    ''|*[!a-z0-9_]*) echo "say.sh: not a voice name: $VOICE" >&2; exit 2 ;;
esac
case "$SPEED" in
    ''|*[!0-9.]*|*.*.*) echo "say.sh: speed must be a number: $SPEED" >&2; exit 2 ;;
esac

if [ ! -x "$PYTHON" ]; then
    echo "say.sh: kokoro missing — run: ./install.sh --deps=say" >&2
    exit 1
fi

"$PYTHON" "$KSAY" "$1" "$VOICE" "$SPEED" \
    | aplay -q -r "$SAMPLE_RATE" -f S16_LE -t raw -c 1 -
