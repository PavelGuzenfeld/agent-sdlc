#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_script="$dir/bin/git-guardrail.sh"
home_script="${GIT_GUARDRAIL_HOME_SCRIPT:-$HOME/.claude/bin/git-guardrail.sh}"
failures=0

run() {
    payload=$(printf '%s' "$2" | jq -Rs '{tool_input: {command: .}}')
    printf '%s' "$payload" | "$1"
}

expect_block() {
    target="$1"; label="$2"; name="$3"
    set +e
    stderr=$(run "$target" "$4" 2>&1 >/dev/null)
    code=$?
    set -e
    if [ "$code" -ne 2 ]; then
        echo "FAIL: [$label] $name (expected exit 2, got $code)" >&2
        failures=$((failures + 1))
    elif [ -z "$stderr" ]; then
        echo "FAIL: [$label] $name (exit 2 but empty stderr)" >&2
        failures=$((failures + 1))
    fi
}

expect_allow() {
    target="$1"; label="$2"; name="$3"
    set +e
    stderr=$(run "$target" "$4" 2>&1 >/dev/null)
    code=$?
    set -e
    if [ "$code" -ne 0 ]; then
        echo "FAIL: [$label] $name (expected exit 0, got $code): $stderr" >&2
        failures=$((failures + 1))
    fi
}

expect_block_reason() {
    target="$1"; label="$2"; name="$3"; needle="$4"
    set +e
    stderr=$(run "$target" "$5" 2>&1 >/dev/null)
    code=$?
    set -e
    if [ "$code" -ne 2 ]; then
        echo "FAIL: [$label] $name (expected exit 2, got $code)" >&2
        failures=$((failures + 1))
    elif ! printf '%s' "$stderr" | grep -Fq -- "$needle"; then
        echo "FAIL: [$label] $name (exit 2 but stderr missing '$needle'): $stderr" >&2
        failures=$((failures + 1))
    fi
}

run_case_table() {
    target="$1"; label="$2"

    expect_block "$target" "$label" "push --force"        "git push --force origin main"
    expect_block "$target" "$label" "push -f"             "git push -f origin main"
    expect_block "$target" "$label" "push + refspec"      "git push origin +main"
    expect_block "$target" "$label" "reset --hard"        "git reset --hard"
    expect_block "$target" "$label" "clean -fd"           "git clean -fd"
    expect_block "$target" "$label" "checkout ."          "git checkout ."
    expect_block "$target" "$label" "checkout -- ."       "git checkout -- ."
    expect_block "$target" "$label" "restore ."           "git restore ."
    expect_block "$target" "$label" "add -A"              "git add -A"
    expect_block "$target" "$label" "add ."               "git add ."
    expect_block "$target" "$label" "add --all"           "git add --all"
    expect_block "$target" "$label" "branch -D"           "git branch -D old-branch"
    expect_block "$target" "$label" "push --force after quoted ;"   'git push origin "feature;branch" --force'
    expect_block "$target" "$label" "push --force after quoted &"   'git push origin "feature&branch" --force'
    expect_block "$target" "$label" "push --force after quoted |"   'git push origin "feature|branch" --force'

    expect_allow "$target" "$label" "plain push"                 "git push"
    expect_allow "$target" "$label" "push --force-with-lease"    "git push --force-with-lease origin main"
}

run_case_table "$repo_script" "repo"

