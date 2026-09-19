---
name: upstream
description: "Decide where a feature belongs: our tree, the dependency, or both, in order."
disable-model-invocation: true
---

# Upstream

Where does this feature live: our tree, the dependency, or both in a stated order.
Report only. One verdict, the evidence behind it, one ledger line.

## Verdicts — exactly one, always

| verdict | meaning |
|---|---|
| `local-permanent` | ours forever, no upstream attempt |
| `shim-now-plus-PR` | ship the local shim, submit upstream in parallel, drop the shim on release |
| `upstream-only-blocked` | no local copy; the work waits on the merge |
| `fork-pinned` | patch the dependency and pin it; the pin is a maintenance tax |
| `issue-first-no-code` | file the issue, write nothing, wait for a maintainer |

## Discriminators — all four, every run

**generality** — does the patch need one of our concepts to make sense.
`ours`: an internal-project concept appears in the patch itself — see the banned-name list in `~/.claude/rules/public-surface.md`.
`general`: it stands alone for any user of the dependency.

**latency** — `blocks` if a delivery date depends on the merge, else `free`.

**receptivity** — looked up, never asked, never settled from memory alone.
`receptive`: a comparable PR merged within 12 months, or an open issue or roadmap
entry asking for it.
`hostile`: a comparable PR closed unmerged, a maintainer statement against the
design, or no release in 18 months. A relationship constraint is not a receptivity
signal — it caps who writes the text, not whether the patch would land.
`unknown`: neither. Out of queries with nothing found is `unknown`, not `hostile`.

**carry cost** — what the local alternative costs to keep: a named maintenance tax
and a named trigger to revisit. Breaks ties only, on two rows.

## Precheck — is there an upstream at all

No OSS project accepts the patch — a closed-source or vendor-only SDK (NVIDIA
`jetson_multimedia_api`, DeepStream, a binary driver) — then the verdict is
`local-permanent` and no query is spent. The table below assumes a maintainer who
can say yes.

## Receptivity lookup — five queries, hard cap

1. merged PRs in the area
2. closed-unmerged PRs in the area
3. open issues in the area
4. last release, or last commit if the project does not tag
5. CONTRIBUTING or roadmap — only if 1-4 come back ambiguous

GitHub: `gh pr list --repo <r> --search '<area>' --state merged --limit 5`, the
same with `--state closed`, `gh issue list --repo <r> --search '<area>'`,
`gh release list --repo <r> --limit 1`.
GitLab (Eigen, freedesktop): the project REST API —
`/projects/<id>/merge_requests?scope=all&state=merged&search=<area>`,
`/issues?search=<area>`, `/repository/tags?per_page=1`.
GStreamer's `github.com/GStreamer/gstreamer` is a mirror with PRs and issues
disabled — querying it returns empty, not `hostile`. Use the freedesktop API.

Every receptivity claim carries a URL or it is not evidence.

## Decision table

| generality | latency | receptivity | verdict |
|---|---|---|---|
| ours    | *      | *         | `local-permanent` |
| general | blocks | receptive | `shim-now-plus-PR` |
| general | blocks | unknown   | `shim-now-plus-PR`, issue filed alongside |
| general | blocks | hostile   | carry cost decides |
| general | free   | receptive | `upstream-only-blocked` |
| general | free   | unknown   | `issue-first-no-code` |
| general | free   | hostile   | carry cost decides |

**Carry cost decides** on the two hostile rows only, along one axis: shim or pin.
A shim at the dependency's API boundary wins. `fork-pinned` only when no such shim
exists — then record the pin's tax and its revisit trigger with it. A hostile row
carried by a shim, with no upstream attempt left open, is `local-permanent`.

## Scrub — mandatory on every non-local verdict

- origin repo of the feature
- internal names to replace, and what to replace them with: the banned-name list
  in `~/.claude/rules/public-surface.md`, which is the only copy. Do not restate
  it here or anywhere else that gets committed.
- identity to commit under: never the work address, never a `Signed-off-by`
- the grep to run before pushing: build the alternation from that same list and
  run it over the patch

**A GStreamer or freedesktop target caps the output.** Name the points the MR,
commit message or comment must cover, and stop. Never draft the text. nirbheek's
final warning of 2026-03-25 stands.

## Ledger

`~/.claude/upstream-verdicts.md`, append-only, one line per verdict:

`YYYY-MM-DD | <dependency> | <feature> | <verdict> | <evidence + URL> | scrub: <origin, names, identity, grep result + date> | revisit: <trigger>`

The scrub field is comma-separated — `|` is the column delimiter. On a local
verdict it is `scrub: n/a (local)`. Record the identity as a label — `personal
identity`, `work identity` — never a literal address: the ledger is committed and
the pre-commit hook blocks emails. A recorded scrub says what was checked and
when; it never substitutes for re-running the grep before a push.

Read it before scoring. A hit on the same dependency and feature short-circuits:
print the prior verdict with its date, evidence and scrub, and spend no queries.
Re-score only once the recorded revisit trigger has fired.

## Output

```
verdict: <one of five>
because: generality=<> latency=<> receptivity=<> — <the URL that decided it>
scrub:   <origin> | <names> | <identity> | <grep>
next:    1. ...
ledger:  <the appended line>
```

Where a step is "file an issue" or "open an MR", `next` names the points the text
must cover. It never contains the text.

## Boundaries

Third-party OSS dependencies only — not our own repos, not internal shared libs,
not standards bodies. Forward-looking only: no repo scan, no pin sweep, no ledger
sweep. Report only: opens no issue, pushes no branch, writes nothing but its own
ledger line.
