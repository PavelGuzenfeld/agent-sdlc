#!/usr/bin/env sh
set -eu
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE

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

narrate_stub() {
    dest="$1"
    marker="$2"
    mkdir -p "$dest"
    cat > "$dest/say-narrate.py" <<SH
#!/usr/bin/env sh
printf '%s' "\$*" > "$marker"
SH
    chmod +x "$dest/say-narrate.py"
}

wait_for() {
    file="$1"
    i=0
    while [ ! -f "$file" ] && [ "$i" -lt 50 ]; do
        i=$((i + 1))
        sleep 0.1
    done
}

# --- say.sh: KSAY resolves under ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/bin ---
say_sh_scenario() {
    label="$1"
    plugin_root="$2"
    home="$3"
    want="$4"

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

    if [ -n "$plugin_root" ]; then
        env CLAUDE_PLUGIN_ROOT="$plugin_root" HOME="$home" PATH="$PATH" \
            sh "$dir/bin/say.sh" "$txt" >/dev/null 2>&1 || true
    else
        env HOME="$home" PATH="$PATH" \
            sh "$dir/bin/say.sh" "$txt" >/dev/null 2>&1 || true
    fi

    got=$(cat "$marker" 2>/dev/null || echo MISSING)
    [ "$got" = "$want" ] || fail "[$label] say.sh KSAY: want $want got $got"
}

say_sh_scenario "say.sh plugin root" "/fake/plugin/root" "$(mktemp -d)" \
    "/fake/plugin/root/bin/ksay.py"

legacy_home=$(mktemp -d)
say_sh_scenario "say.sh legacy fallback" "" "$legacy_home" "$legacy_home/.claude/bin/ksay.py"

# --- say-hook.sh: $BIN/say-extract.jq must resolve to find the real filter ---
say_hook_scenario() {
    label="$1"
    plugin_root="$2"
    home="$3"
    bin_root="$4"

    xdg=$(mktemp -d)
    mkdir -p "$xdg/claude-say" "$bin_root"
    cp "$dir/bin/say-extract.jq" "$bin_root/say-extract.jq"

    pane="probe$$"
    p="$xdg/claude-say/p$pane"
    transcript=$(mktemp)
    long_answer=$(printf 'a%.0s' $(seq 1 90))
    {
        printf '{"type":"user","message":{"content":"question"}}\n'
        printf '{"type":"assistant","message":{"content":"%s"}}\n' "$long_answer"
    } > "$transcript"
    printf '{"transcript_path":"%s"}' "$transcript" > "$p.stdin"

    if [ -n "$plugin_root" ]; then
        env CLAUDE_PLUGIN_ROOT="$plugin_root" HOME="$home" WEZTERM_PANE="$pane" \
            XDG_RUNTIME_DIR="$xdg" PATH="$PATH" \
            sh "$dir/bin/say-hook.sh" < "$p.stdin" >/dev/null 2>&1 || true
    else
        env HOME="$home" WEZTERM_PANE="$pane" XDG_RUNTIME_DIR="$xdg" PATH="$PATH" \
            sh "$dir/bin/say-hook.sh" < "$p.stdin" >/dev/null 2>&1 || true
    fi

    [ -f "$p.txt" ] || fail "[$label] say-hook.sh never wrote $p.txt — \$BIN/say-extract.jq did not resolve to $bin_root"
}

plugin_root=$(mktemp -d)
home_without_legacy=$(mktemp -d)
say_hook_scenario "say-hook.sh plugin root" "$plugin_root" "$home_without_legacy" "$plugin_root/bin"

legacy_home2=$(mktemp -d)
say_hook_scenario "say-hook.sh legacy fallback" "" "$legacy_home2" "$legacy_home2/.claude/bin"

# --- say-trigger.sh / say-key.sh: spawn ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/bin/say-narrate.py ---
spawn_scenario() {
    script="$1"
    label="$2"
    plugin_root="$3"
    home="$4"
    bin_root="$5"
    arg_mode="$6"

    xdg=$(mktemp -d)
    mkdir -p "$xdg/claude-say"
    marker="$xdg/marker"
    narrate_stub "$bin_root" "$marker"

    pane="probe$$"
    p="$xdg/claude-say/p$pane"
    printf 'seed' > "$p.txt"

    if [ "$arg_mode" = positional ]; then
        set -- "$pane"
    else
        set --
    fi

    if [ -n "$plugin_root" ]; then
        env CLAUDE_PLUGIN_ROOT="$plugin_root" HOME="$home" WEZTERM_PANE="$pane" \
            XDG_RUNTIME_DIR="$xdg" PATH="$PATH" sh "$dir/bin/$script" "$@" >/dev/null 2>&1 || true
    else
        env HOME="$home" WEZTERM_PANE="$pane" XDG_RUNTIME_DIR="$xdg" PATH="$PATH" \
            sh "$dir/bin/$script" "$@" >/dev/null 2>&1 || true
    fi

    wait_for "$marker"
    [ -f "$marker" ] || fail "[$label] $script never launched \$BIN/say-narrate.py from $bin_root"
}

plugin_root2=$(mktemp -d)
home_without_legacy2=$(mktemp -d)
spawn_scenario say-trigger.sh "say-trigger.sh plugin root" \
    "$plugin_root2" "$home_without_legacy2" "$plugin_root2/bin" wezterm

legacy_home3=$(mktemp -d)
spawn_scenario say-trigger.sh "say-trigger.sh legacy fallback" \
    "" "$legacy_home3" "$legacy_home3/.claude/bin" wezterm

plugin_root3=$(mktemp -d)
home_without_legacy3=$(mktemp -d)
spawn_scenario say-key.sh "say-key.sh plugin root" \
    "$plugin_root3" "$home_without_legacy3" "$plugin_root3/bin" positional

legacy_home4=$(mktemp -d)
spawn_scenario say-key.sh "say-key.sh legacy fallback" \
    "" "$legacy_home4" "$legacy_home4/.claude/bin" positional

if [ "$failures" -ne 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi

echo "all cases passed"
