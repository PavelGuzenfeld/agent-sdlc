#!/usr/bin/env sh
set -eu

dir="$(cd "$(dirname "$0")/.." && pwd)"
doc="$dir/commands/activity.md"
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
failures=0

awk '/^```bash$/{p=1;next} /^```$/{if(p){p=0;next}} p' "$doc" > "$work/activity.sh"
[ -s "$work/activity.sh" ] || { echo "FAIL: no fenced bash block found in $doc" >&2; exit 1; }
chmod +x "$work/activity.sh"

encode() { printf '%s' "$1" | sed 's#/#-#g'; }

make_repo() {
    home="$1"; base="$2"; repo="$3"; name="$4"; email="$5"; subject="$6"; when="$7"
    mkdir -p "$home/$base/$repo"
    git -C "$home/$base/$repo" init -q
    git -C "$home/$base/$repo" config user.name "$name"
    git -C "$home/$base/$repo" config user.email "$email"
    GIT_AUTHOR_DATE="$when" GIT_COMMITTER_DATE="$when" \
        git -C "$home/$base/$repo" commit -q --allow-empty -m "$subject"
}

add_session() {
    home="$1"; project_dir="$2"; ts="$3"
    session_dir=$(encode "$project_dir")
    mkdir -p "$home/.claude/projects/$session_dir"
    {
        printf '{"timestamp":"%s","type":"user"}\n' "$ts"
        printf '{"timestamp":"%s","type":"tool_use","input":{"file_path":"%s/notes.txt"}}\n' \
            "$ts" "$project_dir"
    } > "$home/.claude/projects/$session_dir/sess.jsonl"
}

check_contains() {
    name="$1"; haystack="$2"; needle="$3"
    case "$haystack" in
        *"$needle"*) ;;
        *) echo "FAIL: $name (expected to find: $needle)" >&2; failures=$((failures + 1)) ;;
    esac
}

fake_home="$work/home-default"
mkdir -p "$fake_home/.claude/projects" "$fake_home/workspace" "$fake_home/personalspace"
HOME="$fake_home" git config --global user.name "Test User"
HOME="$fake_home" git config --global user.email "test-user-noaddr"

make_repo "$fake_home" workspace work-repo "Test User" "test-user-noaddr" "add work feature" "2026-03-05T10:00:00"
make_repo "$fake_home" personalspace home-repo "Test User" "test-user-noaddr" "fix personal bug" "2026-03-06T10:00:00"
add_session "$fake_home" "$fake_home/personalspace/home-repo" "2026-03-06T09:00:00.000Z"
add_session "$fake_home" "$fake_home/workspace/work-repo" "2026-03-05T09:00:00.000Z"

out=$(cd "$work" && HOME="$fake_home" "$work/activity.sh" 2026-03)

check_contains "default: derives author from git config, finds work commit" "$out" $'work\twork-repo\tadd work feature'
check_contains "default: derives author from git config, finds personal commit" "$out" $'personal\thome-repo\tfix personal bug'

sessions_block=$(printf '%s\n' "$out" | awk '/###SESSIONS###/{p=1;next}/###REPOS###/{p=0}p')
home_enc=$(encode "$fake_home")
personal_label=$(encode "$fake_home/personalspace/home-repo" | sed "s/^${home_enc}-//")
personal_session_line=$(printf '%s\n' "$sessions_block" | grep "$personal_label" || true)
check_contains "sessions block marks the personalspace session personal under a non-pavelgu HOME" \
    "$personal_session_line" $'\tpersonal\t'

repos_block=$(printf '%s\n' "$out" | awk '/###REPOS###/{p=1;next}/###COMMITS###/{p=0}p')
check_contains "repos block finds a touch on home-repo tagged personal" "$repos_block" $'personal\thome-repo'
check_contains "repos block finds a touch on work-repo tagged work" "$repos_block" $'work\twork-repo'

fake_home2="$work/home-override"
mkdir -p "$fake_home2/.claude/projects" "$fake_home2/workspace" "$fake_home2/mind"
HOME="$fake_home2" git config --global user.name "Nobody Special"
HOME="$fake_home2" git config --global user.email "nobody-user-noaddr"
make_repo "$fake_home2" mind side-repo "Someone Else" "else-user-noaddr" "write a diary entry" "2026-03-07T10:00:00"
add_session "$fake_home2" "$fake_home2/mind/side-repo" "2026-03-07T09:00:00.000Z"

out2=$(cd "$work" && HOME="$fake_home2" ACTIVITY_DIRS="workspace mind" ACTIVITY_PERSONAL_DIRS="mind" \
    ACTIVITY_AUTHOR="Someone Else" "$work/activity.sh" 2026-03)

check_contains "ACTIVITY_PERSONAL_DIRS/ACTIVITY_AUTHOR override picks up a custom layout" "$out2" $'personal\tside-repo'
check_contains "ACTIVITY_AUTHOR override finds the commit despite a different git identity" "$out2" "write a diary entry"

if [ "$failures" -ne 0 ]; then
    echo "activity.sh: $failures failure(s)" >&2
    exit 1
fi
echo "activity.sh: ok"
