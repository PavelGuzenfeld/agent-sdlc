---
name: ps
description: "Park a tangential idea mid-task and return immediately. Use when the user says p.s., \"remind me later,\" or \"note that down,\" or raises an aside worth keeping that would derail the current work."
---

# PS

Capture a tangential ("p.s.") idea and return to what we were doing.

## Where it goes

`parked-ideas.md` in the session scratchpad directory named in your context. One
line per item, appended, each stamped with the time it was parked.

The list dies with the session. `/done` offers every line as a follow-up issue
before that happens; the drain step below is for picking one up while the session
is still live.

## With an argument

1. Append the item verbatim to `parked-ideas.md`, creating the file if absent.
2. Acknowledge in one line: `📌 queued (N): <item>`, where N is the list length.
3. **Return to whatever we were doing.** Leave the item unexpanded, unplanned and
   unstarted until it is picked up explicitly.

## With no argument

Two cases, decided by what just happened:

- A tangent was raised in the conversation and not yet parked: park that, as above.
- Nothing to park: print the current list, numbered, and stop. This is the drain
  step — reading the list is how you decide what to pick up before the session ends.

## Offering it

When you notice a tangent worth keeping rather than being asked, offer it in one
line and carry on with the current work in the same turn. A tangent worth parking
is not worth a pause.
