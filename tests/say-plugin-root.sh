#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE CLAUDE_PLUGIN_ROOT

dir="$(cd "$(dirname "$0")/.." && pwd)"
failures=0

fail() {
    echo "FAIL: $1" >&2
    failures=$((failures + 1))
}

stubbin=$(mktemp -d)
cat > "$stubbin/aplay" <<'SH'
#!/usr/bin/env sh
cat >/dev/null
SH
chmod +x "$stubbin/aplay"
PATH="$stubbin:$PATH"
export PATH

wait_for() {
    file="$1"
    i=0
    while [ ! -f "$file" ] && [ "$i" -lt 50 ]; do
        i=$((i + 1))
        sleep 0.1
    done
}

plugin_install() {
    root=$(mktemp -d)
    mkdir -p "$root/bin"
    cp "$dir/bin/$1" "$dir/bin/say-extract.jq" "$root/bin/"
    printf '%s' "$root/bin"
}

legacy_install() {
    home="$1"
    script="$2"
    mkdir -p "$home/.claude/bin"
    ln -s "$dir/bin/$script" "$home/.claude/bin/$script"
    ln -s "$dir/bin/say-extract.jq" "$home/.claude/bin/say-extract.jq"
    printf '%s' "$home/.claude/bin"
}

narrate_stub() {
    bin="$1"
    marker="$2"
    rm -f "$bin/say-narrate.py"
    cat > "$bin/say-narrate.py" <<SH
#!/usr/bin/env sh
printf '%s' "\$*" > "$marker"
SH
    chmod +x "$bin/say-narrate.py"
}

say_sh_scenario() {
    label="$1"
    bin="$2"
    home="$3"

    mkdir -p "$home/.local/share/kokoro-venv/bin"
    marker="$home/argv0"
    rm -f "$marker"
    cat > "$home/.local/share/kokoro-venv/bin/python" <<SH
#!/usr/bin/env sh
printf '%s' "\$1" > "$marker"
cat >/dev/null
SH
    chmod +x "$home/.local/share/kokoro-venv/bin/python"

    txt=$(mktemp)
    printf 'hi\n' > "$txt"
    env HOME="$home" PATH="$PATH" sh "$bin/say.sh" "$txt" >/dev/null 2>&1 || true

    got=$(cat "$marker" 2>/dev/null || echo MISSING)
    [ "$got" = "$bin/ksay.py" ] || fail "[$label] say.sh KSAY: want $bin/ksay.py got $got"
}

home=$(mktemp -d)
say_sh_scenario "say.sh plugin-only install" "$(plugin_install say.sh)" "$home"

home=$(mktemp -d)
say_sh_scenario "say.sh legacy install" "$(legacy_install "$home" say.sh)" "$home"

say_hook_scenario() {
    label="$1"
    bin="$2"
    home="$3"

    xdg=$(mktemp -d)
    mkdir -p "$xdg/claude-say"

    pane="probe$$"
    p="$xdg/claude-say/p$pane"
    transcript=$(mktemp)
    long_answer=$(printf 'a%.0s' $(seq 1 90))
    {
        printf '{"type":"user","message":{"content":"question"}}\n'
        printf '{"type":"assistant","message":{"content":"%s"}}\n' "$long_answer"
    } > "$transcript"
    printf '{"transcript_path":"%s"}' "$transcript" > "$p.stdin"

    env HOME="$home" WEZTERM_PANE="$pane" XDG_RUNTIME_DIR="$xdg" PATH="$PATH" \
        sh "$bin/say-hook.sh" < "$p.stdin" >/dev/null 2>&1 || true

    [ -f "$p.txt" ] || fail "[$label] say-hook.sh never wrote $p.txt — say-extract.jq did not resolve next to $bin"
}

home=$(mktemp -d)
say_hook_scenario "say-hook.sh plugin-only install" "$(plugin_install say-hook.sh)" "$home"

home=$(mktemp -d)
say_hook_scenario "say-hook.sh legacy install" "$(legacy_install "$home" say-hook.sh)" "$home"

spawn_scenario() {
    script="$1"
    label="$2"
    bin="$3"
    home="$4"
    arg_mode="$5"

    xdg=$(mktemp -d)
    mkdir -p "$xdg/claude-say"
    marker="$xdg/marker"
    narrate_stub "$bin" "$marker"

    pane="probe$$"
    p="$xdg/claude-say/p$pane"
    printf 'seed' > "$p.txt"

    if [ "$arg_mode" = positional ]; then
        set -- "$pane"
    else
        set --
    fi

    env HOME="$home" WEZTERM_PANE="$pane" XDG_RUNTIME_DIR="$xdg" PATH="$PATH" \
        sh "$bin/$script" "$@" >/dev/null 2>&1 || true

    wait_for "$marker"
    [ -f "$marker" ] || fail "[$label] $script never launched say-narrate.py next to $bin"
}

home=$(mktemp -d)
spawn_scenario say-trigger.sh "say-trigger.sh plugin-only install" \
    "$(plugin_install say-trigger.sh)" "$home" wezterm

home=$(mktemp -d)
spawn_scenario say-trigger.sh "say-trigger.sh legacy install" \
    "$(legacy_install "$home" say-trigger.sh)" "$home" wezterm

home=$(mktemp -d)
spawn_scenario say-key.sh "say-key.sh plugin-only install" \
    "$(plugin_install say-key.sh)" "$home" positional

home=$(mktemp -d)
spawn_scenario say-key.sh "say-key.sh legacy install" \
    "$(legacy_install "$home" say-key.sh)" "$home" positional

if grep -q 'CLAUDE_PLUGIN_ROOT:-' "$dir/commands/say.md"; then
    fail "commands/say.md uses a \${CLAUDE_PLUGIN_ROOT:-...} default; only the bare token is substituted in command bodies"
fi
grep -q 'sh "${CLAUDE_PLUGIN_ROOT}/bin/say-trigger.sh"' "$dir/commands/say.md" \
    || fail "commands/say.md does not run say-trigger.sh from \${CLAUDE_PLUGIN_ROOT}/bin"

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
