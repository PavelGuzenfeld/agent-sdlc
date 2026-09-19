# Testing

A suite can be green and blind at the same time. Structure cannot tell the two
apart — tight tests, real assertions, property tests and golden oracles all
survive the distinction. Only a kill rate separates them.

Measured 2026-09-10 on a mature, well-shaped suite: **57%** of real bug-class
mutants survived, four of six survivors sitting in a blind spot the tests
documented as deliberate policy.

## The gate is not optional

`mutation-gate` runs from a pre-commit hook and from the Stop hook. Whichever
runs first satisfies the other. Never `--no-verify`, never `--no-adversary`
outside debugging the pack itself.

A surviving mutant blocks. Two ways forward, no third:

- write the test that kills it — **from the intent, not from the code**, or
- record it in `.mutation-gate-waivers.toml` with a reason that names why no
  test can or should kill it.

"I could not think of a test" is not a reason. A waiver whose reason restates
the mutation is not a reason.

A slice test counts as a covering test for the diff, same standing as any unit
test — the gate does not care which kind killed the mutant.

Spec and all 29 decisions: `PavelGuzenfeld/dotfiles#9`.

## Writing tests the gate will not embarrass

**Assert the tight bound.** `assert x > 0` where the spec says `x == 4.5` passes
on every wrong answer above zero. Pin the value the requirement names.

**Test the contact boundary, do not avoid it.** Float error at a boundary is a
reason to choose exact-representable inputs, not a reason to test only the
"clearly separated" and "clearly overlapping" regimes. Coordinates and sizes
that are exact in binary floating point make `<=` versus `<` observable. Every
boundary you skip is a mutant that will survive.

**No tolerance without a stated reason.** `pytest.approx` and `ASSERT_NEAR` need
the epsilon justified — a unit, an accumulated-error budget, a spec clause. An
unexplained tolerance is a hole sized to whatever the implementation happened to
produce.

**Name the failure mode, not the function.** A test called
`test_obb_circle_overlap` asserts whatever the code does. One called
`test_circle_touching_corner_at_zero_heading_overlaps` asserts a requirement.

**One failure mode per test.** Volume is not the problem — 1044 tests at a median
of 12 lines is fine. Many tests pointed at one failure mode is the problem, and
the waiver file will show you where that happened.

## Vertical slice first

**One slice test per ticket.** Enter where a real consumer enters — an exported
header, a CLI subcommand, a topic, a published API — and assert the
user-visible outcome named in the ticket's acceptance line, not the function
that happens to implement it.

**Unit tests fill in behind it.** Reserve them for what the slice cannot
reach: numeric kernels, boundary values, error paths, property tests. A unit
test that only re-exercises what the slice already covers earns nothing.

**Red first, always.** Write the slice test before the implementation and
watch it fail for the right reason. A test that was never red proves nothing —
it could pass against the unmodified tree.

## Adversary protocol

When the gate goes green, the pack spawns an isolated review that sees the
intent and the tests but **never the implementation**. It reports into the
session; it never blocks.

Take its findings seriously — it is the only reader in the loop that was not
anchored by the code. Respond to each one: fix it, or say why it is wrong. Do
not silently skip them because the gate already passed; green is exactly when
nothing else is looking.

Never feed it your own summary of the diff. That summary is derived from the
diff and can only agree with it. Intent comes from a ticket, a spec, or the
user's own words.

Model changes also run `model-vv.md` — its blind pass is the opposite blindfold: code, no spec.