run_delete_branch_head_cases() {
    label="repo-delete-head"
    tmp=$(mktemp -d)
    origin_dir=$(mktemp -d)/origin.git
    clone_dir=$(mktemp -d)/clone
    (
        unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE
        cd "$tmp"
        git init -q -b main
        git -c user.name=t -c user.email=nobody commit -q --allow-empty -m base
        git rev-parse HEAD >base-sha
        git -c user.name=t -c user.email=nobody branch behind-local HEAD
        git -c user.name=t -c user.email=nobody branch behind-fetch HEAD
        git -c user.name=t -c user.email=nobody branch unfetchable HEAD
        git -c user.name=t -c user.email=nobody branch two-pr HEAD
        git -c user.name=t -c user.email=nobody commit -q --allow-empty -m pr-head
        git rev-parse HEAD >pr-head-sha
        git -c user.name=t -c user.email=nobody branch merged-ok HEAD
        git -c user.name=t -c user.email=nobody commit -q --allow-empty -m local-extra
        git -c user.name=t -c user.email=nobody branch one-past HEAD
        git -c user.name=t -c user.email=nobody checkout -q -b diverged "$(cat base-sha)"
        git -c user.name=t -c user.email=nobody commit -q --allow-empty -m diverged-commit
        git -c user.name=t -c user.email=nobody checkout -q main
        git init -q --bare "$origin_dir"
        git remote add origin "$origin_dir"
    ) >/dev/null 2>&1
    (
        unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE
        git clone -q "$tmp" "$clone_dir"
        cd "$clone_dir"
        git remote add upstream "$origin_dir"
        git -c user.name=t -c user.email=nobody checkout -q "$(cat "$tmp/base-sha")"
        git -c user.name=t -c user.email=nobody commit -q --allow-empty -m fetch-only-head
        git rev-parse HEAD >fetch-head-sha
        git push -q upstream "HEAD:refs/pull/7/head"
    ) >/dev/null 2>&1
    pr_head_sha=$(cat "$tmp/pr-head-sha")
    fetch_head_sha=$(cat "$clone_dir/fetch-head-sha")
    unreachable_head_sha=0123456789abcdef0123456789abcdef01234567

    prs_dir=$(mktemp -d)
    printf '[{"number":1,"headRefOid":"%s"}]' "$pr_head_sha" >"$prs_dir/merged-ok"
    printf '[{"number":1,"headRefOid":"%s"}]' "$pr_head_sha" >"$prs_dir/one-past"
    printf '[{"number":98,"headRefOid":"%s"}]' "$pr_head_sha" >"$prs_dir/behind-local"
    printf '[{"number":7,"headRefOid":"%s"}]' "$fetch_head_sha" >"$prs_dir/behind-fetch"
    printf '[{"number":99,"headRefOid":"%s"}]' "$unreachable_head_sha" >"$prs_dir/unfetchable"
    printf '[{"number":1,"headRefOid":"%s"}]' "$pr_head_sha" >"$prs_dir/diverged"
    printf '[{"number":1,"headRefOid":"%s"},{"number":99,"headRefOid":"%s"}]' \
        "$pr_head_sha" "$unreachable_head_sha" >"$prs_dir/two-pr"

    stub_dir=$(mktemp -d)
    cat >"$stub_dir/gh" <<STUB
#!/bin/sh
state_ok=0
head_branch=""
prev=""
for a in "\$@"; do
    if [ "\$prev" = "--state" ] && [ "\$a" = "merged" ]; then state_ok=1; fi
    if [ "\$prev" = "--head" ]; then head_branch=\$a; fi
    prev=\$a
done
if [ "\$state_ok" -eq 1 ] && [ -n "\$head_branch" ]; then
    cat "$prs_dir/\$head_branch" 2>/dev/null || printf '[]'
else
    printf '[]'
fi
STUB
    chmod +x "$stub_dir/gh"

    fail_stub_dir=$(mktemp -d)
    cat >"$fail_stub_dir/gh" <<'STUB'
#!/bin/sh
exit 1
STUB
    chmod +x "$fail_stub_dir/gh"

    empty_stub_dir=$(mktemp -d)
    cat >"$empty_stub_dir/gh" <<'STUB'
#!/bin/sh
printf '[]'
STUB
    chmod +x "$empty_stub_dir/gh"

    minimal_bin=$(mktemp -d)
    for t in sh git jq sed grep tr; do
        ln -s "$(command -v "$t")" "$minimal_bin/$t"
    done

    orig_path=$PATH
    export PATH="$stub_dir:$orig_path"
    expect_allow "$repo_script" "$label" "tip equals merged PR head"       "git -C $tmp branch -D merged-ok"
    expect_block "$repo_script" "$label" "tip one commit past merged head" "git -C $tmp branch -D one-past"
    expect_allow "$repo_script" "$label" "tip is ancestor of merged PR head, head present locally" \
        "git -C $tmp branch -D behind-local"
    expect_allow "$repo_script" "$label" "tip is ancestor of merged PR head, head must be fetched" \
        "git -C $tmp branch -D behind-fetch"
    expect_block_reason "$repo_script" "$label" "merged PR head cannot be fetched" "could not fetch" \
        "git -C $tmp branch -D unfetchable"
    expect_block_reason "$repo_script" "$label" "tip diverged from merged PR head" "not an ancestor" \
        "git -C $tmp branch -D diverged"
    expect_allow "$repo_script" "$label" \
        "ancestor check short-circuits before an unrelated later PR entry" \
        "git -C $tmp branch -D two-pr"
    expect_allow "$repo_script" "$label" "trailing redirect and pipe are not branch names" \
        "git -C $tmp branch -D merged-ok 2>&1 | tail -3"

    export PATH="$minimal_bin"
    expect_block_reason "$repo_script" "$label" "no gh on PATH" "no gh on PATH" \
        "git -C $tmp branch -D merged-ok"

    export PATH="$fail_stub_dir:$orig_path"
    expect_block_reason "$repo_script" "$label" "gh exits non-zero" "gh failed" \
        "git -C $tmp branch -D merged-ok"

    export PATH="$empty_stub_dir:$orig_path"
    expect_block_reason "$repo_script" "$label" "gh reports no merged PR" "no merged PR" \
        "git -C $tmp branch -D merged-ok"

    export PATH="$orig_path"

    expect_allow "$repo_script" "$label" "quoted text mentioning it is not a real invocation" \
        'echo "see: git branch -D old-branch for cleanup"'
    expect_allow "$repo_script" "$label" "heredoc body inside a quoted substitution is not a real invocation" \
        "git commit -m \"\$(cat <<'EOF'
git branch -D old-branch
EOF
)\""
}

run_delete_branch_head_cases

if [ -f "$home_script" ]; then
    run_case_table "$home_script" "installed"
else
    echo "installed $home_script not found — skipping the live-copy pass" >&2
fi

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
