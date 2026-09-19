# SDLC

```text
+--------------------------+
| ticket                   |   labelled `ready`: the approved ticket is the plan
+--------------------------+
             |
             v
+--------------------------+
| branch                   |   one ticket, one branch, one PR
+--------------------------+
             |
             v
+--------------------------+
| red slice test           |   enters where a real consumer enters; fails first
+--------------------------+
             |
             v
+--------------------------+
| implement, <= 40 lines   |   smallest change that satisfies the ticket
+--------------------------+
             |
             v
+--------------------------+
| mutation gate            |   pre-commit or Stop hook; a survivor blocks
+--------------------------+
             |
             v
+--------------------------+
| PR, `Closes #N`          |   CI green
+--------------------------+
             |
             v
+--------------------------+
| review, squash merge     |   branch deleted on merge
+--------------------------+
```

Intent lives in the tracker, never in the tree. An approved ticket is the
plan and maps to exactly one branch and one PR. The first code written is a
slice test at a seam a real consumer uses, watched failing for the right
reason; unit tests fill in behind it. Past about 40 request-driven lines with
no ticket, the work stops and a ticket gets written. The gate runs before the
commit lands, the PR body carries `Closes #N`, and merges are squash-only.

Source: `rules/tickets.md`, `rules/testing.md`, `rules/diff-discipline.md`.
