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
