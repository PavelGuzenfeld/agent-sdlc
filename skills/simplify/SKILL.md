---
name: simplify
description: "Over-engineering review: reports what to delete from a diff or repo."
disable-model-invocation: true
---

# Simplify

Review for unnecessary complexity. One line per finding: location, what to cut,
what replaces it. The best outcome is the target getting shorter. Report
only — lists findings, applies nothing.

## Tiers

- Default: the current diff (recently changed code).
- `repo`: the whole tree instead of a diff. Rank findings biggest cut first.

## Tags

- `delete:` dead code, unused flexibility, speculative feature. Replacement: nothing.
- `stdlib:` hand-rolled thing the standard library ships. Name the function.
- `native:` dependency or code doing what the platform already does. Name the feature.
- `yagni:` abstraction with one implementation, config nobody sets, layer with one caller.
- `shrink:` same logic, fewer lines. Show the shorter form.
- `upstream:` workaround for behaviour a third-party OSS dependency owns — never
  our own wrappers or internal libs. Replacement: `run /upstream`.

## Hunt

Deps the stdlib or platform already ships, single-implementation interfaces,
factories with one product, wrappers that only delegate, dead flags and config,
hand-rolled stdlib.

## Format

`<file>:L<line>: <tag> <what>. <replacement>.`

End with `net: -<N> lines possible.` Nothing to cut: `Lean already. Ship.`

## Boundaries

Scope: over-engineering and complexity only. Correctness bugs, security holes,
and performance are out of scope — route them to `/complicate`. Report-only,
applies nothing.
