# CLI

Everything `mutation-gate` does from the command line. Install it with the
pack's `--deps`, or alone with `pip install agent-sdlc`.

[TOC]

## At a glance

| Command | What it does | Hook id |
|---|---|---|
| `mutation-gate` | Diff-scoped mutation run plus the model, comment and vocabulary checks | `mutation-gate` |
| `mutation-gate rules sync` / `check` | Write the rules into a repo / report drift | `rules-check` |
| `mutation-gate vocabulary lookup` / `audit` | Judge a word or name / audit the repo's names | none |
| `mutation-gate commit-msg` | Banned words, AI attribution, `Signed-off-by` | `commit-msg` |
| `mutation-gate diff-discipline` | 40-line limit without a ticket reference | `diff-discipline` |
| `mutation-gate no-new-docs` | New `.md` files must be allowlisted | `no-new-docs` |
| `mutation-gate no-leaks` | Identity, RFC1918 and home-path scan, plus banned names | `no-leaks` |

Hook ids come from this repo's `.pre-commit-hooks.yaml`. See
[Hooks and tools](tools.md#pre-commit-hooks) for wiring them in.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Pass |
| `1` | Blocked: a survivor, a finding, a banned word |
| `2` | Refused: misconfiguration, nothing was measured |

- A refusal is never a pass.
- One exception: under `--worktree`, a lock held by a concurrent run exits
  `0`. The Stop hook is best-effort; a live gate on the same repo is a reason
  to skip.

## mutation-gate

```text
usage: mutation-gate [-h] [--staged] [--worktree] [--user-prompt USER_PROMPT]
                     [--no-adversary] [--file FILE] [--dry-run]
                     [files ...]
```

| Flag | Use |
|---|---|
| `--staged` | Gate the index. The default; what pre-commit runs |
| `--worktree` | Gate the working tree. What the Stop hook runs |
| `--file FILE` | Gate every line of one file, not just the diff |
| `--dry-run` | Print candidate tests and mutants; run no tests |
| `--user-prompt TEXT` | Intent for the adversary when there is no ticket |
| `--no-adversary` | Skip the adversary and blind pass. Debugging the pack only |
| `files ...` | Ignored; pre-commit passes filenames |

Order of checks in one run:

```text
 changed lines
      |
      v
 model V&V: probe, golden, spec
      |
      v
 no-comments                      (only if no_comments = true)
      |
      v
 vocabulary, -path, -synonyms     (only if a vocabulary file is set)
      |
      v
 mutants vs covering tests ---- survivor ----> BLOCKED, exit 1
      |
      | all killed
      v
 mutation-gate: pass
      |
      v
 adversary report
      |
      v
 model blind pass                 (only if a model_paths file changed)
```

Example: see what would run, without running it.

```bash
mutation-gate --dry-run
mutation-gate --file src/age.py --no-adversary
```

A run with nothing to gate:

```text
mutation-gate: no gated source files in this change — no mutants, so no adversary review
```

## rules

```text
usage: mutation-gate rules [-h] {sync,check}
```

- `sync` writes `.claude/rules/*.md` and the `AGENTS.md` block from the pack's
  `rules/`.
- `check` reports drift and exits non-zero:

```text
rules check: .claude/rules/voice.md: missing
rules check: AGENTS.md: missing
run `mutation-gate rules sync` and commit the result
```

- Syncing only writes rules. It does not turn the gate on; that takes a
  `.mutation-gate.toml` (Stop hook) and a pre-commit entry (commits).

## vocabulary

```text
usage: mutation-gate vocabulary lookup [-h] [--kind {bool,constant,enumerator,event,field,function,local,method,namespace,parameter,property,type,variable}] word
usage: mutation-gate vocabulary audit [-h] [--format {text,toml}] [--leading-underscore]
```

```text
$ mutation-gate vocabulary lookup candidate
vocabulary lookup: `candidate` is not in the dictionary

$ mutation-gate vocabulary lookup --kind function compute_total
compute_total: fits the function mold
```

- `lookup` without `--kind` judges a word; with `--kind` it judges a name
  against that kind's mold.
- `audit` scans the repo's names; `--format toml` prints entries ready to add
  to the vocabulary file.

## commit-msg

```text
usage: mutation-gate commit-msg [-h] [--range REV_RANGE] [msgfile]
```

- Blocks the banned words listed in `rules/voice.md`, AI co-author and
  "Generated with" lines, and `Signed-off-by` trailers.
- `--range origin/main..HEAD` checks every commit on a branch, for CI.

## diff-discipline

```text
usage: mutation-gate diff-discipline [-h] [--range REV_RANGE] [--branch BRANCH] [msgfile]
```

- Counts added production lines on the branch against the default branch
  (`origin/HEAD`, then `origin/main`, `origin/master`, `main`, `master`).
- Over 40 with no ticket reference, it blocks. A ticket reference is an
  `N-slug` branch name or `#N` in a commit message.
- Test files and model V&V artefacts don't count.
- `--branch` names the branch when HEAD is detached in CI.

## no-new-docs

```text
usage: mutation-gate no-new-docs [-h] [--range REV_RANGE]
```

- A newly added `.md` file must match the built-in allowlist (README,
  LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, NOTICE, CHANGELOG,
  `.github/**`, `AGENTS.md`, synced rules) or a `[[doc_allow]]` entry.
- Everything else belongs in a ticket. See [Config](config.md) for
  `doc_allow`.

## no-leaks

```text
usage: mutation-gate no-leaks [-h] [--range REV_RANGE] [msgfile]
```

- Scans the staged diff and the commit message for emails, RFC1918
  addresses, user-at-host references and `/home/<user>/` paths.
- With `banned_names_file` set in `.mutation-gate.toml`, it also rejects each
  `X → Y` line's left side.
