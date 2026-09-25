# Reporting

How to file a bug, a feature request or a question, and what happens next.

## Pick the form

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

## What goes in each

| Form | Title | Body |
|---|---|---|
| Bug | The defect, stated flat | Repro, expected vs actual, evidence |
| Feature | The outcome you want | Why; never the change you would make |
| Question | — | Discussions, not the tracker |

- No preamble, no restated brief, no closing summary.

A bug report that works:

```text
Title: rules check passes on a repo with no AGENTS.md

Repro:    rm AGENTS.md && mutation-gate rules check; echo $?
Expected: non-zero, "AGENTS.md: missing"
Actual:   0
Evidence: mutation-gate 0.1.1, clean clone of main
```

## Triage

- Triage adds a `model:*` label once the ticket is the plan. The label names
  who runs it and is itself the approval.
- A raw idea with open questions goes through
  [`/grill`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/commands/grill.md):
  one question at a time, recommended answer first. `/grill plan` files a
  decision record plus one step ticket per unit of work.
- A well-scoped ask skips straight to labelling.
- [`/kata`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/commands/kata.md)
  dispatches a labelled ticket: one branch, one PR, wait for review,
  squash-merge on `LGTM`. See [SDLC](sdlc.md).

Source: [`.github/ISSUE_TEMPLATE/`](https://github.com/PavelGuzenfeld/agent-sdlc/tree/main/.github/ISSUE_TEMPLATE), [`CONTRIBUTING.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/CONTRIBUTING.md), [`rules/tickets.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/tickets.md),
[`rules/voice.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/voice.md).
