#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

dir="$(cd "$(dirname "$0")/.." && pwd)"
failures=0
image=agent-sdlc-host-exec-test:pytest

fail() {
    echo "FAIL: $1" >&2
    shift
    [ $# -gt 0 ] && printf '%s\n' "$@" >&2
    failures=$((failures + 1))
}

hook_cmd=$(jq -r '.hooks.PreToolUse[] | select(.matcher == "Bash") | .hooks[].command | select(contains("mutation_gate.host_exec"))' "$dir/hooks/hooks.json")
[ -n "$hook_cmd" ] || fail "hooks/hooks.json has no Bash PreToolUse entry for host-exec"

printf 'FROM python:3.12-slim\nRUN pip install --no-cache-dir -q pytest\n' | docker build -q -t "$image" - >/dev/null

new_repo() {
    repo=$(mktemp -d)
    git -C "$repo" init -q -b main
    printf '%s' "$1" > "$repo/.mutation-gate.toml"
    cat > "$repo/test_writes.py" <<'EOF'
from pathlib import Path


def test_writes_a_file():
    Path("written-by-test.txt").write_text("x")
EOF
    printf '%s' "$repo"
}

run_hook() {
    payload=$(jq -n --arg cwd "$1" --arg c "$2" \
        '{cwd: $cwd, tool_name: "Bash", tool_input: {command: $c, description: "run tests"}}')
    (cd "$1" && printf '%s' "$payload" | CLAUDE_PLUGIN_ROOT="$dir" sh -c "$hook_cmd")
}

with_image=$(new_repo "test_image = \"$image\"
")
set +e
out=$(run_hook "$with_image" "pytest -q" 2>"$with_image.err")
code=$?
set -e
if [ "$code" -ne 0 ]; then
    fail "pytest -q with test_image set: expected exit 0, got $code" "$(cat "$with_image.err")"
else
    rewritten=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.updatedInput.command')
    decision=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision')
    description=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.updatedInput.description')
    [ "$decision" = "allow" ] || fail "rewrite decision: expected allow, got $decision" "$out"
    [ "$description" = "run tests" ] || fail "rewrite dropped the other tool_input fields" "$out"
    case "$rewritten" in
        "docker run --rm --user \$(id -u):\$(id -g) -e HOME=/tmp -v \"\$PWD:/w\" -w /w $image "*) ;;
        *) fail "rewritten command has the wrong prefix" "$rewritten" ;;
    esac
    set +e
    run_out=$(cd "$with_image" && sh -c "$rewritten" 2>&1)
    run_code=$?
    set -e
    if [ "$run_code" -ne 0 ]; then
        fail "rewritten pytest -q failed with $run_code" "$run_out"
    elif ! printf '%s' "$run_out" | grep -q '1 passed'; then
        fail "rewritten pytest -q did not run the test" "$run_out"
    elif [ "$(stat -c %u "$with_image/written-by-test.txt")" != "$(id -u)" ]; then
        fail "file the test wrote is not owned by the invoking user" "$(ls -ln "$with_image")"
    fi
fi

without_image=$(new_repo "")
set +e
run_hook "$without_image" "pytest -q" >/dev/null 2>"$without_image.err"
code=$?
set -e
[ "$code" -eq 2 ] || fail "pytest -q with no image: expected exit 2, got $code"
grep -q 'test_image' "$without_image.err" || fail "no-image denial does not name test_image" "$(cat "$without_image.err")"

switched_off=$(new_repo "is_test_image_used = false
")
set +e
out=$(run_hook "$switched_off" "pytest -q" 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] && [ -z "$out" ] || fail "is_test_image_used = false: expected silent pass, got $code" "$out"

set +e
run_hook "$with_image" 'docker run --rm -v "$PWD:/w" -w /w python:3.12-slim true' >/dev/null 2>"$with_image.err"
code=$?
set -e
[ "$code" -eq 2 ] || fail "docker run bind-mounting the repo without --user: expected exit 2, got $code"
grep -qF 'docker run --user $(id -u):$(id -g) --rm -v "$PWD:/w"' "$with_image.err" \
    || fail "--user denial does not give the corrected command" "$(cat "$with_image.err")"

set +e
out=$(run_hook "$with_image" 'docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/repo -w /repo python:3.12-slim true' 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] && [ -z "$out" ] || fail "docker run with -u: expected silent pass, got $code" "$out"

set +e
out=$(run_hook "$with_image" 'docker run --rm -v "$PWD":/w alpine:3.20 chown -R $(id -u):$(id -g) /w' 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] && [ -z "$out" ] || fail "kata teardown chown: expected silent pass, got $code" "$out"

no_config=$(new_repo "")
rm "$no_config/.mutation-gate.toml"
set +e
out=$(run_hook "$no_config" "pytest -q" 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] && [ -z "$out" ] || fail "repo without .mutation-gate.toml: expected silent pass, got $code" "$out"

if [ "$failures" -gt 0 ]; then
    echo "$failures failure(s)" >&2
    exit 1
fi
echo "host-exec-hook: ok"
