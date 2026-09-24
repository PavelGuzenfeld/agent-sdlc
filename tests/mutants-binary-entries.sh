#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

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
printf '*.py -diff\n' > "$consumer/.gitattributes"
cgit add .mutation-gate.toml .gitattributes
cat > "$consumer/a.py" <<'PY'
def f(x):
    return x
PY
cgit add a.py
cgit commit -q -m init

cat >> "$consumer/a.py" <<'PY'

def g(y):
    return y <= 1
PY
cgit add a.py

cgit diff --cached -U0 --no-color -- a.py | grep -q '^Binary files' \
    || fail "setup: staged diff for a.py did not present as binary — test no longer reproduces #234"

set +e
out=$(cd "$consumer" && mutation-gate --staged --dry-run 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] || fail "dry-run should pass, got exit $code" "$out"

printf '%s\n' "$out" | grep -qE '^a\.py: .* [1-9][0-9]* mutant\(s\)' \
    || fail "dry-run generated zero mutants for a.py marked -diff in .gitattributes — #234 regressed" "$out"

rm -rf "$consumer"
echo "all cases passed"
