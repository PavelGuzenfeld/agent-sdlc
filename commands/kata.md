---
description: Pick a ready ticket, slice it, push it through review, wait for LGTM, merge. `/kata` runs the whole ready queue; `/kata <N>` runs one ticket.
---

# Kata

The main session's ticket-to-merge loop. It dispatches; it never implements.

## Queue

- `/kata` — every issue labelled `ready`.
- `/kata <N>` — just ticket `N`. Naming a ticket in plain English is the same
  authorisation as the label.

Read each ticket's `model:<name>` label before dispatch. A repo missing the
`ready`/`model:*` labels, or a ticket missing one: create what's missing, then
continue — this loop creates labels and repo config on demand, the way `/done`
creates `follow-up`.

## Dispatch

One ticket, one branch, one PR — never batch tickets onto a shared branch.

Same repo: sequential, unless the tickets touch disjoint paths, in which case
run them in parallel. Different repos: always parallel.

The orchestrator creates the ticket's worktree itself — `git worktree add
--lock -b <N>-<slug> ../<repo>-<N>-<slug> origin/main` — and hands the agent
that path. Never the Agent tool's `isolation: "worktree"`: it auto-names the
branch `worktree-agent-<id>`, and the gate's adversary can't read a ticket
off that.

Spawn a fresh implementation agent per ticket, with the ticket's number and
body, its `model:<name>` label as the agent's model override, and the
worktree's path. The agent works from that body and does not loop
`gh issue view` over linked issues unless the ticket names one it needs. The
agent:

1. Writes the ticket's slice test first and confirms it fails.
2. Implements to green.
3. Runs the gate. Its adversary runs on the ticket's `model:<name>` label.
   Findings get addressed each round; after 2 rounds still carrying findings,
   the agent reports back instead of running a third gated commit. A waiver
   is fine only when it is an equivalence waiver proved by rebuild-and-diff —
   any other waiver stops the agent the same way.
4. Pushes, then opens a PR with `Closes #N`, at most three plain sentences on
   what changed, and a Human-testing section when the change is
   user-observable. No how-it-works paragraph.
5. Waits for CI with one blocking call — `gh pr checks <PR> --watch`, output
   to a file — never polling turn by turn. No `.github/workflows/` in the
   repo means no checks to wait for — skip straight to exit. Red: fix, push,
   and watch again.
6. Exits only once CI is green on the pushed sha, never before, reporting the
   PR number, the ticket number, and any follow-up candidates noticed but not
   acted on.

At work: stop once CI is green on the pushed sha, never sooner. No self-merge,
ever, regardless of LGTM.

## Review loop

Before asking for LGTM, the orchestrator runs `/verify-generated-diff` on the
PR.

Wait for a human `LGTM` typed at the terminal prompt — never a PR comment.
Anything else is feedback: respawn the same agent on the same branch with the
comments — never open a second PR for the same ticket.

Where this loop is allowed to merge, an `LGTM` squash-merges, then unlocks and
removes the worktree, then deletes the branch. The merge closes the ticket
through `Closes #N`.

Then file the agent's follow-up candidates, run `/done`'s tail without its
handoff step or its agent-checkpoint step, and move to the next ticket. That
tail follows one ticket's own merge, not a session interrupt, and must never
reach into another lane's live agents.

## Acceptance

`/kata 3` against a `ready` + `model:sonnet` ticket #3 ends with an open PR
whose body has `Closes #3` and, when applicable, a Human-testing section — and
a worktree that is gone once that PR merges.
