# Skills

Playbooks the agent loads on demand. Each is a `SKILL.md` under `skills/`.
Script paths inside them are written `<skill-dir>/scripts/...`, where
`<skill-dir>` is the directory the `SKILL.md` was read from.

[TOC]

## At a glance

| Skill | Use it to | Invoked by |
|---|---|---|
| `/diagnose` | Work a bug that resisted one fix: red loop first | agent or you |
| `/verify-generated-diff` | Check an AI-written diff whose tests can't be trusted | agent or you |
| `/sol-budget` | Budget a hot path against what the hardware can do | agent or you |
| `/land` | Deploy the change into Docker for a system test | agent or you |
| `/wizard` | Script a step only a human can do: credentials, hardware | agent or you |
| `/ps` | Park an aside and carry on | agent or you |
| `/writing-for-agents` | Write a skill, command, rule or CLAUDE.md | agent or you |
| `/blind` | Blind vs informed hypothesis ranking | you only |
| `/simplify` | Report what to delete from a diff or repo | you only |
| `/upstream` | Decide whether a fix belongs here or in the dependency | you only |

- "You only" skills set `disable-model-invocation`: the agent can't start
  them, and asks you to.

The full text follows, included verbatim, frontmatter dropped.

--8<-- "skills/blind/SKILL.md:6"

--8<-- "skills/diagnose/SKILL.md:5"

--8<-- "skills/land/SKILL.md:5"

--8<-- "skills/ps/SKILL.md:5"

--8<-- "skills/simplify/SKILL.md:6"

--8<-- "skills/sol-budget/SKILL.md:5"

--8<-- "skills/upstream/SKILL.md:6"

--8<-- "skills/verify-generated-diff/SKILL.md:5"

--8<-- "skills/wizard/SKILL.md:5"

--8<-- "skills/writing-for-agents/SKILL.md:5"
