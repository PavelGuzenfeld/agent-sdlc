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
[**Mutation testing**](https://en.wikipedia.org/wiki/Mutation_testing) seeds
small, deliberate bugs (mutants) into the diff and reruns the tests: a mutant
the suite doesn't catch is a bug the suite wouldn't catch either. `mutation-gate`
runs this from a pre-commit hook and from the Stop hook. A surviving mutant
blocks the commit: write the test that kills it, from the intent rather than
the code, or record a waiver whose reason names why no test should. When the
diff touches a declared model path the spec issue must resolve, a touched
model test must cite an `MS-n` line, and a code-only blind pass reconstructs
the intent for comparison.

On green, an **adversary** — an isolated review shown the intent and the
tests, never the implementation — checks whether the tests actually assert
the requirement or just match what the code happens to do. It reports into
the session; it never blocks.

Source: [`rules/testing.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/testing.md), [`rules/model-vv.md`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/rules/model-vv.md), [`mutation_gate/`](https://github.com/PavelGuzenfeld/agent-sdlc/tree/main/mutation_gate).
