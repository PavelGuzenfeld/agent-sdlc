---
name: diagnose
description: "Diagnose something broken, hanging, flaky, or slower than before — or a bug that already resisted one fix. Builds a red feedback loop before ranking hypotheses. Skip when the cause is already visible."
---

# Diagnose

A discipline for hard bugs. Skip a phase only with an explicit reason.

## Is this the right tool?

Skip this skill and just fix it when the cause is visible on the first read: a
typo, a stack trace pointing at the line, a bug the user has already localised.
The phases cost more than the reading. Say you are skipping and why.

Reach for it when the bug has resisted one look, is intermittent, appeared between
two known-good states, or is a performance regression.

## Redact

This skill shows commands, output and captured artifacts. **Redact every secret
first**: write `<REDACTED>` in its place. Build loops against environment
variables so credentials stay in the environment rather than in what you show.
Captured artifacts carry auth headers and tokens; quote only the lines carrying
signal. If the redacted output is not enough to diagnose, say so and ask.

## Phase 1 — Build a feedback loop

**This is the skill.** Everything after it is mechanical. With a **tight** loop
that goes red on *this* bug, bisection, hypothesis testing and instrumentation all
just consume it. Without one, no amount of reading code will save you.

Spend disproportionate effort here. Exhaust the list below before concluding no
loop exists.

Keep a local, untracked notes file of per-toolchain recipes for your own stack;
this skill's phases are the discipline, not the recipe list. Ways to construct a
loop, in roughly this order:

1. **Failing test** at whatever seam reaches the bug.
2. **Curl / HTTP script** against a running service.
3. **CLI invocation** with a fixture input, diffing output against a known-good
   snapshot.
4. **Headless driver script** that drives the UI and asserts on DOM, console, or
   network.
5. **Replay a captured trace.** Save a real payload, pcap, rosbag, ulog or event
   log to disk; replay it through the code path in isolation.
6. **Throwaway harness.** A minimal subset of the system, one function call, mocked
   neighbours.
7. **Property / fuzz loop.** For "sometimes wrong output": 1000 random inputs,
   look for the failure mode.
8. **Bisection harness.** If it appeared between two known states (commit, image
   tag, dataset, firmware version), automate "boot at state X, check, repeat" so
   `git bisect run` can drive it.
9. **Differential loop.** Same input through two versions or two configs, diff the
   outputs.
10. **Human-driven loop.** Last resort, when a human must physically act — power a
    bench, click a dashboard, plug a cable. Call the Skill tool with "wizard" to
    generate the walkthrough so the loop stays structured and its captured values
    come back to you.

### Tighten it

Treat the loop as a product. Once you have *a* loop:

- **Faster.** Cache setup, skip unrelated init, narrow to one test target.
- **Sharper.** Assert the specific symptom, never "did not crash".
- **More deterministic.** Pin time, seed RNG, isolate the filesystem, freeze the
  network, fix the tile/scenario seed.

A 30-second flaky loop is barely better than none. Tighten until you will re-run it
without thinking about the cost.

### Non-deterministic bugs

The goal is not a clean repro, it is a **higher reproduction rate**. Loop the
trigger 100 times, parallelise, add load, narrow the timing window, inject sleeps.
A 50% flake is debuggable; 1% is not. Keep raising the rate until it is.

### Completion criterion

Phase 1 is done when you can name **one command** that you have **already run at
least once**, showing the invocation and its output, and that is:

- **Red-capable** — it drives the actual bug code path and asserts the user's
  *exact* symptom, so it goes red on this bug and green once fixed.
- **Deterministic** — the same verdict every run, or a pinned high repro rate.
- **Fast** — seconds, not minutes.
- **Agent-runnable** — you can run it unattended.

**Verify the baseline is green before trusting a red.** A suite already failing
makes every perturbation read as caught.

If you catch yourself reading code to build a theory before this command exists,
**stop**: jumping to a hypothesis is the exact failure this skill prevents. No
red-capable command, no Phase 2.

When you genuinely cannot build one, stop and say so. List what you tried, and ask
for one of: access to an environment that reproduces it, a redacted captured
artifact, or permission to add temporary instrumentation in place. Do not proceed
to hypothesise without a loop.

## Phase 2 — Reproduce and minimise

Run the loop. Watch it go red. Confirm:

- It produces the failure the **user** described, not a different one nearby.
  Wrong bug, wrong fix.
- It reproduces across runs, or at a rate high enough to debug against.
- You have captured the exact symptom, so later phases can prove the fix addresses
  it.

Then shrink to the **smallest scenario that still goes red**. Cut inputs, callers,
config, data and steps **one at a time**, re-running after each cut. Done when
every remaining element is load-bearing: removing any one makes it go green.

A minimal repro shrinks the hypothesis space and becomes the regression test.

## Phase 3 — Hypothesise

Generate **3 to 5 ranked hypotheses before testing any of them**. Single-hypothesis
generation anchors on the first plausible idea.

Each must be **falsifiable** — state the prediction:

> "If X is the cause, then changing Y makes the bug disappear / changing Z makes it
> worse."

A hypothesis with no prediction is a vibe. Discard or sharpen it.

**Show the ranked list before testing.** Domain knowledge re-ranks it instantly
("we changed #3 last week", "we already ruled out #1"). Do not block on it —
proceed with your ranking if nobody answers.

## Phase 4 — Instrument

Each probe maps to a specific prediction. **Change one variable at a time.**

1. **Debugger or REPL inspection** where the environment allows it. One breakpoint
   beats ten logs.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

**Tag every debug line with a unique prefix**, e.g. `[DEBUG-a4f2]`. Cleanup becomes
one grep. Untagged instrumentation survives; tagged instrumentation dies.

Watch for guards that are not guards: a runtime that strips assertions makes an
`assert` probe silently absent.

**Performance regressions take the other branch.** Logs are usually wrong there.
Establish a baseline measurement first — timing harness, profiler, query plan,
frame timestamps — then bisect against it. Measure first, fix second.

## Phase 5 — Fix and regression test

Write the regression test **before the fix**, but only if a **correct seam** exists:
one where the test exercises the real bug pattern as it occurs at the call site. A
seam too shallow to reproduce the chain that triggered the bug gives false
confidence.

**If no correct seam exists, that is itself the finding.** Note it: the
architecture is preventing this bug from being locked down. Do not write the
shallow test instead.

With a correct seam:

1. Turn the minimised repro into a failing test there.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 loop against the original, un-minimised scenario.

## Phase 6 — Cleanup

Required before declaring done:

- [ ] The original repro no longer reproduces (re-run the Phase 1 loop).
- [ ] The regression test passes, or the absence of a seam is documented.
- [ ] All `[DEBUG-...]` instrumentation removed — grep the prefix to prove it.
- [ ] Throwaway harnesses deleted, or kept somewhere clearly marked.
- [ ] The hypothesis that turned out correct is stated in the commit or PR, so the
      next person reading it learns the mechanism and not just the diff.
