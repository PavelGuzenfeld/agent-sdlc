# Debugging

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

`/diagnose` is for bugs that resisted one look. Phase 1 is the skill: a
command that drives the real code path and asserts the exact symptom, fast
and deterministic, run at least once before any theory. No red-capable
command, no hypotheses. The repro shrinks until every element is
load-bearing, then three to five ranked, falsifiable hypotheses are tested one
variable at a time. The regression test goes in before the fix, at a seam
that reaches the real bug pattern; when no such seam exists, that is the
finding.

Source: `skills/diagnose/SKILL.md`.
