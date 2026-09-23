#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

dir="$(cd "$(dirname "$0")/.." && pwd)"
rev=$(git -C "$dir" rev-parse HEAD)
consumer=$(mktemp -d)

git -C "$consumer" init -q
git -C "$consumer" -c user.email=sentinel -c user.name=sentinel commit --allow-empty -q -m init

: > "$consumer/.mutation-gate.toml"
cat > "$consumer/.pre-commit-config.yaml" <<YAML
repos:
  - repo: $dir
    rev: $rev
    hooks:
      - id: rules-check
YAML
git -C "$consumer" add .mutation-gate.toml .pre-commit-config.yaml

(cd "$consumer" && mutation-gate rules sync)
git -C "$consumer" add .claude/rules

if ! (cd "$consumer" && pre-commit run rules-check --all-files); then
    echo "FAIL: rules-check should pass right after sync" >&2
    rm -rf "$consumer"
    exit 1
fi

edited=$(find "$consumer/.claude/rules" -name '*.md' | sort | head -n 1)
name=$(basename "$edited")
printf 'x' >> "$edited"

set +e
out=$(cd "$consumer" && pre-commit run rules-check --all-files 2>&1)
code=$?
set -e

if [ "$code" -eq 0 ]; then
    echo "FAIL: rules-check should fail after editing a synced rule" >&2
    rm -rf "$consumer"
    exit 1
fi
if ! printf '%s' "$out" | grep -qF ".claude/rules/$name: differs from the packaged rule"; then
    echo "FAIL: rules-check failure did not name the edited rule ($name)" >&2
    printf '%s\n' "$out" >&2
    rm -rf "$consumer"
    exit 1
fi

(cd "$consumer" && mutation-gate rules sync)
agents="$consumer/AGENTS.md"
sed -i 's/<!-- BEGIN mutation-gate rules -->/<!-- BEGIN mutation-gate rules -->x/' "$agents"

set +e
out=$(cd "$consumer" && pre-commit run rules-check --all-files 2>&1)
code=$?
set -e

if [ "$code" -eq 0 ]; then
    echo "FAIL: rules-check should fail after editing the AGENTS.md block" >&2
    rm -rf "$consumer"
    exit 1
fi
if ! printf '%s' "$out" | grep -qF "AGENTS.md: rules block differs from the packaged rules"; then
    echo "FAIL: rules-check failure did not name AGENTS.md" >&2
    printf '%s\n' "$out" >&2
    rm -rf "$consumer"
    exit 1
fi

rm -rf "$consumer"
echo "all cases passed"
