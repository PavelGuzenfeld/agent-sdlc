#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
failures=0

fail() {
    echo "FAIL: $1" >&2
    failures=$((failures + 1))
}

required_ids() {
    awk '/^    id: /{id=$2} /required: true/{print id}' "$dir/.github/ISSUE_TEMPLATE/$1.yml" | tr '\n' ' '
}

[ "$(required_ids bug)" = "what-happened repro expected-actual ref " ] \
    || fail "bug form required fields are '$(required_ids bug)'"
[ "$(required_ids feature)" = "outcome why " ] \
    || fail "feature form required fields are '$(required_ids feature)'"
grep -q '^    id: code-context$' "$dir/.github/ISSUE_TEMPLATE/feature.yml" \
    || fail "feature form has no code-context field"
for doc in done grill; do
    grep -q 'Ref: <branch-or-tag>@<sha>' "$dir/commands/$doc.md" \
        || fail "commands/$doc.md does not file tickets with a Ref line"
done

scratch=$(mktemp -d)
mkdir "$scratch/bin"
cat > "$scratch/bin/gh" <<'SH'
#!/usr/bin/env sh
case "$1 $2" in
"label list") ;;
"repo view") [ -n "$STUB_SLUG" ] && echo "$STUB_SLUG" ;;
esac
SH
chmod +x "$scratch/bin/gh"
PATH="$scratch/bin:$PATH"
export PATH

fresh_repo() {
    rm -rf "$scratch/repo"
    mkdir "$scratch/repo"
    git -C "$scratch/repo" init -q
}

run_bootstrap() {
    (cd "$scratch/repo/${1:-.}" && STUB_SLUG="${2-acme/widgets}" sh "$dir/bin/sdlc-bootstrap" > "$scratch/out" 2>&1)
}

templates=".github/ISSUE_TEMPLATE/bug.yml .github/ISSUE_TEMPLATE/feature.yml .github/pull_request_template.md"

fresh_repo
mkdir "$scratch/repo/sub"
run_bootstrap sub || fail "bootstrap exited non-zero in a bare repo"
for file in $templates; do
    cmp -s "$dir/$file" "$scratch/repo/$file" || fail "$file not written byte-identical at the git toplevel"
    grep -q -x "wrote $file" "$scratch/out" || fail "$file not listed on stdout"
done
sed 's#PavelGuzenfeld/agent-sdlc#acme/widgets#' "$dir/.github/ISSUE_TEMPLATE/config.yml" > "$scratch/want-config"
cmp -s "$scratch/want-config" "$scratch/repo/.github/ISSUE_TEMPLATE/config.yml" \
    || fail "config.yml not written with the target slug"
grep -q 'acme/widgets/discussions' "$scratch/repo/.github/ISSUE_TEMPLATE/config.yml" \
    || fail "config.yml discussions url not rewritten"
[ -z "$(git -C "$scratch/repo" log --oneline 2>/dev/null)" ] || fail "bootstrap committed"

printf 'mine\n' > "$scratch/repo/.github/pull_request_template.md"
run_bootstrap || fail "rerun exited non-zero"
[ "$(cat "$scratch/repo/.github/pull_request_template.md")" = mine ] || fail "existing file overwritten"
grep -q -x 'skipped .github/pull_request_template.md (repo has its own template)' "$scratch/out" \
    || fail "existing file not reported as skipped"

fresh_repo
run_bootstrap . "" || fail "failed lookup made the script exit non-zero"
[ ! -e "$scratch/repo/.github/ISSUE_TEMPLATE/config.yml" ] || fail "config.yml written without a target slug"
grep -q -x 'skipped .github/ISSUE_TEMPLATE/config.yml (repo lookup failed)' "$scratch/out" \
    || fail "config.yml skip not reported"
cmp -s "$dir/.github/pull_request_template.md" "$scratch/repo/.github/pull_request_template.md" \
    || fail "other templates not written when lookup fails"

fresh_repo
mkdir -p "$scratch/repo/.github/ISSUE_TEMPLATE"
printf 'old\n' > "$scratch/repo/.github/ISSUE_TEMPLATE/bug_report.md"
run_bootstrap || fail "own-template run exited non-zero"
[ "$(ls "$scratch/repo/.github/ISSUE_TEMPLATE")" = bug_report.md ] || fail "issue forms written beside the repo's own template"
grep -q -x 'skipped .github/ISSUE_TEMPLATE (repo has its own templates)' "$scratch/out" \
    || fail "own issue templates not reported as skipped"

for existing in pull_request_template.md docs/PULL_REQUEST_TEMPLATE.md docs/PULL_REQUEST_TEMPLATE/team.md .github/PULL_REQUEST_TEMPLATE/team.md PULL_REQUEST_TEMPLATE.md; do
    fresh_repo
    mkdir -p "$scratch/repo/$(dirname "$existing")"
    printf 'old\n' > "$scratch/repo/$existing"
    run_bootstrap || fail "run exited non-zero beside $existing"
    [ ! -e "$scratch/repo/.github/pull_request_template.md" ] || fail "PR template written beside $existing"
    grep -q -x 'skipped .github/pull_request_template.md (repo has its own template)' "$scratch/out" \
        || fail "PR template skip not reported beside $existing"
    [ -e "$scratch/repo/.github/ISSUE_TEMPLATE/bug.yml" ] || fail "issue forms skipped because of $existing"
done

(cd "$dir" && STUB_SLUG=acme/widgets sh bin/sdlc-bootstrap > "$scratch/out" 2>&1)
! grep -q '^wrote ' "$scratch/out" || fail "bootstrap in the pack itself wrote files"
[ -z "$(git -C "$dir" status --porcelain .github/ISSUE_TEMPLATE .github/pull_request_template.md)" ] || fail "bootstrap in the pack changed .github"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
