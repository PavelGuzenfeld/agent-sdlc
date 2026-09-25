---
description: Interview relentlessly to resolve a design, one question at a time, until the frontier is empty. `/grill plan` files the decision record and step tickets.
model: opus
---

# Grill

Interview the user relentlessly until every decision is settled.

## Argument

- `/grill` — interview only. No file is written.
- `/grill plan` — interview, then file the decision record and step tickets (see Output).

This is decided at invocation. Do not ask at the end which one it was.

## The design tree

Track the decisions as a tree: every decision branches into the ones that hang off
it. The **frontier** is every decision whose prerequisites are settled — the
questions answerable now, without guessing at answers you have not heard yet.

- Ask **one question at a time**, taking the sharpest question on the frontier.
- Give your recommended answer to every question, with the reason in a line or two.
- A question whose answer depends on one still open is not on the frontier. Hold it.
- Every answer reshapes the tree. Recompute the frontier before asking the next.
- Treat a plain answer ("a", "yes", a choice) as approve-this-and-continue: bank the
  decision and move on.

**Done when the frontier is empty**: every branch visited, nothing silently assumed.
Running out of questions is a different state — if a branch is still unexplored, the
frontier is not empty.

## Facts are yours, decisions are the user's

Finding facts is your job. A question answerable from the environment — the
filesystem, git history, a tool, the transcripts — you answer by exploring, then
report what you found. Never ask the user for something you could look up.

A running exploration is an unsettled prerequisite: it blocks only the questions
downstream of it. Ask the rest of the frontier while it runs.

## One window

Keep the interview and the plan in one context window. A summary of the interview is
a secondary source, and the interview's reasoning is what the plan converts into
decisions.

## Termination

- **`/goon`** — approve your recommended answer for **every** remaining question, end
  the interview, and finish. Inside a plain `/grill`, print the banked decisions
  inline before finishing.
- "done", "that's enough", "write it up" — the same.

## Output (`/grill plan` only)

Draft the material in the scratchpad first. Then, in the repo's own tracker:

- File one decision-record issue and pin it, the interview not retold, with
  sections:
  - **Goal**
  - **Non-goals**
  - **Decisions** — a flat numbered list; each settled decision as one line,
    one atomic, declarative statement (this is the set `/rectify` can later
    audit).
  - **Open questions** — anything left unresolved.
  - **Rejected** — one line per alternative considered and why it lost, so a
    decision is not silently reversed later.
- File one issue per implementation step, each labeled `model:<name>`,
  assigned to `@me`, each linking back to the decision-record issue.
- Print the numbers of every issue filed.
