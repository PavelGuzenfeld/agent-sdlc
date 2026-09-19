---
description: Clear this session's running state and free disk. Tiered — bare is session-scoped, `space` prunes build cache and dangling images, `all` stops everything and prunes volumes.
---

# Cleanup

Clear what this session started, and free what is safe to free. Always print what is
being cleared before clearing it.

## Tiers

- **bare `/cleanup`** — this session only. Background tasks, artifact watches, the
  scratchpad, and containers this session started.
- **`space`** — the above, plus `docker builder prune` and dangling images. Reclaims
  the most for the least risk: no data is lost, only rebuild time.
- **`all`** — the above, plus stop every container and prune volumes. Destructive.
  **Print the exact kill-list first** — which containers, volumes and images will be
  destroyed — and proceed only after showing it. The explicit word is the intent, but
  `all` is never blind.

## Sequence

Enumerate → print → clear → report.

### Enumerate and print

Never clear anything you have not first listed. For `all`, the printed list is the
kill-list and it comes before any destruction.

### Clear

**Background tasks.** List them. Kill finished and idle ones without asking. If one is
still actively running, name it and ask before killing that one — a long build dying
unannounced is the failure worth one round-trip.

**Artifact watches.** Stop them. They are session-local and hold nothing.

**Scratchpad.** Remove its contents and report the size freed. Check for anything that
is the last local copy of something before deleting it — if a scratch clone holds
history that exists nowhere else, say so instead of removing it.

**Containers.** Bare `/cleanup` stops only containers this session started. Containers
belonging to another workspace are not yours: name them, leave them running, and say
whose they are. Only `all` touches them, and only after the kill-list.

### Report

Space reclaimed, from `docker system df` before and after. What was left alone, and
why.

## Out of scope

Git worktrees and branches. Squash-merged PRs never look merged locally, so
`git branch --merged` is not a usable signal — correct pruning needs per-branch PR
state and judgment about unpushed work and locked worktrees. That is a deliberate
task, not a reflex.
