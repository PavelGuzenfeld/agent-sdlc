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
cat > "$consumer/a.py" <<'PY'
def f(x):
    return x
PY
cgit add a.py
cgit commit -q -m init

check_gated() {
    label=$1
    cat >> "$consumer/a.py" <<'PY'

def g(y):
    return y <= 1
PY
    cgit add a.py
    set +e
    out=$(cd "$consumer" && mutation-gate --staged --dry-run 2>&1)
    code=$?
    set -e
    [ "$code" -eq 0 ] || fail "$label: dry-run should pass, got exit $code" "$out"
    printf '%s' "$out" | grep -q "^a.py: " \
        || fail "$label: dry-run silently dropped a.py's changed lines" "$out"
    cgit reset -q --hard HEAD
}

cgit config diff.noprefix true
check_gated "diff.noprefix"
cgit config --unset diff.noprefix

cgit config diff.mnemonicPrefix true
check_gated "diff.mnemonicPrefix"
cgit config --unset diff.mnemonicPrefix

rm -rf "$consumer"
echo "all cases passed"
