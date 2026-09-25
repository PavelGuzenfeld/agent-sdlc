# Commands

Slash commands live in `commands/`. `install.sh` links them into
`~/.claude/commands` and renders each one as a Codex skill.

## At a glance

| Command | Use it when | Writes anything? |
|---|---|---|
| `/kata` | Work the `model:*`-labelled, `@me`-assigned ticket queue to merge | Branches, PRs, merges on `LGTM` |
| `/done` | Close out a bit of work and hand off to a fresh session | One commit; offers follow-up issues |
| `/grill` | Resolve an open design question by question | With `plan`: a decision record and step tickets |
| `/goon` | Approve the recommendation just proposed | Whatever that proposal named |
| `/rectify` | Fix contradictions in a doc against code or other docs | The doc, one conflict at a time |
| `/complicate` | Map deep refactors and tech debt | Nothing, report only |
| `/debrief-agent` | Review a session for changes to the agent's setup | Issues, on request |
| `/cleanup` | Free disk and stop this session's containers | Deletes caches, images, volumes by tier |
| `/activity` | Monthly hours report from transcripts | Nothing |
| `/say` | Hear the last answer read aloud | Nothing |
| `/unslop` | Strip AI tells from text | The text you give it |

## The ticket loop

```text
 idea with open questions        well-scoped ask
          |                             |
          v                             |
   /grill plan                          |
   (decision record + step tickets)     |
          |                             |
          +-------------+---------------+
                        v
              triage adds model:<name>
                        |
                        v
                     /kata  --> worker per ticket --> PR --> LGTM --> merge
                        |
                        v
                     /done  (after each merge: follow-ups filed)
```

### /kata

- `/kata` runs every open issue with a `model:haiku|sonnet|opus|fable` label
  assigned to `@me`. `/kata 42` runs just #42.
- Each ticket gets its own locked worktree, branch `42-slug`, and a fresh
  worker on the labelled model.
- The worker writes the slice test first, implements, runs the gate, opens a
  PR with `Closes #42`, and waits for green CI.
- Nothing merges until you type `LGTM` at the prompt.

```text
/kata 42
```

- Tiny follow-ups that share a model label batch into one PR, up to five.

### /done

- Finds the smallest coherent unit of this session's work, runs the cheap
  checks, and commits it. It never pushes.
- Leaves a handoff note so a clean session can pick up.
- Offers follow-up issues for what was left, each passed through a
  duplicate check and a banned-name scan.

```text
/done
```

### /grill

- Interviews you one question at a time, recommended answer first, until
  nothing is open.
- `/grill plan` files a decision record and one step ticket per unit of work.

```text
/grill how should the gate handle generated files?
```

### /goon

- Runs the most recent recommendation without re-explaining it.
- Does push, delete or send steps only if the proposal named them.

## Review and repair

### /rectify

- Takes a target doc and context sources, lists every contradiction, and
  splits them into verified (a command proved it) and suspected.
- Asks which side wins for each conflict, applies that fix, and shows one
  diff at the end.

```text
/rectify docs/config.md mutation_gate/repo.py
```

### /complicate

- A multi-lens review for deep refactor opportunities and technical debt.
- Report only; you name the items to apply.

### /debrief-agent

- Nine lenses over the session transcript. It proposes changes to rules,
  skills, hooks and memory, never to the code.
- Files findings through `/done`'s gate if you ask.

## Housekeeping

### /cleanup

| Tier | What it removes |
|---|---|
| `/cleanup` | This session's running state |
| `/cleanup space` | Build cache and dangling images |
| `/cleanup all` | Stops everything, prunes volumes |

### /activity

- Per-day work and personal hours for a month, with one sentence per day.

```text
/activity 2026-09
```

### /say

- Reads the last answer aloud through Kokoro. Claude Haiku rewrites it for
  listening first.
- Optional arguments: voice, speed, and free text such as "just the last
  paragraph".
- Needs `./install.sh --deps=say`.

### /unslop

- Rewrites text in a plain human voice and strips AI attribution and
  `Co-Authored-By` lines.

```text
/unslop <paste the PR description>
```
