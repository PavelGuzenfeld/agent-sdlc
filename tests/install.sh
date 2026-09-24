#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
home=$(mktemp -d)
failures=0

expect() {
    name="$1"
    shift
    if ! "$@" >/dev/null; then
        echo "FAIL: $name" >&2
        failures=$((failures + 1))
    fi
}

assert_tree() {
    label="$1"
    expect "[$label] claude skill is a symlink" test -L "$home/.claude/skills/diagnose"
    expect "[$label] codex skill is a symlink" test -L "$home/.codex/skills/diagnose"
    expect "[$label] claude command is a symlink" test -L "$home/.claude/commands/done.md"
    expect "[$label] no global claude rules dir" test ! -e "$home/.claude/rules"
    expect "[$label] claude bin script is a symlink" test -L "$home/.claude/bin/git-guardrail.sh"
    expect "[$label] claude bin script is executable" test -x "$home/.claude/bin/git-guardrail.sh"
    expect "[$label] claude bin subdirectory reachable" test -f "$home/.claude/bin/say-tones/arm.raw"
    expect "[$label] codex command rendered as a skill file" test -f "$home/.codex/skills/done/SKILL.md"
    expect "[$label] codex command skill is not a symlink" test ! -L "$home/.codex/skills/done/SKILL.md"
    expect "[$label] codex command skill names itself" grep -qx 'name: done' "$home/.codex/skills/done/SKILL.md"
    expect "[$label] codex command skill carries a description" grep -q '^description: Finalize the smallest coherent' "$home/.codex/skills/done/SKILL.md"
    expect "[$label] codex command skill keeps the body" grep -qx '# Done' "$home/.codex/skills/done/SKILL.md"
    expect "[$label] no global codex AGENTS.md" test ! -e "$home/.codex/AGENTS.md"
    expect "[$label] CLAUDE.md copied" test -f "$home/.claude/CLAUDE.md"
    expect "[$label] settings.json has the guardrail hook" \
        jq -e '.hooks.PreToolUse | tostring | contains("git-guardrail.sh")' "$home/.claude/settings.json"
    expect "[$label] settings.json has the say hook exactly once" \
        test "$(jq '[.hooks.Stop[].hooks[].command | select(contains("say-hook.sh"))] | length' "$home/.claude/settings.json")" = 1
}

HOME="$home" sh "$dir/install.sh" --target all
assert_tree "first run"

printf 'mine\n' > "$home/.claude/CLAUDE.md"
second=$(HOME="$home" sh "$dir/install.sh" --target all 2>&1)
expect "second run exits clean and prints nothing" test -z "$second"
assert_tree "second run"
expect "existing CLAUDE.md is never overwritten" test "$(cat "$home/.claude/CLAUDE.md")" = "mine"

claude_only=$(mktemp -d)
HOME="$claude_only" sh "$dir/install.sh" --target claude
expect "[claude only] claude skill present" test -L "$claude_only/.claude/skills/diagnose"
expect "[claude only] no codex tree" test ! -e "$claude_only/.codex"

codex_only=$(mktemp -d)
HOME="$codex_only" sh "$dir/install.sh" --target codex
expect "[codex only] codex skill present" test -L "$codex_only/.codex/skills/diagnose"
expect "[codex only] no claude tree" test ! -e "$codex_only/.claude"

rm -rf "$home" "$claude_only" "$codex_only"

collide=$(mktemp -d)
mkdir -p "$collide/skills/dup" "$collide/commands"
: > "$collide/commands/dup.md"
cp "$dir/install.sh" "$collide/install.sh"
if HOME="$collide/home" sh "$collide/install.sh" --target all >"$collide/out" 2>&1; then
    echo "FAIL: collision run exited zero" >&2
    failures=$((failures + 1))
fi
expect "collision message names the colliding name" grep -q dup "$collide/out"
rm -rf "$collide"

stubs=$(mktemp -d)
pipx_log="$stubs/pipx.log"
: > "$pipx_log"
ast_grep_version_file="$stubs/ast-grep-version"

cat > "$stubs/ast-grep" <<EOF
#!/usr/bin/env sh
echo "ast-grep \$(cat "$ast_grep_version_file")"
EOF
cat > "$stubs/pipx" <<EOF
#!/usr/bin/env sh
echo "\$*" >> "$pipx_log"
EOF
cat > "$stubs/python3" <<'EOF'
#!/usr/bin/env sh
exit 0
EOF
for name in git gh jq docker curl pre-commit mutation-gate; do
    printf '#!/usr/bin/env sh\nexit 0\n' > "$stubs/$name"
done
chmod +x "$stubs"/*

deps_home=$(mktemp -d)

echo "0.44.1" > "$ast_grep_version_file"
PATH="$stubs:$PATH" HOME="$deps_home" sh "$dir/install.sh" --deps --target codex >/dev/null
expect "a wrong installed ast-grep version is force-reinstalled to the pin" \
    test "$(cat "$pipx_log")" = "install --force ast-grep-cli==0.45.3"

: > "$pipx_log"
echo "0.45.3" > "$ast_grep_version_file"
PATH="$stubs:$PATH" HOME="$deps_home" sh "$dir/install.sh" --deps --target codex >/dev/null
expect "an already-pinned ast-grep version is left alone" test -z "$(cat "$pipx_log")"

rm -rf "$stubs" "$deps_home"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
