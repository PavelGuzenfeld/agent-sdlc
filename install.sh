#!/usr/bin/env sh
set -eu

repo="$(cd "$(dirname "$0")" && pwd)"
target=all
deps=
status=0

usage() {
    echo "usage: ./install.sh [--target claude|codex|all] [--deps | --deps=say]" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --target) [ $# -ge 2 ] || usage; target="$2"; shift 2 ;;
        --target=*) target="${1#--target=}"; shift ;;
        --deps) deps=base; shift ;;
        --deps=say) deps=say; shift ;;
        *) usage ;;
    esac
done
case "$target" in claude|codex|all) ;; *) usage ;; esac

collisions=
for d in "$repo"/skills/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    if [ -f "$repo/commands/$name.md" ]; then
        collisions="$collisions $name"
    fi
done
if [ -n "$collisions" ]; then
    echo "install.sh: name used by both a skill and a command:$collisions" >&2
    exit 1
fi

wants() { [ "$target" = all ] || [ "$target" = "$1" ]; }

link() {
    src="$1"
    dst="$2"
    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
        return
    fi
    if [ -d "$dst" ] && [ ! -L "$dst" ]; then
        echo "install.sh: $dst is a directory in the way; remove it and rerun" >&2
        status=1
        return
    fi
    mkdir -p "$(dirname "$dst")"
    ln -sfn "$src" "$dst"
    echo "link $dst"
}

command_description() {
    awk '
        NR == 1 && $0 == "---" { fm = 1; next }
        fm && $0 == "---" { fm = 0; next }
        fm { if (sub(/^description:[ \t]*/, "")) desc = $0; next }
        desc == "" && fallback == "" && $0 !~ /^(#|[ \t]*$)/ { fallback = $0 }
        END { print (desc != "" ? desc : fallback) }
    ' "$1"
}

command_body() {
    awk 'NR == 1 && $0 == "---" { fm = 1; next } fm && $0 == "---" { fm = 0; next } !fm' "$1"
}

render_codex_command() {
    file="$1"
    name=$(basename "$file" .md)
    dst="$HOME/.codex/skills/$name/SKILL.md"
    tmp=$(mktemp)
    {
        printf -- '---\nname: %s\ndescription: %s\n---\n' "$name" "$(command_description "$file")"
        command_body "$file"
    } > "$tmp"
    if [ -f "$dst" ] && cmp -s "$tmp" "$dst"; then
        rm -f "$tmp"
        return
    fi
    mkdir -p "$(dirname "$dst")"
    mv "$tmp" "$dst"
    echo "write $dst"
}

merge_hook() {
    hook_type="$1"
    guard="$2"
    entry="$3"
    before=$(jq -c . "$settings")
    "$repo/bin/merge-claude-hook.sh" "$settings" "$hook_type" "$guard" \
        '.hooks[$t] = ((.hooks[$t] // []) + [$e])' --arg t "$hook_type" --argjson e "$entry"
    [ "$before" = "$(jq -c . "$settings")" ] || echo "hook $hook_type $guard"
}

install_claude() {
    for d in "$repo"/skills/*/; do
        link "${d%/}" "$HOME/.claude/skills/$(basename "$d")"
    done
    for f in "$repo"/commands/*.md; do
        link "$f" "$HOME/.claude/commands/$(basename "$f")"
    done
    for f in "$repo"/bin/*; do
        link "$f" "$HOME/.claude/bin/$(basename "$f")"
    done

    settings="$HOME/.claude/settings.json"
    if [ ! -f "$settings" ]; then
        mkdir -p "$HOME/.claude"
        printf '{}\n' > "$settings"
        echo "write $settings"
    fi
    jq -c '.hooks | to_entries[] | .key as $t | .value[] | {type: $t, entry: .}' "$repo/settings.example.json" |
    while IFS= read -r line; do
        merge_hook \
            "$(printf '%s' "$line" | jq -r .type)" \
            "$(printf '%s' "$line" | jq -r '.entry.hooks[0].command | split(" ") | ((map(select(contains("/"))) | first) // .[0]) | split("/") | last')" \
            "$(printf '%s' "$line" | jq -c .entry)"
    done
    if command -v mutation-gate >/dev/null 2>&1; then
        merge_hook Stop mutation-gate '{"hooks":[{"type":"command","command":"mutation-gate --worktree"}]}'
    fi

    if [ ! -e "$HOME/.claude/CLAUDE.md" ]; then
        cp "$repo/CLAUDE.md.example" "$HOME/.claude/CLAUDE.md"
        echo "write $HOME/.claude/CLAUDE.md"
    fi
}

install_codex() {
    for d in "$repo"/skills/*/; do
        link "${d%/}" "$HOME/.codex/skills/$(basename "$d")"
    done
    for f in "$repo"/commands/*.md; do
        render_codex_command "$f"
    done
}

as_root() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

apt_missing=
need_apt() {
    command -v "$1" >/dev/null 2>&1 || apt_missing="$apt_missing $2"
}

py_install() {
    if command -v pipx >/dev/null 2>&1; then
        pipx install ${2:+--force} "$1" >/dev/null
    else
        python3 -m pip install --user "$1" >/dev/null
    fi
    echo "python $1"
}

install_deps() {
    PATH="$HOME/.local/bin:$PATH"
    need_apt git git
    need_apt gh gh
    need_apt jq jq
    need_apt docker docker.io
    need_apt python3 python3
    need_apt pipx pipx
    need_apt curl curl
    python3 -c 'import pytest' >/dev/null 2>&1 || apt_missing="$apt_missing python3-pytest"
    python3 -c 'import ensurepip' >/dev/null 2>&1 || apt_missing="$apt_missing python3-venv"
    [ "$deps" = say ] && need_apt aplay alsa-utils
    if [ -n "$apt_missing" ]; then
        as_root apt-get update -q
        as_root apt-get install -y -q --no-install-recommends $apt_missing
        echo "apt$apt_missing"
    fi
    ast_grep_pin=ast-grep-cli==0.45.3
    installed_ast_grep=$(ast-grep --version 2>/dev/null || true)
    [ "$installed_ast_grep" = "ast-grep ${ast_grep_pin#*==}" ] || py_install "$ast_grep_pin" force
    command -v pre-commit >/dev/null 2>&1 || py_install pre-commit
    command -v mutation-gate >/dev/null 2>&1 || py_install "$repo"
    [ "$deps" = say ] && install_say
    return 0
}

install_say() {
    venv="$HOME/.local/share/kokoro-venv"
    data="$HOME/.local/share/kokoro"
    if [ ! -x "$venv/bin/python" ]; then
        python3 -m venv "$venv"
        echo "venv $venv"
    fi
    if ! "$venv/bin/python" -c 'import kokoro_onnx, numpy, anthropic' >/dev/null 2>&1; then
        "$venv/bin/pip" install -q kokoro-onnx numpy anthropic
        echo "pip kokoro-onnx numpy anthropic"
    fi
    mkdir -p "$data"
    for f in kokoro-v1.0.onnx voices-v1.0.bin; do
        if [ ! -f "$data/$f" ]; then
            curl -fsSL -o "$data/$f.part" \
                "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/$f"
            mv "$data/$f.part" "$data/$f"
            echo "fetch $data/$f"
        fi
    done
}

[ -n "$deps" ] && install_deps
wants claude && install_claude
wants codex && install_codex
exit "$status"
