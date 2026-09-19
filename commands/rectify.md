---
description: Auto-fix internal inconsistencies in a doc/plan against code, logs, or other docs. Asks per conflict, applies the fix, shows one diff at the end.
---

# Rectify

Find and fix internal inconsistencies in a target document or plan.

## Target and context

- If `$ARGUMENTS` names files: the **first** is the target to fix; the **rest** are
  context sources to check it against (code repo, other docs, logs).
- If `$ARGUMENTS` is empty: the target is the plan/doc under discussion in this
  conversation, and the context is the current repository. Ask only if ambiguous.

## Instructions

1. Read the target and all context sources.
2. Find every contradiction:
   - internal (the doc disagrees with itself — e.g. section 2 vs section 5),
   - doc-vs-reality (the doc claims something the code / config / logs contradict),
   - doc-vs-doc (the target disagrees with a referenced external doc).
3. Rank findings by severity, and split them into two tiers:
   - **Verified** — you named a verifier and ran it: the grep, the test
     invocation, the config dump, the log query. Show the command and its output.
   - **Suspected** — you read something and it looked wrong. Report it as a
     suspicion, in its own tier, and say what would settle it.

   A doc-vs-reality claim reaches the verified tier only with a run command
   behind it. Reading the code establishes what you think it says; the command
   establishes what it does, and those come apart exactly where a doc has
   drifted. Assert absence with a command too — grep for what should be *gone*,
   not only for what should be there.
4. For **each** contradiction, one at a time, verified tier first:
   - State exactly which sources conflict and quote the conflicting text.
   - For a verified finding, show the verifier's output alongside the quote.
   - Recommend which side is authoritative and why.
   - **Ask the user which side wins.** Do not guess.
   - Apply the fix the user chose to the target.
5. After all conflicts are resolved, show a single **consolidated diff** of every
   change made to the target, then list any suspected findings left unverified.

Nothing is fixed silently. Every judgment call goes through the user.
