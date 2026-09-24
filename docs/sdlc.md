# SDLC

```text
+--------------------------+
| ticket                   |   labelled `model:*`: the approved ticket is the plan
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

A **vertical slice** enters through something a real consumer actually calls
— an exported header, a CLI subcommand, a published API — rather than the
internal function that happens to implement it. It proves the feature works
end to end, the way a
[walking skeleton](https://en.wikipedia.org/wiki/Vertical_slice) does before
its internals are filled in. Unit tests then cover what the slice can't reach:
numeric edge cases, error paths, boundary values.

Source: [`rules/tickets.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/tickets.md), [`rules/testing.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/testing.md), [`rules/diff-discipline.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/diff-discipline.md).
