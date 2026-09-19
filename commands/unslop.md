---
description: Strip AI speech artifacts and rewrite text in a plain, unpolished human voice. Removes AI-attribution and Co-Authored-By lines unconditionally.
---

# Unslop

Rewrite text to remove AI speech artifacts. Output plain, short, declarative prose —
the way a terse human writes, not a "professional" assistant.

## Target

- If `$ARGUMENTS` is a file path or pasted text, rewrite that.
- Otherwise, rewrite the most recent draft produced in this conversation (commit
  message, PR body, comment, doc).

## Instructions

1. Rewrite the text directly. Remove AI tells: hedging preambles, filler intensifiers,
   throat-clearing, tricolon padding, formulaic openings/closings, and any phrasing
   that reads as machine-generated. Keep the meaning; cut the polish.
2. **Unconditionally remove** any AI-authorship signal: "Generated with Claude Code"
   (or equivalents), `Co-Authored-By: Claude ...` (or any model/agent) trailers, and
   any credit to Claude / an AI model. These are never allowed regardless of style.
3. Show the result. For a file, also show a diff.
