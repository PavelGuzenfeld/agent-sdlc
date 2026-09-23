#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

dir="$(cd "$(dirname "$0")/.." && pwd)"
rev=$(git -C "$dir" rev-parse HEAD)
consumer=$(mktemp -d)

git -C "$consumer" init -q
git -C "$consumer" -c user.email=sentinel -c user.name=sentinel commit --allow-empty -q -m init

git -C "$consumer" -c user.email=sentinel -c user.name=sentinel commit --allow-empty -q -m "we should leverage this"
bad_sha=$(git -C "$consumer" rev-parse HEAD | cut -c1-12)
git -C "$consumer" -c user.email=sentinel -c user.name=sentinel commit --allow-empty -q -m "fix a plain thing"
clean_sha=$(git -C "$consumer" rev-parse HEAD | cut -c1-12)

set +e
range_out=$(cd "$consumer" && mutation-gate commit-msg --range "HEAD~2..HEAD" 2>&1)
range_code=$?
set -e
if [ "$range_code" -ne 1 ]; then
    echo "FAIL: commit-msg --range should block on the leverage commit (got $range_code)" >&2
    rm -rf "$consumer"
    exit 1
fi
if ! printf '%s' "$range_out" | grep -qF "$bad_sha"; then
    echo "FAIL: commit-msg --range did not name the offending commit" >&2
    printf '%s\n' "$range_out" >&2
    rm -rf "$consumer"
    exit 1
fi
if printf '%s' "$range_out" | grep -qF "$clean_sha"; then
    echo "FAIL: commit-msg --range named the clean commit" >&2
    printf '%s\n' "$range_out" >&2
    rm -rf "$consumer"
    exit 1
fi

cat > "$consumer/.pre-commit-config.yaml" <<YAML
repos:
  - repo: $dir
    rev: $rev
    hooks:
      - id: commit-msg
YAML

(cd "$consumer" && pre-commit install --hook-type commit-msg >/dev/null)

check_rejected() {
    label=$1
    message=$2
    needle=$3
    set +e
    out=$(cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit --allow-empty -q -m "$message" 2>&1)
    code=$?
    set -e
    if [ "$code" -eq 0 ]; then
        echo "FAIL: commit-msg should reject $label" >&2
        rm -rf "$consumer"
        exit 1
    fi
    if ! printf '%s' "$out" | grep -qF "$needle"; then
        echo "FAIL: commit-msg rejection of $label did not name the reason" >&2
        printf '%s\n' "$out" >&2
        rm -rf "$consumer"
        exit 1
    fi
}

check_rejected "a banned word (leverage)" \
    "we should leverage this" \
    'banned word "leverage"'
check_rejected "an AI Co-Authored-By trailer" \
    "$(printf 'fix a thing\n\nCo-Authored-By: Claude <noreply%santhropic.com>' '@')" \
    'Co-Authored-By names an AI'
check_rejected "a Signed-off-by trailer" \
    "$(printf 'fix a thing\n\nSigned-off-by: Someone <someone%sexample.com>' '@')" \
    'Signed-off-by trailer is not allowed'

if ! (cd "$consumer" && git -c user.email=sentinel -c user.name=sentinel commit --allow-empty -q -m "fix a plain thing"); then
    echo "FAIL: commit-msg should accept a plain message" >&2
    rm -rf "$consumer"
    exit 1
fi

rm -rf "$consumer"
echo "all cases passed"
