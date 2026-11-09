#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
failures=0

hook_cmd=$(jq -r '.hooks.PreToolUse[] | select(.matcher == "Bash") | .hooks[].command | select(contains("bare-rm-guard.sh"))' "$dir/hooks/hooks.json")
[ -n "$hook_cmd" ] || { echo "FAIL: hooks/hooks.json has no Bash PreToolUse entry for bare-rm-guard" >&2; exit 1; }

run_hook() {
    jq -n --arg c "$1" '{tool_name: "Bash", tool_input: {command: $c}}' \
        | CLAUDE_PLUGIN_ROOT="$dir" sh -c "$hook_cmd"
}

expect_block() {
    set +e
    stderr=$(run_hook "$2" 2>&1 >/dev/null)
    code=$?
    set -e
    if [ "$code" -ne 2 ]; then
        echo "FAIL: $1 (expected exit 2, got $code)" >&2
        failures=$((failures + 1))
    elif ! printf '%s' "$stderr" | grep -Fq -- "command $3"; then
        echo "FAIL: $1 (stderr does not point at 'command $3'): $stderr" >&2
        failures=$((failures + 1))
    fi
}

expect_allow() {
    set +e
    stderr=$(run_hook "$2" 2>&1 >/dev/null)
    code=$?
    set -e
    if [ "$code" -ne 0 ]; then
        echo "FAIL: $1 (expected exit 0, got $code): $stderr" >&2
        failures=$((failures + 1))
    fi
}

expect_block "bare rm"                    "rm data/docs.json" rm
expect_block "bare cp"                    "cp a b" cp
expect_block "bare mv"                    "mv a b" mv
expect_block "rm after &&"                "hugo build && rm data/docs.json" rm
expect_block "rm after ;"                 "cd x; rm -f y" rm
expect_block "rm after |"                 "ls | rm y" rm
expect_block "rm after ||"                "test -f y || rm y" rm
expect_block "rm in a subshell"           "(rm y)" rm
expect_block "rm in a subshell after cd"  "(cd x && rm y)" rm
expect_block "rm on a later line"         "echo hi
rm y" rm
expect_block "rm after quoted separator"  'echo "a;b" && rm y' rm
expect_block "rm after then"              "if true; then rm y; fi" rm
expect_block "rm after brace"             "{ rm y; }" rm
expect_block "rm with tab"                "rm	y" rm

expect_allow "command rm"                 "command rm data/docs.json"
expect_allow "command cp"                 "command cp a b"
expect_allow "command mv"                 "command mv a b"
expect_allow "backslash rm"               '\rm y'
expect_allow "absolute path rm"           "/bin/rm y"
expect_allow "git rm"                     "git rm y"
expect_allow "git mv"                     "git mv a b"
expect_allow "echo rm"                    "echo rm"
expect_allow "grep -rn mv"                "grep -rn mv ."
expect_allow "quoted rm"                  'echo "rm y"'
expect_allow "single-quoted rm"           "echo 'a; rm y'"
expect_allow "word starting with rm"      "rmdir y && cpp x && mvn test"
expect_allow "path containing rm"         "ls ./rm/y"
expect_allow "empty command"              ""
expect_allow "heredoc body"               "cat <<EOF > s.sh
rm -rf build
EOF"
expect_allow "quoted heredoc word"        "cat <<'EOF' > s.sh
rm -rf build
EOF"
expect_allow "dash heredoc with tab terminator" "cat <<-EOF > s.sh
rm -rf build
	EOF"
expect_allow "double-quoted separator"    'echo "a; rm y"'
expect_allow "multi-line quoted string"   'echo "a
rm y"'
expect_block "rm after heredoc ends"      "cat <<EOF > s.sh
rm -rf build
EOF
rm y" rm

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
