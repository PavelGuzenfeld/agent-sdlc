# Reporting

```text
                     what do you have?
                             |
        +--------------------+--------------------+
        |                    |                    |
        v                    v                    v
+---------------+    +---------------+    +---------------+
| bug           |    | feature       |    | question      |
+---------------+    +---------------+    +---------------+
        |                    |                    |
        v                    v                    v
  title is the defect    the outcome you       Discussions
  repro steps            want, not the
  expected vs actual     change you would
  evidence               make, and why
        |                    |
        +---------+----------+
                  |
                  v
        +-------------------+
        | triage            |   `model:*`: approved, and which model runs it
        +-------------------+
                  |
                  v
        one branch, one PR, `Closes #N`
```

A bug report names the defect in the title, then gives the repro, expected
versus actual, and the evidence. A feature request names the outcome and why,
never the change you would make. Questions go to Discussions, not the
tracker. Triage adds a `model:*` label once the ticket is the plan — the
label names who runs it and is itself the approval; from there the SDLC
chart applies. No preamble, no restated brief, no closing summary.

Triage itself uses two skills, depending on how settled the ask already is.
A raw idea with open questions goes through
[`/grill`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/commands/grill.md):
one question at a time, recommended answer first, until nothing is left
unresolved; `/grill plan` files the result as a decision record plus one
step ticket per unit of work, each already labelled `model:*`.
An ask that's already well-scoped skips straight to labelling. Either way,
[`/kata`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/commands/kata.md)
is what actually dispatches a `model:*`-labelled ticket: one branch, one PR,
wait for review, squash-merge on `LGTM`.

Source: [`.github/ISSUE_TEMPLATE/`](https://github.com/PavelGuzenfeld/agent-sdlc/tree/main/.github/ISSUE_TEMPLATE), [`CONTRIBUTING.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/CONTRIBUTING.md), [`rules/tickets.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/tickets.md),
[`rules/voice.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/voice.md).
