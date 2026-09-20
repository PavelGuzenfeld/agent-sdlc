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
        | triage            |   `ready`: approved, the ticket is the plan
        |                   |   `model:*`: which model runs it
        +-------------------+
                  |
                  v
        one branch, one PR, `Closes #N`
```

A bug report names the defect in the title, then gives the repro, expected
versus actual, and the evidence. A feature request names the outcome and why,
never the change you would make. Questions go to Discussions, not the
tracker. Triage adds `ready` once the ticket is the plan and a `model:*`
label for who runs it; from there the SDLC chart applies. No preamble, no
restated brief, no closing summary.

Source: `.github/ISSUE_TEMPLATE/`, `CONTRIBUTING.md`, `rules/tickets.md`,
`rules/voice.md`.
