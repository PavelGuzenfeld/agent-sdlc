#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

dir="$(cd "$(dirname "$0")/.." && pwd)"
rev=$(git -C "$dir" rev-parse HEAD)

main=$(mktemp -d)
git clone -q --no-checkout "$dir" "$main"
git -C "$main" checkout -q "$rev"

worktrees=$(mktemp -d)
wt="$worktrees/wt"
git -C "$main" worktree add -q -b "worktree-shim-slice-$$" "$wt" "$rev"

sentinel="WORKTREE-OWN-CODE-127-$$"
python3 - "$wt/mutation_gate/cli.py" "$sentinel" <<'PY'
import sys
path, sentinel = sys.argv[1], sys.argv[2]
text = open(path).read()
marker = "argv = sys.argv[1:] if argv is None else argv\n"
if text.count(marker) != 1:
    raise SystemExit(f"expected exactly one marker, found {text.count(marker)}")
text = text.replace(marker, marker + f'    print("{sentinel}")\n    return 0\n', 1)
open(path, "w").write(text)
PY
git -C "$wt" add mutation_gate/cli.py
git -C "$wt" -c user.email=sentinel -c user.name=sentinel commit -q -m "worktree-only patch for the slice test"

PATH="$main/bin:$PATH"
export PATH

msgfile=$(mktemp)
echo "fix a thing" > "$msgfile"

failures=0

check_hook() {
    id="$1"
    shift
    set +e
    out=$(cd "$wt" && pre-commit run --verbose "$@" "$id" 2>&1)
    code=$?
    set -e
    if [ "$code" -ne 0 ]; then
        echo "FAIL: $id did not pass" >&2
        printf '%s\n' "$out" >&2
        failures=$((failures + 1))
        return
    fi
    if ! printf '%s' "$out" | grep -qF "$sentinel"; then
        echo "FAIL: $id ran code other than the worktree's own" >&2
        printf '%s\n' "$out" >&2
        failures=$((failures + 1))
    fi
}

check_hook rules-check --all-files
check_hook mutation-gate --all-files
check_hook no-new-docs --all-files
check_hook commit-msg --hook-stage commit-msg --commit-msg-filename "$msgfile"
check_hook diff-discipline --hook-stage commit-msg --commit-msg-filename "$msgfile"

rm -f "$msgfile"
git -C "$main" worktree remove -f "$wt" >/dev/null 2>&1 || true
rm -rf "$main" "$worktrees"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
