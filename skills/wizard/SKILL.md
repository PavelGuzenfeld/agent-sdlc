---
name: wizard
description: "Generate a bash wizard for a step only a human can perform — credentials, hardware, or a migration. Reach for it the moment you hit one. Skip anything the agent can do."
---

# Wizard

A **wizard** is a bash script that walks a human, stage by stage, through a manual
procedure that is tedious by hand and tedious to re-explain every session. It opens
each URL, says what to click and copy, captures the values, writes them where they
belong, confirms before anything irreversible, and shows how many stages remain.

The UX is already solved by [template.sh](template.sh): stage progress, hidden
secret entry, cross-platform URL opening, idempotent `.env` upserts, `gh secret` /
`gh variable` writes, confirmation gates, and a closing summary. **Your job is only
to scope the procedure and author its stages.** The library above the `STAGES`
marker is identical in every wizard. Never hand-edit it.

A wizard is ephemeral by default: one run, written to a scratch path, deleted
afterwards. Commit it only when the user wants a repeatable setup path in the repo.

## 1. Scope the procedure

Work out every manual step and every value captured along the way. **Read the repo
first, do not ask cold:**

- Setup: `.env`, `.env.example`, `.env.*`, README, `docker-compose*`, framework
  config, and `.github/workflows/*` — every `secrets.*` and `vars.*` reference is a
  value the wizard must produce.
- Migration or cutover: the current state, the target state, and every irreversible
  action between them.
- Hardware or bench work: which box, which user, whether `sudo` needs a password,
  what has to be physically touched.

Then show the ordered stage list and the values each produces, and confirm it. The
user may add, drop, or reorder.

**Done when** every stage is named in order and, for each value, you know where the
human gets it, where it is written (`.env`, a CI secret, both, or nowhere — some
stages are pure actions), and whether it is secret.

## 2. Map each stage's journey

For each stage, write the precise path: which URL, what to do there, where the value
appears, which variable it fills. "Dashboard → Developers → API keys → Reveal test
key → copy."

Where you do not know the current UI or the exact command, **say so and ask, or
check the docs.** Never invent steps that may not exist — a wrong click path is
worse than no wizard, because the human trusts it.

**Done when** every stage traces to instructions a stranger could follow.

## 3. Author it

Copy `template.sh` to the target path. Replace the example stage with one `stage`
per step, in dependency order, and set `TOTAL_STAGES`.

Hold the bar the template sets:

- `open_url` before asking for the value that page shows.
- `ask_secret` for anything secret, `ask` otherwise.
- `write_env` every persisted value; `set_secret` only what CI actually reads.
- `confirm` before every irreversible action.
- One focused task per stage — each `stage` clears the screen, so nothing the human
  still needs may scroll away.

## 4. Verify and hand off

- `bash -n <script>`, and `shellcheck` if available.
- `chmod +x <script>`.
- **Do not run it end-to-end yourself.** It opens browsers and blocks on human
  input. Trace it statically instead: every value from step 1 is captured and lands
  where step 1 said, and every `set_secret` name matches a `secrets.*` reference in
  CI exactly.
- Tell the user how to run it, and that `! bash <path>` runs it in-session so its
  output lands in the conversation.
- If it is a repeatable setup path, commit it and link it from the README, so the
  next person runs the script instead of asking an agent.
