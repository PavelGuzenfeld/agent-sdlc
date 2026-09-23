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
printf 'x' >> "$edited"

if (cd "$consumer" && pre-commit run rules-check --all-files); then
    echo "FAIL: rules-check should fail after editing a synced rule" >&2
    rm -rf "$consumer"
    exit 1
fi

rm -rf "$consumer"
echo "all cases passed"
