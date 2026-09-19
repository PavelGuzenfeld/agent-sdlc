# Output contract

Both passes emit the same table. That is what makes the difference mechanical
instead of narrative.

| id | mechanism | support | predicted signature | discriminating measurement | where that measurement runs |
|----|-----------|---------|--------------------|-----------------------------|------------------------------|

`support` is `observed` or `assumed: <condition>`. A row marked `assumed` for a
condition the evidence never shows is a candidate identifier leak — the source
named an entity the data does not contain — not a finding. Treat it as one when
the informed pass adopts it.

The last column is where the *new* measurement would be taken — bench, simulation,
or an existing capture that already holds it. Not a citation of evidence in hand.

Blind ids are `B1..Bn`. Informed ids are `I1..In`.

**Ids are never shared.** The informed pass has not read the blind table and so
cannot know whether its candidate is the same mechanism. Letting it reuse an id
would fabricate a match, and "survived" would then mean nothing.

Rank order carries meaning. Row 1 is the most likely mechanism, not the first one
thought of.

A row whose discriminating measurement is `none` stays in the table. A mechanism
that cannot currently be falsified is a finding about the instrumentation.

## Matching

The difference step maps `B` ids to `I` ids under one criterion:

> same predicted signature **and** same discriminating measurement

Same name is not a match. Two mechanisms can share a label and predict different
things; those are different rows.

## The five verdicts

Assign one per mechanism. Every verdict names the next measurement.

**1 — Converged.** Your candidate was already ranked high blind.

Strong support for the mechanism: the data alone implies it. Zero credit to your
domain reasoning, which added nothing the evidence did not already carry. Do not
read this as weak evidence *for the mechanism* — it is weak evidence that the
context was load-bearing.

*Next:* run its discriminating measurement. It is the cheapest confirmation
available.

**2 — Promoted.** Informed lifted a candidate the blind pass ranked low.

The promotion rests on a domain fact the data does not carry. Name that fact
explicitly. It is now the thing under test, more than the mechanism is — if the
fact is wrong the promotion evaporates.

*Next:* test the fact, not the mechanism.

**3 — Dropped silently.** The blind pass found a mechanism the informed pass never
mentions.

The highest-value verdict in the run. Silence is where bias hides: a mechanism
ruled out without an argument was ruled out by familiarity. Either state the
reason it does not apply, or treat it as live.

*Next:* run its discriminating measurement, unless a stated reason survives
scrutiny.

**4 — Informed only.** A mechanism the blind pass could not have reached.

It rests entirely on context absent from the data. That is legitimate — it is what
the informed pass is for — but it is also unfalsifiable from the evidence in hand.

*Next:* name what would have to be captured for the data to speak to it.

**5 — Blind only, unexplained.** A blind mechanism the informed pass neither
adopted nor argued against, and which no domain fact excludes.

*Next:* run its discriminating measurement.

## Reading the result

If every verdict is **Converged**, the domain context contributed nothing this run.
That is a real finding about the problem, not a failure of the protocol.

If most are **Informed only**, the bundle was too thin to test anything. Capture
the measurements the blind pass listed as missing, and run it again.
