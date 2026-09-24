---
description: Read the previous answer aloud through Kokoro — a spoken rendering, not a transcript.
---

# Say

Speak your immediately preceding response aloud.

## Instructions

Run `sh "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/bin/say-trigger.sh" <voice> <speed> <extra>`
and reply with one short line and nothing else — never a summary of what was
spoken. The command returns immediately; narration and playback happen outside
this conversation. If it fails, that one line is the error.

The rendering itself is generated out of context by Claude Haiku from the rules in
`${CLAUDE_PLUGIN_ROOT:-$HOME/.claude}/bin/say-prompt.md`. Do not write a rendering
yourself and do not restate those rules here — that file is the only copy.

`ctrl+shift+s` does the same thing without costing a turn: it speaks the pane's last
answer, stops playback if something is already speaking, and arms itself if the answer
was already spoken, so the next one reads itself as it lands.

## Arguments

`$ARGUMENTS` is free-form and maps onto the three positions.

**Third position, `<extra>`** — anything shaping the rendering, passed through
verbatim: "just the last paragraph", "read the commit message exactly", "shorter".
Empty renders the whole response.

**Second position, `<speed>`** — a multiplier where **higher is faster** and 1.0 is
default: "faster" is 1.2, "much faster" 1.5, "slower" 0.85, "much slower" 0.7. Clamp
to 0.5 through 2.0; outside that it is unlistenable.

**First position, `<voice>`** — default `af_heart`. American female: af_alloy,
af_aoede, af_bella, af_heart, af_jessica, af_kore, af_nicole, af_nova, af_river,
af_sarah, af_sky. American male: am_adam, am_echo, am_eric, am_fenrir, am_liam,
am_michael, am_onyx, am_puck, am_santa. British female: bf_alice, bf_emma,
bf_isabella, bf_lily. British male: bm_daniel, bm_fable, bm_george, bm_lewis. Match a
request like "a british man" or "try bella" to the closest name; if none fits, keep
the default rather than inventing one.
