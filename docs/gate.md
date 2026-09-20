# Gate

```text
        git commit                        session Stop
            |                                  |
            v                                  v
    +---------------+                  +---------------+
    | pre-commit    |                  | Stop hook     |
    +---------------+                  +---------------+
            |                                  |
            +----------------+-----------------+
                             |   whichever runs first satisfies the other
                             v
                  +----------------------+
                  | mutation-gate        |
                  | mutates the diff,    |
                  | runs the tests       |
                  +----------------------+
                     |               |
        survivor     |               |   model_paths touched
                     v               v
    +--------------------+     +---------------------------+
    | kill it: a test    |     | spec present: MS-n lines  |
    | from the intent    |     | in the pinned issue       |
    | or waive it with   |     | each test cites an MS-n   |
    | a reason           |     | blind pass over the code  |
    +--------------------+     +---------------------------+
                     |               |
                     +-------+-------+
                             |   green
                             v
                  +----------------------+
                  | adversary            |
                  | sees intent + tests, |
                  | never the code;      |
                  | reports, no block    |
                  +----------------------+
```

A suite can be green and blind at once; only a kill rate tells them apart.
`mutation-gate` runs the diff's mutants from a pre-commit hook and from the
Stop hook. A surviving mutant blocks the commit: write the test that kills it,
from the intent rather than the code, or record a waiver whose reason names
why no test should. When the diff touches a declared model path the spec
issue must resolve, a touched model test must cite an `MS-n` line, and a
code-only blind pass reconstructs the intent for comparison. On green an
adversary that never sees the implementation reviews intent against tests and
reports into the session.

Source: `rules/testing.md`, `rules/model-vv.md`, `mutation_gate/`.
