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

expect "marketplace.json names this marketplace agent-sdlc" \
    test "$(jq -r .name "$dir/.claude-plugin/marketplace.json")" = agent-sdlc
expect "marketplace.json names an owner" \
    test -n "$(jq -r '.owner.name // empty' "$dir/.claude-plugin/marketplace.json")"
expect "marketplace.json's plugin source is this repo" \
    test "$(jq -r '.plugins[0].source' "$dir/.claude-plugin/marketplace.json")" = "./"

assert_tree() {
    label="$1"
    expect "[$label] codex skill is a symlink" test -L "$home/.codex/skills/diagnose"
    expect "[$label] codex command rendered as a skill file" test -f "$home/.codex/skills/done/SKILL.md"
    expect "[$label] codex command skill is not a symlink" test ! -L "$home/.codex/skills/done/SKILL.md"
    expect "[$label] codex command skill names itself" grep -qx 'name: done' "$home/.codex/skills/done/SKILL.md"
    expect "[$label] codex command skill carries a description" grep -q '^description: Finalize the smallest coherent' "$home/.codex/skills/done/SKILL.md"
    expect "[$label] codex command skill keeps the body" grep -qx '# Done' "$home/.codex/skills/done/SKILL.md"
    expect "[$label] no global codex AGENTS.md" test ! -e "$home/.codex/AGENTS.md"
    expect "[$label] nothing installed into ~/.claude, the plugin owns it" test ! -e "$home/.claude"
}

HOME="$home" sh "$dir/install.sh" --target all
assert_tree "first run"

second=$(HOME="$home" sh "$dir/install.sh" --target all 2>&1)
expect "second run exits clean and prints nothing" test -z "$second"
assert_tree "second run"

claude_only=$(mktemp -d)
if HOME="$claude_only" sh "$dir/install.sh" --target claude >"$claude_only.out" 2>&1; then
    echo "FAIL: --target claude exited zero" >&2
    failures=$((failures + 1))
fi
expect "[claude only] points at the plugin install" \
    grep -q 'claude plugin install agent-sdlc@agent-sdlc' "$claude_only.out"
expect "[claude only] no claude tree" test ! -e "$claude_only/.claude"
expect "[claude only] no codex tree" test ! -e "$claude_only/.codex"

codex_only=$(mktemp -d)
HOME="$codex_only" sh "$dir/install.sh" --target codex
expect "[codex only] codex skill present" test -L "$codex_only/.codex/skills/diagnose"
expect "[codex only] no claude tree" test ! -e "$codex_only/.claude"

rm -rf "$home" "$claude_only" "$claude_only.out" "$codex_only"

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

uninstall_home=$(mktemp -d)
mkdir -p "$uninstall_home/.claude/skills" "$uninstall_home/.claude/commands" "$uninstall_home/.claude/bin"
for d in "$dir"/skills/*/; do
    ln -s "${d%/}" "$uninstall_home/.claude/skills/$(basename "$d")"
done
for f in "$dir"/commands/*.md; do
    ln -s "$f" "$uninstall_home/.claude/commands/$(basename "$f")"
done
for f in "$dir"/bin/*; do
    ln -s "$f" "$uninstall_home/.claude/bin/$(basename "$f")"
done
jq '{hooks: .hooks}
    | .hooks.Stop += [{"hooks":[{"type":"command","command":"sh $HOME/.claude/bin/mutation-gate-hook.sh"}]},
                      {"hooks":[{"type":"command","command":"mutation-gate --worktree"}]}]' \
    "$dir/settings.example.json" > "$uninstall_home/.claude/settings.json"
printf 'mine\n' > "$uninstall_home/.claude/CLAUDE.md"
HOME="$uninstall_home" sh "$dir/install.sh" --target codex >/dev/null

settings="$uninstall_home/.claude/settings.json"
tmp=$(mktemp)
jq '.permissions = {"allow": ["Bash(ls *)"]}
    | .hooks.Stop += [{"hooks":[{"type":"command","command":"echo unrelated-stop"}]}]
    | .hooks.Stop += [{"hooks":[{"type":"command","command":"echo sibling-stop"},{"type":"command","command":"/opt/legacy/bin/mutation-gate --worktree"}]}]
    | .hooks.PreToolUse += [{"matcher":"Bash","hooks":[{"type":"command","command":"echo unrelated-pretooluse"}]}]' \
    "$settings" > "$tmp"
mv "$tmp" "$settings"

foreign=$(mktemp -d)
mkdir -p "$foreign/bin"
: > "$foreign/bin/git-guardrail.sh"
chmod +x "$foreign/bin/git-guardrail.sh"
ln -sfn "$foreign/bin/git-guardrail.sh" "$uninstall_home/.claude/bin/git-guardrail.sh"

HOME="$uninstall_home" sh "$dir/install.sh" --uninstall-legacy >/dev/null

expect "[uninstall] owned skill symlink removed" test ! -e "$uninstall_home/.claude/skills/diagnose"
expect "[uninstall] owned command symlink removed" test ! -e "$uninstall_home/.claude/commands/done.md"
expect "[uninstall] owned bin symlink removed" test ! -e "$uninstall_home/.claude/bin/say-hook.sh"
expect "[uninstall] a bin symlink pointing at a different clone survives" \
    test "$(readlink "$uninstall_home/.claude/bin/git-guardrail.sh")" = "$foreign/bin/git-guardrail.sh"
expect "[uninstall] settings.json drops the say hook" \
    test "$(jq '[.hooks.Stop[]?.hooks[]?.command | select(contains("say-hook.sh"))] | length' "$settings")" = 0
expect "[uninstall] settings.json drops the mutation-gate hook" \
    test "$(jq '[.hooks.Stop[]?.hooks[]?.command | select(contains("mutation-gate-hook.sh"))] | length' "$settings")" = 0
expect "[uninstall] settings.json drops every mutation-gate --worktree entry" \
    test "$(jq '[.hooks.Stop[]?.hooks[]?.command | select(contains("mutation-gate --worktree"))] | length' "$settings")" = 0
expect "[uninstall] a sibling hook sharing the absolute-path gate entry's group survives" \
    jq -e '[.hooks.Stop[]?.hooks[]?.command | select(contains("sibling-stop"))] | length == 1' "$settings"
expect "[uninstall] the not-owned git-guardrail hook survives" \
    jq -e '.hooks.PreToolUse | tostring | contains("git-guardrail.sh")' "$settings"
expect "[uninstall] an unrelated Stop entry survives" \
    jq -e '[.hooks.Stop[]?.hooks[]?.command | select(contains("unrelated-stop"))] | length == 1' "$settings"
expect "[uninstall] an unrelated PreToolUse entry survives" \
    jq -e '[.hooks.PreToolUse[]?.hooks[]?.command | select(contains("unrelated-pretooluse"))] | length == 1' "$settings"
expect "[uninstall] top-level permissions block survives" \
    jq -e '.permissions.allow | index("Bash(ls *)")' "$settings"
expect "[uninstall] CLAUDE.md is untouched" test -f "$uninstall_home/.claude/CLAUDE.md"
expect "[uninstall] codex install is untouched" test -L "$uninstall_home/.codex/skills/diagnose"

before_second=$(jq -c . "$settings")
second_uninstall=$(HOME="$uninstall_home" sh "$dir/install.sh" --uninstall-legacy 2>&1)
expect "[uninstall] a second run is a no-op" test -z "$second_uninstall"
expect "[uninstall] a second run changes nothing in settings.json" \
    test "$(jq -c . "$settings")" = "$before_second"

rm -rf "$uninstall_home" "$foreign"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
