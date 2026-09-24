#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

dir="$(cd "$(dirname "$0")/.." && pwd)"
failures=0

fail() {
    echo "FAIL: $1" >&2
    shift
    [ $# -gt 0 ] && printf '%s\n' "$@" >&2
    failures=$((failures + 1))
}

hook_cmd=$(jq -r '.hooks.Stop[].hooks[].command | select(contains("mutation-gate-hook.sh"))' "$dir/hooks/hooks.json")
[ -n "$hook_cmd" ] || fail "hooks/hooks.json has no Stop entry for mutation-gate-hook.sh"

real_path() {
    stub="$1"
    mkdir -p "$stub"
    for tool in git jq sh cat; do
        ln -s "$(command -v "$tool")" "$stub/$tool"
    done
    printf '%s' "$stub"
}

consumer=$(mktemp -d)
git -C "$consumer" init -q -b main
git -C "$consumer" -c user.email=s -c user.name=s commit -q --allow-empty -m init

run_hook() {
    path="$1"
    payload="$2"
    CLAUDE_PLUGIN_ROOT="$dir" PATH="$path" sh -c "$hook_cmd" <<EOF
$payload
EOF
}

path_without_gate=$(real_path "$(mktemp -d)")
payload="{\"cwd\":\"$consumer\"}"

set +e
out=$(run_hook "$path_without_gate" "$payload" 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] || fail "no .mutation-gate.toml should exit 0" "got $code: $out"

: > "$consumer/.mutation-gate.toml"

set +e
out=$(run_hook "$path_without_gate" "$payload" 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] || fail ".mutation-gate.toml present but mutation-gate absent should still exit 0" "got $code: $out"
printf '%s' "$out" | grep -qi 'mutation-gate' \
    || fail "missing-mutation-gate case did not name mutation-gate in its message" "$out"

stub_dir=$(mktemp -d)
stub_marker="$stub_dir/invoked"
stub_exit="$stub_dir/exit-code"
cat > "$stub_dir/mutation-gate" <<'EOSTUB'
#!/usr/bin/env sh
printf '%s' "$*" > "$STUB_MARKER.args"
cat > "$STUB_MARKER"
exit "$(cat "$STUB_EXIT" 2>/dev/null || echo 0)"
EOSTUB
chmod +x "$stub_dir/mutation-gate"
path_with_gate="$stub_dir:$path_without_gate"

echo 0 > "$stub_exit"
set +e
out=$(STUB_MARKER="$stub_marker" STUB_EXIT="$stub_exit" run_hook "$path_with_gate" "$payload" 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] || fail "a passing gate should exit 0" "got $code: $out"
[ -f "$stub_marker" ] || fail "mutation-gate stub was never invoked with .mutation-gate.toml present"
[ "$(cat "$stub_marker" 2>/dev/null)" = "$payload" ] || fail "stdin payload was not forwarded to mutation-gate"
[ "$(cat "$stub_marker.args" 2>/dev/null)" = "--worktree" ] || fail "mutation-gate was not invoked with --worktree"

echo 1 > "$stub_exit"
rm -f "$stub_marker" "$stub_marker.args"
set +e
STUB_MARKER="$stub_marker" STUB_EXIT="$stub_exit" run_hook "$path_with_gate" "$payload" >/dev/null 2>&1
code=$?
set -e
[ "$code" -eq 1 ] || fail "a blocking gate's exit code should propagate" "got $code"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
