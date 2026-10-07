#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
failures=0

fail() {
    echo "FAIL: $1" >&2
    failures=$((failures + 1))
}

scratch=$(mktemp -d)
mkdir "$scratch/bin"
cat > "$scratch/bin/gh" <<'SH'
#!/usr/bin/env sh
case "$1 $2" in
"label list")
    limit=30
    [ "${3:-}" = "--limit" ] && limit="$4"
    head -n "$limit" "$STUB_EXISTING"
    ;;
"label create")
    echo "$*" >> "$STUB_CALLS"
    [ "$3" != "$STUB_REFUSE" ]
    ;;
esac
SH
chmod +x "$scratch/bin/gh"
PATH="$scratch/bin:$PATH"
export PATH
export STUB_EXISTING="$scratch/existing" STUB_CALLS="$scratch/calls"

all_labels="model:haiku model:sonnet model:opus model:fable follow-up correctness clarity security performance scope size:tiny bug enhancement"

run_bootstrap() {
    : > "$STUB_CALLS"
    STUB_REFUSE="${1:-}" sh "$dir/bin/sdlc-bootstrap" > "$scratch/out" 2>&1
}

created() {
    awk '{print $3}' "$STUB_CALLS" | sort | tr '\n' ' '
}

printf '%s\n' model:sonnet bug > "$STUB_EXISTING"
run_bootstrap || fail "bootstrap exited non-zero when every create succeeds"
expected=$(printf '%s\n' $all_labels | grep -v -x -e model:sonnet -e bug | sort | tr '\n' ' ')
[ "$(created)" = "$expected" ] || fail "created '$(created)', wanted only the missing labels '$expected'"

: > "$STUB_EXISTING"
run_bootstrap || fail "fresh-repo run exited non-zero"
sort "$STUB_CALLS" > "$scratch/calls.sorted"
sort > "$scratch/calls.expected" <<'CALLS'
label create model:haiku --color 006B75 --description run with Haiku
label create model:sonnet --color 1D76DB --description run with Sonnet
label create model:opus --color FEF2C0 --description run with Opus
label create model:fable --color 5319E7 --description run with Fable
label create follow-up --color FBCA04 --description noticed during another ticket, not yet triaged
label create correctness --color FEF2C0 --description follow-up category: correctness
label create clarity --color C5DEF5 --description follow-up category: clarity
label create security --color C5DEF5 --description follow-up category: security
label create performance --color D93F0B --description follow-up category: performance
label create scope --color D93F0B --description follow-up category: scope, deferred with nothing broken
label create size:tiny --color 006B75 --description one location, no design choice, no new file
label create bug --color d73a4a --description Something isn't working
label create enhancement --color C5DEF5 --description Feature request from the issue form
CALLS
cmp -s "$scratch/calls.sorted" "$scratch/calls.expected" \
    || fail "label colours or descriptions differ from the ones every repo shares"

printf '%s\n' $all_labels > "$STUB_EXISTING"
run_bootstrap || fail "rerun exited non-zero"
[ ! -s "$STUB_CALLS" ] || fail "rerun created labels that already exist: $(created)"

: > "$STUB_EXISTING"
run_bootstrap model:opus || fail "refused create made the script exit non-zero"
[ "$(wc -l < "$STUB_CALLS")" -eq 13 ] || fail "script stopped after the refused create"
grep -q 'model:opus' "$scratch/out" || fail "refused label not reported"

: > "$STUB_EXISTING"
: > "$STUB_CALLS"
STUB_REFUSE=enhancement sh "$dir/bin/sdlc-bootstrap" > "$scratch/stdout" 2> "$scratch/stderr" \
    || fail "refusing the last label made the script exit non-zero"
grep -q 'could not create label enhancement' "$scratch/stderr" || fail "refused label not reported on stderr"
! grep -q 'could not create label' "$scratch/stdout" || fail "refused label reported on stdout"

printf '%s\n' bugfix model:sonnet-old > "$STUB_EXISTING"
run_bootstrap || fail "substring run exited non-zero"
grep -q ' bug --color' "$STUB_CALLS" || fail "bug skipped because bugfix contains it"
grep -q ' model:sonnet --color' "$STUB_CALLS" || fail "model:sonnet skipped because model:sonnet-old contains it"

{
    seq 1 40 | sed 's/^/filler-/'
    echo scope
} > "$STUB_EXISTING"
run_bootstrap || fail "long-list run exited non-zero"
! grep -q ' scope --color' "$STUB_CALLS" || fail "scope recreated though it sits past the default page of 30"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
