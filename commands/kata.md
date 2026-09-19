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

Spawn a fresh implementation agent per ticket, with the ticket's number and
body, its `model:<name>` label as the agent's model override, and its own
locked worktree. The agent:

1. Writes the ticket's slice test first and confirms it fails.
2. Implements to green.
3. Runs the gate. A waiver is fine only when it is an equivalence waiver proved
   by rebuild-and-diff — any other waiver stops the agent, which reports back
   instead of pushing.
4. Pushes, then waits for checks to go green on the pushed sha. No
   `.github/workflows/` in the repo means no checks to wait for — skip
   straight to opening the PR.
5. Opens a PR with `Closes #N` in the body, and a Human-testing section when
   the change is user-observable.
6. Exits, reporting the PR number, the ticket number, and any follow-up
   candidates noticed but not acted on.

`/verify-generated-diff` still applies to this diff like any other.

At work: stop at PR-open. No self-merge, ever, regardless of LGTM.

## Review loop

Wait for a human `LGTM` on the PR. Anything else is feedback: respawn the same
agent on the same branch with the comments — never open a second PR for the
same ticket.

Where this loop is allowed to merge, an `LGTM` squash-merges, deletes the
branch, and removes the worktree. The merge closes the ticket through
`Closes #N`.

Then file the agent's follow-up candidates, run `/done`'s tail without its
handoff step, and move to the next ticket.

## Acceptance

`/kata 3` against a `ready` + `model:sonnet` ticket #3 ends with an open PR
whose body has `Closes #3` and, when applicable, a Human-testing section — and
a worktree that is gone once that PR merges.
