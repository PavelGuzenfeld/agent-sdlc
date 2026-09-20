#!/usr/bin/env sh
set -eu

identity='(^|[^A-Za-z0-9._%+/-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*'
octet='[0-9]{1,3}'
rfc1918="(^|[^0-9.])(10\\.$octet|192\\.168|172\\.(1[6-9]|2[0-9]|3[01]))\\.$octet\\.$octet([^0-9]|\$)"
home_path='/home/[A-Za-z0-9._-]+/'

public_git_ssh_clone_url_pattern='(^|[^A-Za-z0-9._%+/-])git@(github\.com|gitlab\.com|bitbucket\.org):'
public_git_ssh_clone_url_replacement='\1public-git-ssh-clone-url'

npm_version_specifier_pattern='(^|[^A-Za-z0-9._%+/-])[A-Za-z0-9._%+-]+@[0-9]+\.[0-9]+\.[0-9]+([^0-9.]|$)'
npm_version_specifier_replacement='\1npm-package-version\2'

identity_carve_outs='public_git_ssh_clone_url npm_version_specifier'

carve_out_sed_program() {
    program=''
    for carve_out in $identity_carve_outs; do
        eval "pattern=\$${carve_out}_pattern"
        eval "replacement=\$${carve_out}_replacement"
        program="${program}s#${pattern}#${replacement}#g;"
    done
    printf '%s' "$program"
}

is_text_file() {
    chunk_size=$(head -c 8000 "$1" | wc -c)
    text_size=$(head -c 8000 "$1" | LC_ALL=C tr -d '\000' | wc -c)
    [ "$chunk_size" -eq "$text_size" ]
}

scan_identity_patterns() {
    sed -E "$carve_out_program" -- "$1" \
        | grep -nIE -e "$identity" -e "$rfc1918" -e "$home_path" | cut -d: -f1 | sed "s|^|$1:|"
}

scan_ghcr_namespace() {
    awk -v file="$1" '{
        line = tolower($0)
        gsub(/ghcr\.io\/pavelguzenfeld\//, "", line)
        if (line ~ /ghcr\.io\/[a-z0-9._-]+\//) print file ":" NR
    }' "$1"
}

carve_out_program=$(carve_out_sed_program)

files=$(git ls-files -- . ':!tests/fixtures/**')

hits=$(printf '%s\n' "$files" | while IFS= read -r file; do
    [ -f "$file" ] || continue
    is_text_file "$file" || continue
    scan_identity_patterns "$file"
    scan_ghcr_namespace "$file"
done | sort -t: -k1,1 -k2,2n -u)

if [ -n "$hits" ]; then
    printf '%s\n' "$hits" >&2
    exit 1
fi
