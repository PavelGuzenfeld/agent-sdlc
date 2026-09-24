---
description: Pick a model-labelled ticket, slice it, push it through review, wait for LGTM, merge. `/kata` runs the whole model-label queue; `/kata <N>` runs one ticket.
---

# Kata

The main session's ticket-to-merge loop. It dispatches; it never implements.

## Queue

- `/kata` — every open issue labelled `model:haiku`, `model:sonnet`,
  `model:opus` or `model:fable`. An unlabelled ticket was never in the queue.
  Follow-ups also labelled size:tiny that share one `model:<name>` label group
  into batches of at most five, each batch taking its oldest ticket's queue
  position — a longer tiny queue splits into more batches. Kata's own
  judgment may pull a ticket out of a batch it finds not tiny; it never adds
  an unlabelled ticket to one.
- `/kata <N>` — just ticket `N`, alone, even when it carries size:tiny.
  Batching only happens in whole-queue `/kata`. Naming a ticket in plain
  English is the same authorisation as the label.

A run works the queue as it stood when it started. A ticket filed while it
runs waits for the next `/kata`.

Read each ticket's `model:<name>` label before dispatch. Triage adding it is
the approval, so kata never creates or adds a `model:*` label at dispatch —
it only creates repo config and labels on demand the way the labels
`rules/tickets.md`'s Follow-ups section requires get created if missing.
`/kata <N>` on a ticket with no model label asks which model; that answer is
the triage, so kata adds its `model:<name>` label, then dispatches.

## Dispatch

One ticket, one branch, one PR, per `rules/tickets.md` — except its one
carve-out, a confirmed-tiny batch, which shares a worker, a branch and a PR
across the tickets grouped for it above.

Same repo: sequential, unless the tickets touch disjoint paths, in which case
run them in parallel. Different repos: always parallel.

The orchestrator creates the worktree itself — `git worktree add --lock -b
<N>-<slug> ../<repo>-<N>-<slug> origin/main` — and hands the agent that path.
A batch keeps the same branch shape, named for its oldest ticket, so the
gate's adversary still reads a ticket number off it. Never the Agent tool's
`isolation: "worktree"`: it auto-names the branch `worktree-agent-<id>`, and
the gate's adversary can't read a ticket off that.

Spawn a fresh implementation agent per ticket or per batch, with every
ticket's number and body, the shared `model:<name>` label as the agent's
model override, and the worktree's path. The agent works from that body and
does not loop `gh issue view` over linked issues unless a ticket names one it
needs. The agent:

1. Writes each ticket's slice test first and confirms it fails.
2. Implements each ticket to green.
3. Runs the gate once for the whole branch. Its adversary runs on the shared
   `model:<name>` label. Findings get addressed each round; after 2 rounds
   still carrying findings, the agent reports back instead of running a third
   gated commit. A waiver is fine only when it is an equivalence waiver proved
   by rebuild-and-diff — any other waiver stops the agent the same way.
4. Pushes, then opens one PR with a `Closes #N` line per ticket still in it,
   at most three plain sentences on what changed, and a Human-testing section
   when the change is user-observable. No how-it-works paragraph.
5. Waits for CI with one blocking call — `gh pr checks <PR> --watch`, output
   to a file — never polling turn by turn. No `.github/workflows/` in the
   repo means no checks to wait for — skip straight to exit. Red: fix, push,
   and watch again.
6. Exits only once CI is green on the pushed sha, never before, reporting the
   PR number, every ticket number still in it, and any follow-up candidates —
   only what it saw fail or deferred out loud this session, never a
   same-class-elsewhere guess or anything it would itself call speculative.
   "None" is the normal answer.

A ticket the agent finds not tiny mid-batch: it reverts that ticket's changes
off the branch, drops its `Closes #N` line, strips its size:tiny label with a
one-line comment giving the reason, then finishes the rest of the batch. That
ticket reports as pulled, not closed, and returns to the queue as a single
run. If it is the batch's oldest ticket, stop the batch instead; the branch
name depends on it.

At work: stop once CI is green on the pushed sha, never sooner. No self-merge,
ever, regardless of LGTM.

## Review loop

Before asking for LGTM, the orchestrator runs `/verify-generated-diff` on the
PR.

Wait for a human `LGTM` typed at the terminal prompt — never a PR comment.
Anything else is feedback: respawn the same agent on the same branch with the
comments — never open a second PR for the same ticket or batch.

Where this loop is allowed to merge, an `LGTM` squash-merges, then unlocks and
removes the worktree, then deletes the branch with `git branch -D`, which the
guardrail allows once the branch's tip is that merged PR's head or an ancestor of it. The merge
closes every ticket still in it through its own `Closes #N` line.

Run `/done`'s tail without its handoff step or its agent-checkpoint step —
its step 5 files the agent's candidates — and move to the next ticket or
batch. That tail follows one PR's own merge, not a session interrupt, and
must never reach into another lane's live agents.

## Acceptance

`/kata 3` against a `model:sonnet` ticket #3 ends with an open PR whose body
has `Closes #3` and, when applicable, a Human-testing section — and a
worktree that is gone once that PR merges.

`/kata` over three size:tiny `model:sonnet` tickets and one plain
`model:sonnet` ticket opens two PRs, one of them with a `Closes #N` line for
all three tiny tickets.

`/kata` over one `model:haiku` ticket and one unlabelled ticket dispatches
only the first, on haiku.
