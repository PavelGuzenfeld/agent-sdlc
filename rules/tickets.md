# Tickets

Intent-bearing prose lives in the repo's own tracker, never in the tree. A file
survives only if something other than a human reads it — CI config, lint config,
a gate config — or it is README, LICENSE, or CONTRIBUTING. Never write a design
doc, an RFC, or a decision log as a file in the repo; open a ticket and point to
it instead.

This binds this repo. An upstream tree keeps its own doc conventions.

## Model spec

model-vv.md Layer 0 no longer defaults to a file. Its `MS-n` lines live in one
pinned ticket, named by `model_spec = "issue:N"` in the repo's own gate config.
Where the tracker itself lives is that repo's business, never named in a rule
file.

## One ticket, one branch, one PR

An approved ticket is the plan, and satisfies diff-discipline's stop on its own
— no ticket, no change past the line-count limit; open one first. A ticket maps
to exactly one branch and one PR, and the PR body carries `Closes #N`. This
repo defaults to squash-only merges with delete-branch-on-merge.

The one carve-out: a batch of confirmed `size:tiny` follow-ups may share one
worker, one branch and one PR, with a `Closes #N` line per ticket.

## Follow-ups

A follow-up starts from `/done`, a kata worker, any agent mid-task, or the
maintainer — this section binds all of them, and nowhere else restates it.

Every follow-up carries `follow-up` and exactly one category: `correctness`,
`clarity`, `security`, `performance`, or `scope`. `scope` covers work deferred
with nothing broken — a deferred scope, an added `TODO`/`FIXME`, a waiver, a
parked idea. `bug` never goes on a follow-up; it stays the outside-reporter
form's label.

The filer proposes `size:tiny` when the ticket is tiny: its evidence names
one location, it leaves no design choice open, and it needs no new file,
dependency or config key. The maintainer confirms the proposal by adding its
model label. A follow-up is never born with a `model:<name>` label, and a
label-creation step must never add one to an untriaged follow-up.

Labels are created if missing; if creation is refused, file without them
rather than drop the item.
