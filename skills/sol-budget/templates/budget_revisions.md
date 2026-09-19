# Budget revisions

The only way past a failing `budget_check.py`. One row per node, dated, with a reason
that names why the old budget was wrong — not why the code is slow.

A reason that restates the overrun ("node takes 6 ms, budget was 4 ms") is not a
reason. Neither is "acceptable for now" without the ceiling it hits and the trigger to
revisit. If the graph changed, the answer is a re-derived SOL, not a revision.

| date | node | allowed p99 (ms) | reason |
|---|---|---|---|
| YYYY-MM-DD | <node> | <ms> | <why the derived budget was wrong> |
