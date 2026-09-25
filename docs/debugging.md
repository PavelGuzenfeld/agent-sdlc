# Debugging

How `/diagnose` works a bug that resisted one look.

[TOC]

## The loop

```text
+-----------------------------+
| 1  build a red loop         |   one command, already run, red on this bug
+-----------------------------+
               |
               v
+-----------------------------+
| 2  reproduce, minimise      |   cut one thing at a time; keep the load-bearing
+-----------------------------+
               |
               v
+-----------------------------+
| 3  rank 3-5 hypotheses      |   each with a falsifiable prediction
+-----------------------------+
               |
               v
+-----------------------------+
| 4  test one                 | <-------+
+-----------------------------+         |
       |               |                |
       | confirmed     | refuted        |   next hypothesis
       v               +----------------+
+-----------------------------+
| 5  regression test, fix     |   test first, watch it fail, then the fix
+-----------------------------+
               |
               v
+-----------------------------+
| 6  verify, clean up         |   original loop green, `[DEBUG-...]` lines gone
+-----------------------------+
```

## Phase 1 is the skill

- A red loop is one command that drives the real code path and asserts the
  exact symptom. It is fast, deterministic, and has been run at least once.
- No red-capable command, no hypotheses.

```bash
pytest -q tests/test_parser.py::test_empty_header_is_rejected
```

- Good: it names the symptom, runs in seconds, and is red on this bug today.
- Not a loop: "run the app and look at the log", or a test that passes.

## Then

| Phase | Rule |
|---|---|
| Minimise | Cut one thing at a time until every element is load-bearing |
| Hypotheses | Three to five, ranked, each with a falsifiable prediction |
| Test | One variable at a time |
| Regression test | Before the fix, at a seam that reaches the real bug pattern |
| Clean up | The original loop is green; every `[DEBUG-...]` line is gone |

- When no test seam reaches the bug, that is the finding.

Source: [`skills/diagnose/SKILL.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/skills/diagnose/SKILL.md).
