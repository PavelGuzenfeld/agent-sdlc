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
cgit add .mutation-gate.toml
cgit commit -q -m init

name=$(printf 'caf\351.py')
cat > "$consumer/$name" <<'PY'
def f(x):
    return x <= 1
PY
cgit add -- "$name"

set +e
out=$(cd "$consumer" && mutation-gate --staged --dry-run 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] || fail "dry-run should pass, got exit $code" "$out"

printf '%s\n' "$out" | grep -q 'panicked' \
    && fail "ast-grep panicked on the Latin-1-named file's argv" "$out"

printf '%s\n' "$out" | grep -qE '[1-9][0-9]* mutant\(s\)' \
    || fail "dry-run generated zero mutants for the Latin-1-named file" "$out"

rm -rf "$consumer"
echo "all cases passed"
