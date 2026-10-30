---
description: One read-only report of open PRs, worktrees and background lanes, and gate holds, ending in what is Ready on LGTM and what Needs you. No arguments.
---

# Status

One report, read-only. Nothing is merged, pushed, killed, or filed.

## Sequence

Gather → report → close.

### Gather

**PRs.** Every open PR assigned to `@me` in this repo
(`gh pr list --assignee @me --state open`). Per PR: CI from `gh pr checks`, review
state, and one blocker — the failing check by name, the change request, a merge
conflict, or "none". A PR is *green* when every check passed on its head sha and
nothing blocks it; any other PR is *red* or *pending*, and a red one names its
failing check.

**Lanes.** `git worktree list` for this repo, and the background lanes still
running, each with its last progress line. A worktree with no live lane says so.

**Gate holds.** Tickets whose branch the mutation gate is holding: a survivor with no
waiver, an adversary finding still open, or a gated commit still running. Name the
ticket, the branch, and why, from the lane's gate log.

**Preflight.** The preflight hook's line from this session's start, if any. None
fired: print nothing for it.

### Report

One block per source, in that order, a row per item. An empty source prints one
"none" row.

### Close

End with exactly two lines.

`Ready on LGTM: #a, #b` — the green PRs' numbers as a comma list, the form `/kata`
uses when it requests LGTM. None green: `Ready on LGTM: none`.

`Needs you: ` — each red or pending PR with its failing check or blocker, each gate
hold, and each lane that stopped waiting on an answer. Nothing: `Needs you: nothing`.
