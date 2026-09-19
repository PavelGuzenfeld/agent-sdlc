---
description: Multi-lens code review reporting deep refactor opportunities and technical debt. Report-only — the strategic counterpart to /simplify.
---

# Complicate

Review code from multiple aspects and report the deep, structural work — the hard
stuff `/simplify` deliberately leaves alone. **Report only. Change nothing.**

## Scope

- If `$ARGUMENTS` names a target (file / module / subsystem), review that.
- Otherwise, review the current diff (recently changed code).

## Instructions

1. Review the target through several lenses, one pass each:
   - **correctness** — latent bugs, edge cases, silent-failure paths,
   - **style / clarity** — naming, altitude, dead code, duplication,
   - **security** — unsafe patterns, secrets, input handling,
   - **performance** — hot paths, allocations, complexity.
2. Synthesize the passes into one report. Do not edit any files.

## Output

```
COMPLICATE REPORT: <target>

Recommendations        (what to act on now, ranked)
Deep refactors         (structural opportunities; each with rationale + rough effort)
Technical debt         (inventory: what's owed, where, and the risk of leaving it)
```

For each item, give the file:line, the problem, and the proposed direction. This is a
map for later work — the user approves a subset with `/goon`; do not start applying
changes yourself.
