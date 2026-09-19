# Pre-registration — filter consistency

For anything scored by comparing an estimator's own error claim against its
measured error. Committed before the run that produces the numbers.

Fill every field. A blank is not "not applicable" — it is a band you can move
afterwards.

---

## Under test

- **Estimator:**
- **Commit / build:**
- **Mechanism this tests** (verdict id from `diff.md`):
- **What a fail would mean:**

## Statistic

- **Statistic:** NEES / NIS / other —
- **State or innovation dimension:**
- **Degrees of freedom:**
- **Averaged over how many runs (M):**
- **Effective DOF:** `M x dim` for an M-run average, `dim` for a single run

A NEES band without a stated DOF is unfalsifiable — any window can be made to pass.

## Window

- **Window length N (samples):**
- **Start condition:** what marks the window open — time, event, convergence test
- **Excluded intervals** and why (initialisation transient, manoeuvre, dropout):

Exclusions are declared here or not at all. Cutting a window after seeing the
result is the failure this document exists to prevent.

## Acceptance

- **Significance alpha:**
- **Two-sided chi-square interval:** `[ lower / M , upper / M ]` at the effective
  DOF above — write the computed numbers, not the formula
- **Pass:** the statistic lies inside the interval for at least ___ % of windows
- **Fail:** outside on the ___ side for at least ___ % of windows

Note the direction. Consistently high means the filter is overconfident — its
covariance is too small. Consistently low means it is conservative. These have
different causes and the distinction is lost if only "outside" is recorded.

## Inconclusive

The band this document exists to pin down. Without it, "run more sequences" is a
decision made after seeing which way the result leans.

- **Inconclusive when:**
- **Pre-committed next action:**
- **Cap:** after this much additional data, an inconclusive result is reported as
  inconclusive and the mechanism is set aside —

## Data

- **Sequences / logs:**
- **Seeds:**
- **Anything that must be regenerated rather than reused, and why:**

---

*Committed before results exist. Results go in `results.md` as a separate commit.*
