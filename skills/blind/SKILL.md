---
name: blind
description: "Two-pass blind vs informed hypothesis test; the difference between the rankings is the finding."
disable-model-invocation: true
---

# Blind

Two ranked lists of mechanisms, produced under different information, and the
difference between them.

You adjudicate — you are the one who can go to the bench. This skill generates
widely and hands you discriminating measurements. It is not a neutral judge.

## Why it is built this way

Suppressing a hypothesis already in context does not work. So the blind pass is
never *told* to ignore anything: it runs in a process that never receives it.

Every guard here is structural. Nothing relies on an agent choosing to obey.

| Leak | Closed by |
|---|---|
| memory index of solved mechanisms | separate process, neutral cwd |
| user rules and CLAUDE.md | `--restricted` |
| skills firing and injecting method | `--disable-slash-commands` |
| reading outside the bundle | `--restricted` confines file tools to cwd |
| branch names, commit messages | export with no `.git` |
| plan docs, issues, prior runs | export exclusions |

## Run — `/blind <workstream>`

### 1. Manifest

`mkdir -p <work>/evidence`, then ask for, and write to `<work>/manifest.md` — the blind pass reads it and can only
read inside `<work>`. Copy it to `<record>/manifest.md`, which is the committed
copy.

- **One symptom line.** What was observed. Not what you think causes it.
- **Evidence artifacts** — logs, plots, CSVs, bags. Copy each into
  `<work>/evidence/` and record the in-run path. Copy unconditionally, even when
  the artifact is also tracked in the repo; otherwise the audit trail names a path
  the agent did not use.
- **The pin** — the commit the evidence was captured from.
- **Capture-tree dirtiness.** Record whether the tree was clean at capture, and
  what was modified if not. A dirty tree means the pin names code that is not
  quite the code that ran.

- **Untracked dependency.** Run at the pin:

  ```
  git -C <repo> status --porcelain --untracked-files=all
  ```

  Subtract `git -C <repo> ls-tree -r --name-only <pin>`. What remains is what the export silently drops.
  Show that list and ask which entries were load-bearing for the capture. An
  export missing a load-bearing path diagnoses code that did not produce the data.

- **Hypothesis-term hits.** You hold the hypothesis; the blind process never will.
  So `git -C <repo> grep -n -e <term> <pin>` for its terms — mechanism names, component names — and show
  the hits. Ask which paths to withhold. Record the answer.

  Identifiers still leak, and measurably more than by nudging a ranking. In an
  A/B where two trees differed only in naming, the loaded arm asserted a sensor
  dropout that appeared nowhere in the evidence — 14 mentions per run against
  zero in the neutral arm — and pinned that mechanism first every time, where the
  neutral arm ranked it 1st, 2nd and 5th. A name introduces an entity.

  So rename nothing to hide it. The table's `support` column carries `observed` or
  `assumed: <condition>` instead, and an `assumed` row citing something the
  evidence never shows is a candidate identifier leak, not a finding.

  **That guard is partial and the rate is measured, not assumed.** Over ten runs
  it caught the injected entity 7 times; the column was filled every time, but
  three runs called it `observed` when the condition appeared nowhere in the data.
  An inline marker rather than a column managed 4 of 10. So read the `observed`
  rows too — roughly one leak in three arrives wearing the wrong label. Say in the
  manifest that identifiers were not sanitised.

### 2. Freeze

Manifest and pin are now fixed. Nothing downstream may edit either. A pin chosen
after the informed pass is a pin the informed reasoning selected.

### 3. Informed pass — main session

Runs **first**. A subagent's report returns to its parent, so a blind pass running
first would leave its ranking in context while the informed table was written.

Write the table from `references/schema.md` using the full domain context: the
hypothesis, the repo history, the issues, everything. IDs are `I1..In`.

Write it to `<record>/informed.md` before spawning anything.

### 4. Blind pass and rejection review — parallel

**Blind.** Build the working root, then run it out of process:

```
mkdir -p <work>/tree
git -C <repo> archive --format=tar <pin> -- . \
  ':(exclude)docs/hypotheses' <accepted exclusions> | tar -x -C <work>/tree
cd <work> && claude -p \
  --restricted --disable-slash-commands --strict-mcp-config \
  --tools Read Grep Glob \
  --system-prompt-file ~/.claude/skills/blind/references/blind-prompt.md \
  "$(cat manifest.md)" < /dev/null > <record>/blind.md
```

`docs/hypotheses` is excluded unconditionally — it is this skill's own output, so
run N would otherwise ship runs 1..N-1.

The blind process gets no memory, no rules, no skills, no MCP, and file tools it
cannot point outside `<work>` — verified: a read by absolute path outside the
working root is refused.

`--tools` is an allowlist, not a denylist, and that is deliberate. `--restricted`
alone leaves `WebSearch`, `Agent` and the messaging tools in place; web access
breaks the premise that everything relevant is in the bundle, and an `Agent` child
may inherit none of these restrictions. Naming the three tools the pass needs
survives new tools being added; a denylist does not.

**Rejection.** In-process subagent, full prose access, working root plus the
issues and plan docs the blind pass is denied. It holds the hypothesis by design;
blinding it protects nothing and costs it the history that makes a review sharp.

Give it a generation target, never a prohibition:

> Write the review that rejects this hypothesis. Name the failure mode that shows
> first in flight data. State the measurement that would already have caught it.

Write to `<record>/rejection.md`.

### 5. Difference

Map `B` ids to `I` ids under one criterion: **same predicted signature and same
discriminating measurement**. Anything else is a different mechanism wearing a
similar name. The informed pass never saw the blind ids and cannot do this itself.

Then assign the five verdicts from `references/schema.md`. Write
`<record>/diff.md`.

### 6. Pre-registration

The verdicts name measurements. Pick which to run, then write the matching
template — `references/prereg-filter-consistency.md` or
`references/prereg-ablation.md` — and commit it **as its own commit, before any
result exists**. The commit boundary is what makes "pre-registered" checkable
later.

## Score — `/blind close <record-dir>`

Read the pre-registration **before** asking for any numbers. Then take the
measured values and mark each band pass, fail or inconclusive **as written**. The
band is not renegotiated after the fact; that is the whole point of writing it
down first.

Record which mechanism the bench actually implicated, and whether it came from the
blind list, the informed list, or neither. **Neither** is the finding that
justifies running this at all.

Commit as a second commit in the record dir.

## Layout

Two locations, deliberately.

```
<record>  <repo>/docs/hypotheses/<date>-<slug>/   committed
          manifest.md informed.md blind.md rejection.md diff.md
          prereg.md results.md

<work>    <scratchpad>/blind/<date>-<slug>/       never committed
          tree/       export at the pin, no .git
          evidence/   copied artifacts
```

The export must not live in the repo it came from — committed it duplicates the
tree, untracked it corrupts the untracked accounting step 1 depends on.

The gate's no-new-docs check blocks `<record>` until the repo's
`.mutation-gate.toml` has a `[[doc_allow]]` for `docs/hypotheses/**` whose
reason names blind records as evidence, not a decision log.

## Blinding is a trade

It buys independence and costs the domain knowledge that makes a candidate list
useful. The blind pass is not the better pass. A blind list full of generic
failure modes means the bundle was too thin, not that the mechanisms are ranked
right.
