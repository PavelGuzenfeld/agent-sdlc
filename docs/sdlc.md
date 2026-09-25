# SDLC

From an approved ticket to a squash merge.

[TOC]

## The flow

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
| implement the slice      |   smallest change that satisfies the ticket
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

## The rules behind it

| Rule | What it means in practice |
|---|---|
| Intent lives in the tracker | Design notes go in the ticket; a new `.md` file in the tree is blocked |
| An approved ticket is the plan | The `model:*` label is the approval |
| One ticket, one branch, one PR | Branch `42-slug`, PR body `Closes #42` |
| No ticket, no change past ~40 lines | `diff-discipline` blocks the commit |
| Red slice test first | Watched failing for the right reason before any code |
| The gate runs before the commit lands | A survivor blocks |
| Squash-only merges | The branch is deleted on merge |

## A ticket, end to end

```bash
gh issue create -t "is_adult accepts 17" -b "Expected: 18 is the first adult age."
# triage: add the label, which is the approval
gh issue edit 42 --add-label model:sonnet
```

```text
/kata 42
```

- The worker branches `42-is-adult-boundary` off `origin/main`.
- It writes `test_eighteen_is_the_first_adult_age`, watches it fail, then
  fixes the code.
- The commit runs the gate; a survivor sends it back to the test.
- It opens the PR with `Closes #42` and waits for CI.
- You read it and type `LGTM`; it squash-merges and removes the worktree.

## Vertical slice

- A slice test enters through something a real consumer calls: an exported
  header, a CLI subcommand, a published API.
- It proves the feature works end to end, like a
  [walking skeleton](https://en.wikipedia.org/wiki/Vertical_slice) before
  its internals are filled in.
- Unit tests then cover what the slice can't reach: numeric edge cases,
  error paths, boundary values.

Source: [`rules/tickets.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/tickets.md), [`rules/testing.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/testing.md), [`rules/diff-discipline.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/diff-discipline.md).
