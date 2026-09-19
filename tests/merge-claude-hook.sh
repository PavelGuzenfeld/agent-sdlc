#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
script="$dir/bin/merge-claude-hook.sh"
failures=0

fresh_settings() {
    tmp=$(mktemp)
    printf '%s' "$1" > "$tmp"
    printf '%s' "$tmp"
}

expect_json_eq() {
    name="$1"
    file="$2"
    want="$3"
    got=$(jq -c . "$file")
    wantc=$(printf '%s' "$want" | jq -c .)
    if [ "$got" != "$wantc" ]; then
        echo "FAIL: $name" >&2
        echo "  want: $wantc" >&2
        echo "  got:  $got" >&2
        failures=$((failures + 1))
    fi
}

settings=$(fresh_settings '{"hooks":{}}')
frag=$(mktemp)
printf '%s' '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"mutation-gate --worktree"}]}]}}' > "$frag"

"$script" "$settings" "Stop" "mutation-gate --worktree" \
    '.hooks.Stop = ((.hooks.Stop // []) + $frag[0].hooks.Stop)' \
    --slurpfile frag "$frag"
expect_json_eq "fragment merge appends Stop hook" "$settings" \
    '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"mutation-gate --worktree"}]}]}}'

before=$(jq -c . "$settings")
"$script" "$settings" "Stop" "mutation-gate --worktree" \
    '.hooks.Stop = ((.hooks.Stop // []) + $frag[0].hooks.Stop)' \
    --slurpfile frag "$frag"
expect_json_eq "fragment merge is idempotent on rerun" "$settings" "$before"

settings=$(fresh_settings '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"mutation-gate --worktree"}]}]}}')
"$script" "$settings" "Stop" "say-hook.sh" \
    '.hooks.Stop = ((.hooks.Stop // []) + [{"hooks":[{"type":"command","command":$cmd}]}])' \
    --arg cmd "sh ~/.claude/bin/say-hook.sh"
expect_json_eq "inline merge preserves the pre-existing Stop hook" "$settings" \
    '{"hooks":{"Stop":[
        {"hooks":[{"type":"command","command":"mutation-gate --worktree"}]},
        {"hooks":[{"type":"command","command":"sh ~/.claude/bin/say-hook.sh"}]}
    ]}}'

before=$(jq -c . "$settings")
"$script" "$settings" "Stop" "say-hook.sh" \
    '.hooks.Stop = ((.hooks.Stop // []) + [{"hooks":[{"type":"command","command":$cmd}]}])' \
    --arg cmd "sh ~/.claude/bin/say-hook.sh"
expect_json_eq "inline merge is idempotent on rerun" "$settings" "$before"

settings=$(fresh_settings '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo see git-guardrail.sh for policy"}]}]}}')
"$script" "$settings" "PreToolUse" "git-guardrail.sh" \
    '.hooks.PreToolUse = ((.hooks.PreToolUse // []) + [{"hooks":[{"type":"command","command":"git-guardrail.sh"}]}])'
expect_json_eq "guard scoped to the target hook array, not the whole file" "$settings" \
    '{"hooks":{
        "Stop":[{"hooks":[{"type":"command","command":"echo see git-guardrail.sh for policy"}]}],
        "PreToolUse":[{"hooks":[{"type":"command","command":"git-guardrail.sh"}]}]
    }}'

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
