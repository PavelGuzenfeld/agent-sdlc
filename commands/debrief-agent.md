---
description: Post-session review that proposes changes to the agent's environment — never to the code. Nine lenses over the transcript, ranked findings, filed through /done's gate on request.
---

# Debrief agent

Review one session's transcript and propose changes to the environment it ran
in: rules, hooks, skills, memory, permissions. Never propose a code change —
that is `/complicate` or `/simplify`'s job. Edits nothing itself; filing is the
only write, and only on request.

## Target

The current session's transcript, under `~/.claude/projects/<cwd-slug>/` —
the directory name is the cwd with `/` replaced by `-`. `$ARGUMENTS` names a
different session id; find its `.jsonl` the same way, searching every
project directory if the current one doesn't have it.

Read the whole transcript: user turns, assistant turns, tool calls and
results, denied calls, recalled memory bodies, loaded skill and rule
contents. Include any `subagents/*.jsonl` beside it — a subagent's denials
and tool calls are this session's too, just not in the parent stream.

## Lenses

Pass over the transcript once per lens below. A lens with nothing to report
says nothing — do not manufacture a finding to fill a slot.

1. **Navigation** — a stretch where the agent searched, grepped, or read
   multiple files to find something a pointer (a memory line, a `CLAUDE.md`
   reference, a comment linking to the real location) would have given
   directly.
2. **Automated checks** — a mistake that a gate, pre-commit hook, or
   `PreToolUse` hook could have caught before it happened, or a check that
   already exists in this repo's config but wasn't wired to fire on the path
   touched.
3. **Standards** — every violation of a written rule or convention found
   elsewhere in this session, classified one of two ways: mechanical (fits a
   gate, pre-commit check, or hook — propose the check) or judgement (needs a
   human call each time — propose one line for the pack's `rules/<name>.md`,
   or the consuming repo's own rules, no more).
4. **Steering-file size** — a rule or `CLAUDE.md` line so long, or repeated so
   often, that it would work as well or better as an automated check or a
   short pointer to where the real content lives. This includes the
   always-loaded surface: every skill and command's frontmatter
   `description` sits in context every turn. Measure it — word-count each
   `description` in `~/.claude/skills/*/SKILL.md` and `.claude/commands/*.md`
   touched or loaded this session, and flag the long tail against the
   shortest ones in the same set, not against a guessed target.
5. **Tool economy** — a tool call that burned unusual time or tokens (a full
   file read where a grep would do, a broad search where a memory or a
   pointer already named the path, a subagent for something the parent could
   answer inline) where a cheaper call would have reached the same result.
6. **No-ops** — a steering line (rule, `CLAUDE.md`, skill description,
   frontmatter trigger) that, read against what the agent actually did, did
   not change behaviour from what the model would have done anyway.
7. **Information access** — a fact the agent needed, went looking for, and
   could not reach at all (not slow to find — genuinely unreachable from
   inside the session).
8. **Memory** — a recalled memory body that was wrong, stale, or contradicted
   by what the session found; or one that fired, was read, and was then
   ignored. The finding names the memory file and, when a hook should have
   enforced it instead of leaving it to be read and obeyed, names the hook
   gap — not just "the agent should have listened."
9. **Permission denials** — every denied tool call in the transcript, one
   finding each. Say which side is wrong: the classifier boundary is correct
   and should stay (the call should not have been attempted), or it's an
   allow-list gap (the call is legitimate and should be permitted for this
   pattern). Name any memory or rule already in context that covered the
   denied call — a denial the agent had already been told about is the
   sharper finding than a bare "boundary held."

## Output

Rank all findings together by severity, high to low, across all nine lenses.
For each:

```
<N>. [<lens>] <one-line finding>
   Evidence: "<quoted transcript line or tool call>"
   Proposed change: <what to add/edit/wire — one line>
```

Severity is impact on future sessions, not lens order — a single no-op rule
line ranks below a permission denial that blocked real work. One event can
hit more than one lens (a denied call after an ignored memory is both a
memory finding and a permission finding); report it once, tagged with
whichever lens carries the proposed change, not once per lens it touches.

## Filing

Offer to file each finding as an issue on this repo, through the same gate
`/done` step 4 uses: one prompt, private-remote rows pre-selected, unticked
rows dropped, five-candidate cap, the labels `rules/tickets.md`'s Follow-ups
section names, the banned-name scan from the `banned_names_file` named in
`.mutation-gate.toml` run over every draft before it's filed. Title is the
finding flat, body is the same four-field shape (`Evidence` / `Noticed in` —
this session's transcript path and id, not a commit — / `Deferred because`,
or the reason it's being filed now instead of deferred).

This command never edits or commits. Filing issues is its only write, and
only after the user confirms the prompt.
