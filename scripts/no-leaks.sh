#!/usr/bin/env sh
set -eu

identity='(^|[^A-Za-z0-9._%+/-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*'
octet='[0-9]{1,3}'
rfc1918="(^|[^0-9.])(10\\.$octet|192\\.168|172\\.(1[6-9]|2[0-9]|3[01]))\\.$octet\\.$octet([^0-9]|\$)"
home_path='/home/[A-Za-z0-9._-]+/'
public_git_ssh_clone_url='(^|[^A-Za-z0-9._%+/-])git@(github\.com|gitlab\.com|bitbucket\.org):'
npm_version_specifier='(^|[^A-Za-z0-9._%+/-])[A-Za-z0-9._%+-]+@[0-9]+\.[0-9]+\.[0-9]+([^0-9.]|$)'

files=$(git ls-files -- . ':!tests/fixtures/**')

hits=$(printf '%s\n' "$files" | while IFS= read -r file; do
    [ -f "$file" ] || continue
    chunk_size=$(head -c 8000 "$file" | wc -c)
    text_size=$(head -c 8000 "$file" | LC_ALL=C tr -d '\000' | wc -c)
    [ "$chunk_size" -ne "$text_size" ] && continue
    sed -E "s#$public_git_ssh_clone_url#\\1public-git-ssh-clone-url#g" -- "$file" \
        | sed -E "s#$npm_version_specifier#\\1npm-package-version\\2#g" \
        | grep -nIE -e "$identity" -e "$rfc1918" -e "$home_path" | cut -d: -f1 | sed "s|^|$file:|"
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
