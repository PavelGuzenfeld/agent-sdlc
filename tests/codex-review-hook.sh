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

hook_cmd=$(jq -r '.hooks.Stop[].hooks[].command | select(contains("codex-review-hook.sh"))' "$dir/hooks/hooks.json")
[ -n "$hook_cmd" ] || fail "hooks/hooks.json has no Stop entry for codex-review-hook.sh"

real_path() {
    stub="$1"
    mkdir -p "$stub"
    for tool in git jq sh cat mktemp rm cp head grep printf timeout dirname ls; do
        ln -s "$(command -v "$tool")" "$stub/$tool"
    done
    printf '%s' "$stub"
}

consumer=$(mktemp -d)
git -C "$consumer" init -q -b main
printf 'one\n' > "$consumer/kept.txt"
git -C "$consumer" add kept.txt
git -C "$consumer" -c user.email=s -c user.name=s commit -q -m init
payload="{\"cwd\":\"$consumer\",\"last_assistant_message\":\"edited files\"}"

stub_dir=$(mktemp -d)
cat > "$stub_dir/codex" <<'EOSTUB'
#!/usr/bin/env sh
calls=$(cat "$STUB_LOG.calls" 2>/dev/null || echo 0)
echo $((calls + 1)) > "$STUB_LOG.calls"
printf '%s\n' "$@" > "$STUB_LOG.args"
work=""
out=""
while [ $# -gt 0 ]; do
    case "$1" in
        -C) work="$2"; shift ;;
        -o) out="$2"; shift ;;
    esac
    shift
done
ls -A "$work/baseline" > "$STUB_LOG.baseline"
ls -A "$work/candidate" > "$STUB_LOG.candidate"
[ -f "$STUB_VERDICT" ] && cp "$STUB_VERDICT" "$out"
exit "$(cat "$STUB_EXIT" 2>/dev/null || echo 0)"
EOSTUB
chmod +x "$stub_dir/codex"

base_path=$(real_path "$(mktemp -d)")
gate_path="$stub_dir:$base_path"
log="$stub_dir/log"
verdict="$stub_dir/verdict"
exit_file="$stub_dir/exit"

run_hook() {
    CLAUDE_PLUGIN_ROOT="$dir" PATH="$1" STUB_LOG="$log" STUB_VERDICT="$verdict" STUB_EXIT="$exit_file" \
        sh -c "$hook_cmd" <<EOF
$payload
EOF
}

calls() { cat "$log.calls" 2>/dev/null || echo 0; }

printf 'two\n' > "$consumer/added.txt"

set +e
out=$(run_hook "$gate_path" 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] || fail "a repo without agent-sdlc.codexReview should exit 0" "got $code: $out"
[ "$(calls)" -eq 0 ] || fail "codex ran in a repo that never opted in"

git -C "$consumer" config agent-sdlc.codexReview true

set +e
out=$(run_hook "$base_path" 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] || fail "opted in but codex absent should exit 0" "got $code: $out"
printf '%s' "$out" | grep -q 'codex' || fail "the missing-codex case did not name codex" "$out"

printf 'BLOCK: added.txt breaks the build\ncommand: make check\ncandidate: exit 2\nbaseline: exit 0\n' > "$verdict"
set +e
out=$(run_hook "$gate_path")
code=$?
set -e
[ "$code" -eq 0 ] || fail "a BLOCK verdict should still exit 0 and block through JSON" "got $code"
[ "$(printf '%s' "$out" | jq -r .decision 2>/dev/null)" = block ] \
    || fail "a reproduced regression did not block the stop" "$out"
printf '%s' "$out" | jq -r .reason | grep -q 'baseline: exit 0' \
    || fail "the block reason dropped codex's evidence" "$out"
grep -qx added.txt "$log.candidate" || fail "the uncommitted new file never reached the candidate checkout"
grep -qx added.txt "$log.baseline" && fail "the baseline checkout already had the turn's new file"
grep -qx -- danger-full-access "$log.args" || fail "codex did not get full access to run docker and the network"
[ -f "$consumer/added.txt" ] && [ -z "$(git -C "$consumer" diff --cached --name-only)" ] \
    || fail "the hook disturbed the live checkout's files or index"
[ "$(git -C "$consumer" worktree list | wc -l)" -eq 1 ] \
    || fail "the review worktrees were left registered" "$(git -C "$consumer" worktree list)"

set +e
out=$(run_hook "$gate_path")
set -e
[ "$(calls)" -eq 1 ] || fail "an unchanged tree since the last review ran codex again"
[ -z "$out" ] || fail "a skipped review still printed a decision" "$out"

printf 'three\n' >> "$consumer/added.txt"
printf 'ALLOW: no regression reproduced\n' > "$verdict"
set +e
out=$(run_hook "$gate_path")
set -e
[ "$(calls)" -eq 2 ] || fail "a changed tree did not trigger a new review"
grep -qx added.txt "$log.baseline" && fail "a tree codex blocked became the baseline for the fix"
[ -z "$out" ] || fail "a clean ALLOW blocked or printed" "$out"

printf 'four\n' >> "$consumer/added.txt"
printf 'ALLOW: nothing new\nDEBT: kept.txt parser drops the last line | ./parse kept.txt | fails at both\n' > "$verdict"
set +e
out=$(run_hook "$gate_path")
set -e
[ "$(printf '%s' "$out" | jq -r .decision 2>/dev/null)" = block ] \
    || fail "a pre-existing issue was not handed back to be filed" "$out"
printf '%s' "$out" | jq -r .reason | grep -q 'DEBT: kept.txt parser drops the last line' \
    || fail "the debt line did not reach the reason" "$out"

git -C "$consumer" add added.txt
git -C "$consumer" -c user.email=s -c user.name=s commit -q -m accepted
set +e
out=$(run_hook "$gate_path")
set -e
[ "$(calls)" -eq 3 ] || fail "committing the already accepted tree ran codex again"
printf 'six\n' > "$consumer/kept.txt"
git -C "$consumer" -c user.email=s -c user.name=s commit -q -am turn
printf 'ALLOW: fine\n' > "$verdict"
run_hook "$gate_path" >/dev/null
[ "$(calls)" -eq 4 ] || fail "a commit since the last review did not trigger a review"
grep -qx added.txt "$log.baseline" \
    || fail "after a commit the baseline was not the last accepted tree" "$(cat "$log.baseline")"

printf 'five\n' >> "$consumer/added.txt"
echo 1 > "$exit_file"
rm -f "$verdict"
set +e
out=$(run_hook "$gate_path" 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] || fail "a failed codex run should not block the stop" "got $code: $out"
run_hook "$gate_path" >/dev/null 2>&1 || true
[ "$(calls)" -eq 6 ] || fail "a failed review was recorded, so the tree will never be reviewed"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
