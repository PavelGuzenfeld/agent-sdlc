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
    cat "$STUB_EXISTING"
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

grep -q -x 'label create model:fable --color 5319E7 --description run with Fable' "$STUB_CALLS" \
    || fail "model:fable not created with its colour and description"

printf '%s\n' $all_labels > "$STUB_EXISTING"
run_bootstrap || fail "rerun exited non-zero"
[ ! -s "$STUB_CALLS" ] || fail "rerun created labels that already exist: $(created)"

: > "$STUB_EXISTING"
run_bootstrap model:opus || fail "refused create made the script exit non-zero"
[ "$(wc -l < "$STUB_CALLS")" -eq 13 ] || fail "script stopped after the refused create"
grep -q 'model:opus' "$scratch/out" || fail "refused label not reported"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
