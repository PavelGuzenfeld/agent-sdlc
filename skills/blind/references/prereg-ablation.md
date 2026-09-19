# Pre-registration — ablation

For anything scored by comparing variants on a metric. Committed before the run
that produces the numbers.

Fill every field. A blank is not "not applicable" — it is a threshold you can move
afterwards.

---

## Under test

- **Mechanism this tests** (verdict id from `diff.md`):
- **Claim:** which variant should win, and by how much
- **What a fail would mean:**

## Variants

One row per variant. The baseline is a row, not an assumption.

| id | variant | what changes | expected direction |
|----|---------|--------------|--------------------|
| V0 | baseline | — | — |

Change one thing per row. A variant that moves two things cannot attribute its
own result.

## Metric

- **Primary metric:** exactly one
- **Definition:** how it is computed, including what counts as a failure case
- **Direction:** higher or lower is better
- **Secondary metrics** (reported, never used to decide):

One primary metric, chosen now. Choosing among several afterwards is choosing the
one that agreed.

## Data

- **Sequences / scenarios:**
- **Count (N):**
- **Seeds:**
- **Held-out set, if any:**
- **Selection rule:** how these were chosen, and what was excluded

If the sequences were picked because a variant already did well on them, the
result is not measuring the variant.

## Acceptance

- **Effect size that counts as real:** absolute or relative —
- **Pass:** the variant beats baseline by at least that margin on at least ___ of
  ___ sequences
- **Fail:** does not clear the margin, or loses on ___ or more sequences
- **Regression guard:** a secondary metric that must not degrade by more than —

An effect smaller than run-to-run variance is not an effect. If variance is
unknown, measure it before writing the margin.

## Inconclusive

- **Inconclusive when:** the margin is cleared on some sequences and lost on
  others, without —
- **Pre-committed next action:**
- **Cap:** after this many additional sequences, an inconclusive result is
  reported as inconclusive and the mechanism is set aside —

## Environment

- **Commit / build:**
- **Hardware:**
- **Anything that must be held fixed across variants:**

---

*Committed before results exist. Results go in `results.md` as a separate commit.*
