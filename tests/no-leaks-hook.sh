#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

dir="$(cd "$(dirname "$0")/.." && pwd)"
rev=$(git -C "$dir" rev-parse HEAD)
consumer=$(mktemp -d)
work=$(mktemp -d)

fail() {
    echo "FAIL: $1" >&2
    shift
    [ $# -gt 0 ] && printf '%s\n' "$@" >&2
    rm -rf "$consumer" "$work"
    exit 1
}

cgit() {
    git -C "$consumer" -c user.email=sentinel -c user.name=sentinel "$@"
}

email_content=$(awk -F'|' '$1 == "email" { print $2 }' "$dir/tests/fixtures/leaky.txt")
[ -n "$email_content" ] || { echo "FAIL: leaky.txt has no 'email' row" >&2; exit 1; }

banned_file="$work/banned-names.txt"
printf '%s\n' '- foo → bar' > "$banned_file"
missing_file="$work/missing.txt"

git -C "$consumer" init -q -b main
printf 'test_paths = ["tests"]\nbanned_names_file = "%s"\n' "$banned_file" > "$consumer/.mutation-gate.toml"
cgit add .mutation-gate.toml
cgit commit -q -m init

cgit checkout -q -b banned-name main
printf 'token = "foo"\n' > "$consumer/config.txt"
cgit add config.txt
cgit commit -q -m "add config"
set +e
range_out=$(cd "$consumer" && mutation-gate no-leaks --range "main..HEAD" 2>&1)
range_code=$?
set -e
[ "$range_code" -eq 1 ] || fail "--range should block a banned name (got $range_code)" "$range_out"
printf '%s' "$range_out" | grep -qF 'use "bar"' || fail "--range block did not suggest the replacement" "$range_out"
printf '%s' "$range_out" | grep -qF "foo" && fail "--range block echoed the banned token" "$range_out"

cat > "$consumer/.pre-commit-config.yaml" <<YAML
repos:
  - repo: $dir
    rev: $rev
    hooks:
      - id: no-leaks
YAML
(cd "$consumer" && pre-commit install --hook-type commit-msg >/dev/null)

cgit checkout -q -b hooked main
printf 'token = "foo"\n' > "$consumer/hooked.txt"
cgit add hooked.txt
set +e
hook_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add hooked" 2>&1)
hook_code=$?
set -e
[ "$hook_code" -ne 0 ] || fail "the hook should reject a staged banned name"
printf '%s' "$hook_out" | grep -qF 'use "bar"' || fail "the hook rejection did not suggest the replacement" "$hook_out"
printf '%s' "$hook_out" | grep -qF "foo" && fail "the hook rejection echoed the banned token" "$hook_out"
cgit reset -q --hard main

printf '%s\n' "$email_content" > "$consumer/identity.txt"
cgit add identity.txt
set +e
present_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add identity" 2>&1)
present_code=$?
set -e
[ "$present_code" -ne 0 ] || fail "the hook should reject a staged email address with banned_names_file present"
printf '%s' "$present_out" | grep -qF "identity.txt:1" || fail "the hook rejection did not name identity.txt:1" "$present_out"
printf '%s' "$present_out" | grep -qF "$email_content" && fail "the hook rejection echoed the email address" "$present_out"
cgit reset -q --hard main

mkdir -p "$consumer/tests/fixtures"
printf '%s\n' "$email_content" > "$consumer/tests/fixtures/x.txt"
cgit add tests/fixtures/x.txt
(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add fixture") \
    || fail "the hook should not block an email address staged under tests/fixtures/**"
cgit reset -q --hard main

printf 'test_paths = ["tests"]\nbanned_names_file = "%s"\n' "$missing_file" > "$consumer/.mutation-gate.toml"
cgit add .mutation-gate.toml
cgit commit -q -m "point banned_names_file at a missing file"

printf 'token = "foo"\n' > "$consumer/hooked.txt"
cgit add hooked.txt
(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add hooked") \
    || fail "a banned_names_file pointing at a missing file should skip that check"

printf '%s\n' "$email_content" > "$consumer/identity.txt"
cgit add identity.txt
set +e
email_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add identity" 2>&1)
email_code=$?
set -e
[ "$email_code" -ne 0 ] || fail "the hook should reject a staged email address even with a missing banned_names_file"
printf '%s' "$email_out" | grep -qF "identity.txt:1" || fail "the hook rejection did not name identity.txt:1" "$email_out"
printf '%s' "$email_out" | grep -qF "$email_content" && fail "the hook rejection echoed the email address" "$email_out"
cgit reset -q --hard main

cgit config diff.noprefix true
printf '%s\n' "$email_content" > "$consumer/identity.txt"
cgit add identity.txt
set +e
noprefix_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add identity" 2>&1)
noprefix_code=$?
set -e
[ "$noprefix_code" -ne 0 ] || fail "the hook should reject a staged email address under diff.noprefix"
printf '%s' "$noprefix_out" | grep -qF "identity.txt:1" || fail "the hook rejection under diff.noprefix did not name identity.txt:1" "$noprefix_out"
printf '%s' "$noprefix_out" | grep -qF "$email_content" && fail "the hook rejection under diff.noprefix echoed the email address" "$noprefix_out"
cgit config --unset diff.noprefix
cgit reset -q --hard main

cgit config diff.mnemonicPrefix true
printf '%s\n' "$email_content" > "$consumer/identity.txt"
cgit add identity.txt
set +e
mnemonic_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add identity" 2>&1)
mnemonic_code=$?
set -e
[ "$mnemonic_code" -ne 0 ] || fail "the hook should reject a staged email address under diff.mnemonicPrefix"
printf '%s' "$mnemonic_out" | grep -qF "identity.txt:1" || fail "the hook rejection under diff.mnemonicPrefix did not name identity.txt:1" "$mnemonic_out"
printf '%s' "$mnemonic_out" | grep -qF "$email_content" && fail "the hook rejection under diff.mnemonicPrefix echoed the email address" "$mnemonic_out"
cgit config --unset diff.mnemonicPrefix
cgit reset -q --hard main

hide_textconv="$work/hide-textconv.sh"
cat > "$hide_textconv" <<'SH'
#!/usr/bin/env sh
exit 0
SH
chmod +x "$hide_textconv"
printf 'identity.txt diff=hide\n' > "$consumer/.gitattributes"
cgit add .gitattributes
cgit commit -q -m "add textconv attribute"
cgit config "diff.hide.textconv" "$hide_textconv"
printf '%s\n' "$email_content" > "$consumer/identity.txt"
cgit add identity.txt
set +e
textconv_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add identity" 2>&1)
textconv_code=$?
set -e
[ "$textconv_code" -ne 0 ] || fail "the hook should reject a staged email address hidden behind a textconv filter"
printf '%s' "$textconv_out" | grep -qF "identity.txt:1" || fail "the hook rejection behind a textconv filter did not name identity.txt:1" "$textconv_out"
printf '%s' "$textconv_out" | grep -qF "$email_content" && fail "the hook rejection behind a textconv filter echoed the email address" "$textconv_out"
cgit config --unset "diff.hide.textconv"
cgit reset -q --hard main

printf '%s\n' "$email_content" > "$consumer/café identity.txt"
cgit add "café identity.txt"
set +e
quoted_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add identity" 2>&1)
quoted_code=$?
set -e
[ "$quoted_code" -ne 0 ] || fail "the hook should reject a staged email address behind a quoted non-ascii path"
printf '%s' "$quoted_out" | grep -qF "identity.txt:1" || fail "the hook rejection behind a quoted path did not name the file" "$quoted_out"
printf '%s' "$quoted_out" | grep -qF "$email_content" && fail "the hook rejection behind a quoted path echoed the email address" "$quoted_out"
cgit reset -q --hard main

rm -rf "$consumer" "$work"
echo "all cases passed"
