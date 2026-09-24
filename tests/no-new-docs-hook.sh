#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

dir="$(cd "$(dirname "$0")/.." && pwd)"
rev=$(git -C "$dir" rev-parse HEAD)
consumer=$(mktemp -d)

fail() {
    echo "FAIL: $1" >&2
    shift
    [ $# -gt 0 ] && printf '%s\n' "$@" >&2
    rm -rf "$consumer"
    exit 1
}

cgit() {
    git -C "$consumer" -c user.email=sentinel -c user.name=sentinel "$@"
}

git -C "$consumer" init -q -b main
printf 'test_paths = ["tests"]\n' > "$consumer/.mutation-gate.toml"
cgit add .mutation-gate.toml
cgit commit -q -m init

cgit checkout -q -b design-doc main
: > "$consumer/design.md"
cgit add design.md
cgit commit -q -m "add design.md"
set +e
range_out=$(cd "$consumer" && mutation-gate no-new-docs --range "main..HEAD" 2>&1)
range_code=$?
set -e
[ "$range_code" -eq 1 ] || fail "--range should block a newly added design.md (got $range_code)" "$range_out"
printf '%s' "$range_out" | grep -qF "design.md" || fail "--range block did not name design.md" "$range_out"

cgit checkout -q -b add-readme main
: > "$consumer/README.md"
cgit add README.md
cgit commit -q -m "add readme"
(cd "$consumer" && mutation-gate no-new-docs --range "main..HEAD") \
    || fail "--range should pass a newly added README.md"

cgit checkout -q -b nested-readme main
mkdir -p "$consumer/pkg"
: > "$consumer/pkg/README.md"
cgit add pkg/README.md
cgit commit -q -m "add pkg/README.md"
(cd "$consumer" && mutation-gate no-new-docs --range "main..HEAD") \
    || fail "--range should pass a newly added pkg/README.md (any depth)"

cgit checkout -q -b nested-design main
mkdir -p "$consumer/pkg"
: > "$consumer/pkg/design.md"
cgit add pkg/design.md
cgit commit -q -m "add pkg/design.md"
set +e
nested_out=$(cd "$consumer" && mutation-gate no-new-docs --range "main..HEAD" 2>&1)
nested_code=$?
set -e
[ "$nested_code" -eq 1 ] || fail "--range should block a newly added pkg/design.md (got $nested_code)" "$nested_out"
printf '%s' "$nested_out" | grep -qF "pkg/design.md" || fail "--range block did not name pkg/design.md" "$nested_out"

cgit checkout -q -b add-github-doc main
mkdir -p "$consumer/.github"
: > "$consumer/.github/x.md"
cgit add .github/x.md
cgit commit -q -m "add .github/x.md"
(cd "$consumer" && mutation-gate no-new-docs --range "main..HEAD") \
    || fail "--range should pass a newly added .github/x.md"

cgit checkout -q -b add-docs-doc main
mkdir -p "$consumer/docs"
: > "$consumer/docs/y.md"
cgit add docs/y.md
cgit commit -q -m "add docs/y.md"
set +e
docs_out=$(cd "$consumer" && mutation-gate no-new-docs --range "main..HEAD" 2>&1)
docs_code=$?
set -e
[ "$docs_code" -eq 1 ] || fail "--range should block docs/y.md with no doc_allow entry (got $docs_code)" "$docs_out"

printf '\n[[doc_allow]]\nglob = "docs/**/*"\nreason = "design notes"\n' >> "$consumer/.mutation-gate.toml"
(cd "$consumer" && mutation-gate no-new-docs --range "main..HEAD") \
    || fail "--range should pass docs/y.md once doc_allow carries a reason"

printf '\n[[doc_allow]]\nglob = "skills/**/*"\n' >> "$consumer/.mutation-gate.toml"
set +e
noreason_out=$(cd "$consumer" && mutation-gate no-new-docs --range "main..HEAD" 2>&1)
noreason_code=$?
set -e
[ "$noreason_code" -eq 2 ] || fail "a doc_allow entry without a reason should refuse loudly (got $noreason_code)" "$noreason_out"
printf '%s' "$noreason_out" | grep -qiF "reason" || fail "the refusal did not name the missing reason" "$noreason_out"

cat > "$consumer/.pre-commit-config.yaml" <<YAML
repos:
  - repo: $dir
    rev: $rev
    hooks:
      - id: no-new-docs
YAML
(cd "$consumer" && pre-commit install >/dev/null)

cgit checkout -q -b hooked main
: > "$consumer/README.md"
cgit add README.md
cgit commit -q -m "add readme" || fail "the hook should allow adding README.md"

: > "$consumer/design2.md"
cgit add design2.md
set +e
hook_out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit -q -m "add design2.md" 2>&1)
hook_code=$?
set -e
[ "$hook_code" -ne 0 ] || fail "the hook should reject a commit adding design2.md"
printf '%s' "$hook_out" | grep -qF "design2.md" || fail "the hook rejection did not name design2.md" "$hook_out"
cgit reset -q --hard HEAD

echo "more text" >> "$consumer/README.md"
cgit add README.md
cgit commit -q -m "edit readme" || fail "the hook should allow editing an existing README.md"

rm -rf "$consumer"
echo "all cases passed"
