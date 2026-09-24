#!/usr/bin/env sh
set -eu

cmd=$(jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

cmd_unquoted=$(printf '%s' "$cmd" | tr '\n' ';' | sed -E -e 's/"[^"]*"/Q/g' -e "s/'[^']*'/Q/g")

deny() {
    echo "git-guardrail: blocks $1" >&2
    echo "  $2" >&2
    echo "  run it yourself with: ! git ..." >&2
    exit 2
}

check_delete_branch_head() {
    b="$1"
    path="$2"
    (
        if [ -n "$path" ]; then
            cd -- "$path" 2>/dev/null || { printf 'branch path not found: %s' "$path"; exit 1; }
        fi
        command -v gh >/dev/null 2>&1 || { printf 'no gh on PATH to verify %s' "$b"; exit 1; }
        tip=$(git rev-parse --verify --quiet "refs/heads/$b" 2>/dev/null) || tip=""
        [ -n "$tip" ] || { printf 'no local branch %s' "$b"; exit 1; }
        gh_status=0
        json=$(gh pr list --head "$b" --state merged --json number,headRefOid 2>/dev/null) || gh_status=$?
        [ "$gh_status" -eq 0 ] || { printf 'gh failed listing merged PRs for %s' "$b"; exit 1; }
        count=$(printf '%s' "$json" | jq 'length' 2>/dev/null) || count=""
        [ "$count" != "0" ] && [ -n "$count" ] || { printf 'no merged PR found for %s' "$b"; exit 1; }
        printf '%s' "$json" | jq -e --arg t "$tip" 'any(.[]; .headRefOid == $t)' >/dev/null 2>&1 && exit 0
        for pr in $(printf '%s' "$json" | jq -r '.[] | "\(.number):\(.headRefOid)"'); do
            pr_head=${pr#*:}
            pr_number=${pr%%:*}
            git cat-file -e "${pr_head}^{commit}" 2>/dev/null \
                || git fetch --quiet origin "pull/$pr_number/head" 2>/dev/null \
                || { printf 'could not fetch pull/%s/head for %s' "$pr_number" "$b"; exit 1; }
            git merge-base --is-ancestor "$tip" "$pr_head" 2>/dev/null && exit 0
        done
        printf '%s tip is not an ancestor of its merged PR head' "$b"
        exit 1
    )
}

parse_delete_targets() {
    D_PATH=""
    D_BRANCHES=""
    D_OK=1
    D_HAS_D=0
    seen_branch=0
    dashdash=0
    skip_path=0
    skip_redirect_target=0
    for tok in "$@"; do
        if [ "$skip_path" -eq 1 ]; then
            D_PATH=$tok
            skip_path=0
            continue
        fi
        if [ "$skip_redirect_target" -eq 1 ]; then
            skip_redirect_target=0
            continue
        fi
        redirect_rest=$(printf '%s' "$tok" | sed -E 's/^[0-9]*(>>|>|<<|<)//')
        if [ "$redirect_rest" != "$tok" ]; then
            [ -n "$redirect_rest" ] || skip_redirect_target=1
            continue
        fi
        case "$tok" in
            git) ;;
            branch) seen_branch=1 ;;
            -C)
                if [ "$seen_branch" -eq 0 ]; then
                    skip_path=1
                else
                    D_OK=0
                fi
                ;;
            -D) D_HAS_D=1 ;;
            --delete|-f|--force) ;;
            --) dashdash=1 ;;
            -*)
                if [ "$dashdash" -eq 1 ]; then
                    D_BRANCHES="$D_BRANCHES $tok"
                else
                    D_OK=0
                fi
                ;;
            *)
                D_BRANCHES="$D_BRANCHES $tok"
                ;;
        esac
    done
}

branch_segments=$(printf '%s' "$cmd_unquoted" | grep -Eo -- 'git[[:space:]]+(-C[[:space:]]+[^;&|[:space:]]+[[:space:]]+)?branch[^;&|]*' 2>/dev/null || true)
delete_ok=1
delete_reason=""
old_ifs=$IFS
IFS='
'
for seg in $branch_segments; do
    IFS=$old_ifs
    parse_delete_targets $seg
    if [ "$D_HAS_D" -eq 1 ]; then
        if [ "$D_OK" -eq 0 ] || [ -z "$D_BRANCHES" ]; then
            delete_ok=0
            delete_reason="unparseable git branch -D invocation"
        else
            for b in $D_BRANCHES; do
                check_status=0
                check_reason=$(check_delete_branch_head "$b" "$D_PATH") || check_status=$?
                if [ "$check_status" -ne 0 ]; then
                    delete_ok=0
                    delete_reason="$check_reason"
                fi
            done
        fi
    fi
    IFS='
'
done
IFS=$old_ifs
if [ "$delete_ok" -eq 0 ]; then
    deny "git branch -D" "git safety protocol: never delete a branch with -D without explicit request ($delete_reason)"
fi

if printf '%s' "$cmd" | grep -Eq -- 'git[[:space:]]+push'; then
    push_segment=$(printf '%s' "$cmd_unquoted" | grep -Eo -- 'git[[:space:]]+push[^;&|]*' | head -n1)
    push_segment=$(printf '%s' "$push_segment" | sed 's/--force-with-lease//g')
    if printf '%s' "$push_segment" | grep -Eq -- '(^|[[:space:]])(--force|-f)([[:space:]]|$)'; then
        deny "force-push without --force-with-lease" \
            "memory: feedback_no_force_push_shared_branches (flowdiff #18 squash-clobber, 2026-09-11)"
    fi
    if printf '%s' "$push_segment" | grep -Eq -- '[[:space:]]\+[[:alnum:]_./-]'; then
        deny "force-push via + refspec" \
            "memory: feedback_no_force_push_shared_branches (flowdiff #18 squash-clobber, 2026-09-11)"
    fi
fi

if printf '%s' "$cmd" | grep -Eq -- 'git[[:space:]]+reset[[:space:]]+--hard([[:space:]]|$)'; then
    deny "git reset --hard" "git safety protocol: never reset --hard without explicit request"
fi

if printf '%s' "$cmd" | grep -Eq -- 'git[[:space:]]+clean[[:space:]]+-[a-zA-Z]*f'; then
    deny "git clean -f*" "git safety protocol: never clean -f* without explicit request"
fi

if printf '%s' "$cmd" | grep -Eq -- 'git[[:space:]]+(checkout[[:space:]]+(--[[:space:]]+)?|restore[[:space:]]+)\.([[:space:]]|$)'; then
    deny "git checkout . / checkout -- . / restore ." \
        "git safety protocol: never discard uncommitted changes without explicit request"
fi

if printf '%s' "$cmd" | grep -Eq -- 'git[[:space:]]+add[[:space:]]+(-A|--all|\.)([[:space:]]|$)'; then
    deny "git add -A / add . / add --all" \
        "memory: feedback_never_add_dash_a_across_branches (uncommitted edits ride along across branches)"
fi

exit 0
