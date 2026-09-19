#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
out="$dir/AGENTS.md"

: > "$out"

first=1
for file in $(find "$dir/rules" -maxdepth 1 -name '*.md' | LC_ALL=C sort); do
    name=$(basename "$file" .md)
    if [ "$first" -eq 0 ]; then
        printf '\n' >> "$out"
    fi
    first=0
    printf '## %s\n\n' "$name" >> "$out"
    cat "$file" >> "$out"
done
