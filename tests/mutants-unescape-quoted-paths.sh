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

cat > "$consumer/café.py" <<'PY'
def f(x):
    return x <= 1
PY
cgit add -- café.py

set +e
out=$(cd "$consumer" && mutation-gate --staged --dry-run 2>&1)
code=$?
set -e
[ "$code" -eq 0 ] || fail "dry-run should pass, got exit $code" "$out"

printf '%s\n' "$out" | grep -q '^café\.py: ' \
    || fail "dry-run did not label the finding with café.py's real name" "$out"

printf '%s\n' "$out" | grep -q 'caf\\303\\251' \
    && fail "dry-run leaked git's C-style octal escape instead of the real name" "$out"

printf '%s\n' "$out" | grep -qE '^café\.py: .* [1-9][0-9]* mutant\(s\)' \
    || fail "dry-run generated zero mutants for café.py — the file was silently skipped" "$out"

rm -rf "$consumer"
echo "all cases passed"
