---
description: Finalize the smallest coherent bit of this session's work and leave a handoff, so a clear session can continue. Commits, never pushes. Offers gated follow-up issues for what was left. Ends by offering /cleanup and /debrief-agent.
---

# Done

Finalize the smallest coherent unit this session produced, and leave enough behind
that a fresh session continues without re-deriving anything.

Commit. **Never push** — pushing is its own deliberate act.

## Sequence

Checkpoint agents → survey → verify → commit → file → handoff → report → offer cleanup.
Handoff comes after the commit so it can name the real SHA, and after filing so it can
name the real issue numbers.

### 1. Checkpoint agents

Only on an explicit `/done`. Kata's post-merge tail — `/done`'s tail run without its
handoff step — skips this too: that tail follows one ticket's own merge, not a session
interrupt, and must never reach into another lane's live agents.

`ListAgents`, the Subagents section only — a peer or remote session, listed
elsewhere in ListAgents, is foreign, same as another terminal's work, and is
never checkpointed, at most named "not touched" in the report. Nothing live:
skip to survey.

Send each live agent a checkpoint request: stop at a clean point, commit WIP on its own
branch, never push, and report back its branch, worktree, SHA, next step, and any
follow-up candidates noticed but not acted on. The commit this causes is one `/done`
makes happen, not one it pushes — "never push" still holds.

Wait for every reply. An agent that never replies is named in the report and the
handoff with no branch or SHA to give. Nothing to commit: the agent says so and no
commit is made. Mid a gated commit: the agent finishes or aborts the gate cleanly before
replying — never killed, a killed mutation-gate run leaves mutants on disk.

### 2. Survey

`git status` and `git diff` in every repo touched this session, and in every worktree of
an agent that replied to the checkpoint. Attribute each change: did this session make
it, or not?

Anything you cannot attribute to this session is **foreign** — another terminal, the
user's own edit, a harness rewrite of its own files. Foreign changes are never
committed and never reverted. They get reported.

Run git from the work-tree root. A subdirectory cwd silently scopes pathspecs, so
`ls-files`, `grep <tree-ish>` and `apply` quietly operate on the wrong subset — with
`--work-tree` set this fails without an error message.

### 3. Verify

The cheapest check per changed file type, on changed files only, in every repo Survey
covered — main tree and each replying agent's worktree: `bash -n`, `zsh -n`, an elisp
`read` loop, `ruff`/`prettier`, a JSON parse. Never a build, never Docker — this command
is a reflex and has to stay sub-second.

A deleted line range is the case that needs this most: confirm the file still parses
and that only what you meant to remove is gone. If a check fails, fix before
committing.

Full test suites are a deliberate ask, not part of `/done`.

### 4. Commit

Stage selectively. If this session's work spans unrelated concerns, split it into
separate commits rather than one mixed one.

When a file mixes this session's work with foreign edits, do not stage the file. Build
a patch of your hunks alone and stage that:

```
git show HEAD:<path> > base
# apply only your change to a copy
git diff --no-index --src-prefix=a/ --dst-prefix=b/ base new | sed 's#base#<path>#;s#new#<path>#' > p
git apply --cached p
```

Then confirm the staged diff is exactly yours: `git diff --cached --numstat`, and grep
the staged diff for lines you did not intend to touch.

Report the changed-line count. Follow the repo's commit-message convention — read
`git log` before writing one.

### 5. File follow-ups

A candidate needs an artifact from this session behind it: a defect you observed and
did not fix, scope deferred out loud, a `TODO`/`FIXME` this diff added, a waiver
recorded in `.mutation-gate-waivers.toml`, or a line of `parked-ideas.md` in the
session scratchpad — read that file, leave it untouched. Nothing inferred, nothing
`/simplify` or `/complicate` would have produced.

Route by the remote the commit landed on; no remote, or not a repo, means print the
candidates and file nothing. Drop any the handoff already references, and any whose
title matches an open issue — one `gh issue list --state open` per target repo. The
handoff is overwritten each run, so only that match catches a repeat from last week.

One gate, five candidates maximum across all repos — a checkpointed agent's reported
candidates count against the same five, not a pool of their own — rows reading
`<repo> — <title>`.
Private-remote rows come pre-selected; public-remote rows do not, and ticking one
prints its full title and body for a yes/no first. Unticked is dropped, not deferred.
Past five, offer the strongest five and say how many were dropped. Scan every draft
before filing it; a hit blocks that item and names the token, never redact and file.

Build the alternation from the banned-name and identity lists in
`~/.claude/rules/public-surface.md`, which is the only copy of them, and run it
over the draft. Never restate the tokens here — this file is committed.

Title states the defect or the task flat — no prefix tag, no Overview, no closing
line. Body is these four fields and nothing else, `Noticed in` being the commit that
touched the evidence path, or the run's last commit when it is not a path:

```
<what was observed, one or two lines>

Evidence: <path:line, test name, waiver entry, or a quoted session line>
Noticed in: <commit SHA>
Deferred because: <one line>
```

A public remote gets the same content as prose: no field labels, no bullets, no
AI-attribution line ever. `gh issue create` with the `follow-up` label, created if
missing; if creation is refused, file without it rather than drop the item.

Nothing qualifying prints nothing. Anything here failing — auth, network, API — prints
the drafts and continues; the commit and the SHA report never depend on this step.

### 6. Handoff

Skip this step entirely when every commit this session landed, main's and every
checkpointed agent's, is on a branch whose PR carries `Closes #N` — the ticket already
holds the state. An agent branch with no PR open yet fails that test on its own, so a
live checkpoint almost always forces this step even when main's commit alone would have
skipped it. Delete a stale `project_current_work.md` and its pointer.

Rewrite `project_current_work.md` in this project's memory directory. **Overwrite it.**
It is one rolling file, never a per-session note — accumulating stopping points is the
failure this design exists to avoid.

It holds only what git cannot: the commit SHA and what landed, the next concrete step,
anything blocked with the reason, and — one line per checkpointed agent — its branch,
worktree, SHA and next step. Anything that outlives this thread of work is an issue, not
a line here — reference those by number and do not restate them. Keep its `MEMORY.md`
pointer to one line.

When the work is finished, delete the file and its pointer. A stale handoff is worse
than none.

### 7. Report

The SHA and subject. The changed-line count. What was left unstaged and why. What is
unpushed. The issues filed, by number, if any were — or the reason filing failed.

### 8. Offer cleanup

One line offering `/cleanup` and `/debrief-agent`. Do not run either.
