#!/usr/bin/env sh
set -eu

cmd=$(jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

deny() {
    echo "git-guardrail: blocks $1" >&2
    echo "  $2" >&2
    echo "  run it yourself with: ! git ..." >&2
    exit 2
}

if printf '%s' "$cmd" | grep -Eq -- 'git[[:space:]]+push'; then
    cmd_unquoted=$(printf '%s' "$cmd" | sed -E -e 's/"[^"]*"/Q/g' -e "s/'[^']*'/Q/g")
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

if printf '%s' "$cmd" | grep -Eq -- 'git[[:space:]]+branch[[:space:]]+-D([[:space:]]|$)'; then
    deny "git branch -D" "git safety protocol: never delete a branch with -D without explicit request"
fi

exit 0
