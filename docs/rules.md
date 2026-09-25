# Rules

How the agent is told to work. The files live in `rules/`; `mutation-gate
rules sync` writes them into a repo as `.claude/rules/*.md` and an
`AGENTS.md` block.

## At a glance

| Rule | In one line | Enforced by |
|---|---|---|
| Code clarity | No comments; docstrings of three lines at most, and only for what code can't say | `no-comments` (opt-in) |
| Diff discipline | Smallest change that satisfies the ask; stop at ~40 lines without a ticket | `diff-discipline` |
| Model V&V | Spec issue, units at every boundary, symbolic golden, consistency harness | `mutation-gate` model checks |
| Naming | Canonical dictionary words, in spoken-English order, in the kind's mold | `vocabulary` checks |
| Testing | A survivor blocks; tight bounds; slice test first; answer the adversary | `mutation-gate` |
| Tickets | Intent in the tracker; one ticket, one branch, one PR | `no-new-docs`, `diff-discipline` |
| Voice | No fluff, answer first, banned words | `commit-msg` |

The full text follows, included verbatim.

--8<-- "rules/code-clarity.md"

--8<-- "rules/diff-discipline.md"

--8<-- "rules/model-vv.md"

--8<-- "rules/naming.md"

--8<-- "rules/testing.md"

--8<-- "rules/tickets.md"

--8<-- "rules/voice.md"
