#!/usr/bin/env bash
# Interactive wizard. Copy this file, edit only below the STAGES marker.
#
#   stage "<title>"            start a stage; clears the screen, shows progress
#   say "<text>"               a line of narration
#   step "<instruction>"       something for the human to do; waits for Enter
#   open_url "<url>"           open in the human's browser (Linux/macOS/WSL)
#   ask VAR "<question>"       read a visible value into VAR
#   ask_secret VAR "<question>"  read a hidden value into VAR
#   write_env KEY "<value>"    idempotent upsert into $ENV_FILE
#   set_secret NAME "<value>"  gh secret set (CI)
#   set_var NAME "<value>"     gh variable set (CI)
#   confirm "<what>"           gate before anything irreversible; aborts on no
#   summary                    closing report of what was written

set -euo pipefail

TOTAL_STAGES="${TOTAL_STAGES:-0}"
ENV_FILE="${ENV_FILE:-.env}"
CURRENT_STAGE=0
WROTE=()

_bold() { printf '\033[1m%s\033[0m\n' "$1"; }

stage() {
  CURRENT_STAGE=$((CURRENT_STAGE + 1))
  clear 2>/dev/null || printf '\n\n'
  _bold "[$CURRENT_STAGE/$TOTAL_STAGES] $1"
  printf '\n'
}

say() { printf '%s\n' "$1"; }

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _
}

open_url() {
  local url="$1" opener=''
  for candidate in xdg-open open wslview; do
    if command -v "$candidate" >/dev/null 2>&1; then opener="$candidate"; break; fi
  done
  say "Opening: $url"
  if [ -n "$opener" ]; then
    "$opener" "$url" >/dev/null 2>&1 || say "  (could not open automatically)"
  else
    say "  (open it by hand)"
  fi
}

ask() {
  local var="$1" question="$2" answer=''
  while [ -z "$answer" ]; do
    printf '\n>>> %s\n' "$question"
    read -r -p "    > " answer
  done
  printf -v "$var" '%s' "$answer"
}

ask_secret() {
  local var="$1" question="$2" answer=''
  while [ -z "$answer" ]; do
    printf '\n>>> %s\n' "$question"
    read -rsp "    > " answer
    printf '\n'
  done
  printf -v "$var" '%s' "$answer"
}

write_env() {
  local key="$1" value="$2"
  touch "$ENV_FILE"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    local tmp
    tmp="$(mktemp)"
    grep -vE "^${key}=" "$ENV_FILE" >"$tmp" || true
    mv "$tmp" "$ENV_FILE"
  fi
  printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
  WROTE+=("$ENV_FILE: $key")
}

# A gh failure must never abort the run: the human has already typed the value.
set_secret() {
  if gh secret set "$1" --body "$2" 2>/dev/null; then
    WROTE+=("gh secret: $1")
  else
    WROTE+=("gh secret: $1 — FAILED, set it by hand")
    say "  ! could not set secret $1; it is recorded in the summary"
  fi
}

set_var() {
  if gh variable set "$1" --body "$2" 2>/dev/null; then
    WROTE+=("gh variable: $1")
  else
    WROTE+=("gh variable: $1 — FAILED, set it by hand")
    say "  ! could not set variable $1; it is recorded in the summary"
  fi
}

confirm() {
  local answer=''
  printf '\n!!! %s\n' "$1"
  read -r -p "    Type yes to proceed: " answer
  [ "$answer" = "yes" ] || { say "Aborted."; exit 1; }
}

summary() {
  printf '\n'
  _bold "Done. Written:"
  local item
  for item in "${WROTE[@]:-}"; do [ -n "$item" ] && printf '  - %s\n' "$item"; done | sort -u
}

# --- STAGES ------------------------------------------------------------------
# Everything above this marker is the library. Do not edit it.

TOTAL_STAGES=1

stage "Example: get an API key"
say "Replace this stage with the real procedure."
open_url "https://example.com/dashboard/api-keys"
step "Sign in, then go to Developers -> API keys."
ask_secret API_KEY "Reveal the test key and paste it here:"
write_env "EXAMPLE_API_KEY" "$API_KEY"
set_secret "EXAMPLE_API_KEY" "$API_KEY"

summary
