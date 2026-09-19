#!/usr/bin/env sh
set -eu

identity='[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*'
octet='[0-9]{1,3}'
rfc1918="(^|[^0-9.])(10\\.$octet|192\\.168|172\\.(1[6-9]|2[0-9]|3[01]))\\.$octet\\.$octet([^0-9]|\$)"
home_path='/home/[A-Za-z0-9._-]+/'

files=$(git ls-files)

hits=$(printf '%s\n' "$files" | while IFS= read -r file; do
    [ -f "$file" ] || continue
    grep -nIE -e "$identity" -e "$rfc1918" -e "$home_path" -- "$file" | cut -d: -f1 | sed "s|^|$file:|"
    awk -v file="$file" '{
        line = tolower($0)
        gsub(/ghcr\.io\/pavelguzenfeld\//, "", line)
        if (line ~ /ghcr\.io\/[a-z0-9._-]+\//) print file ":" NR
    }' "$file"
done | sort -t: -k1,1 -k2,2n -u)

if [ -n "$hits" ]; then
    printf '%s\n' "$hits" >&2
    exit 1
fi
