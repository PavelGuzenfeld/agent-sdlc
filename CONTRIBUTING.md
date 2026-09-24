# Contributing

Bugs and feature requests go through the issue templates: a bug report asks
what happened, how to reproduce it and what you expected; a feature request
asks what outcome you are after and why.

PRs are welcome. One ticket, one branch, one PR, with `Closes #N` in the body.
Merges are squash-only.

CI must be green. It runs a growing set of checks — see
`.github/workflows/ci.yml` for the current jobs.

Install `pre-commit` and run `pre-commit install` once per clone; this repo's
`.pre-commit-config.yaml` sets `default_install_hook_types` so that one command
installs both the pre-commit and the commit-msg git hook. A consumer repo that
copies this pattern without that setting needs `pre-commit install --hook-type
commit-msg` in addition to the plain `pre-commit install`. The no-leaks check
runs on every commit; it needs only `git` and POSIX shell utilities. If you have
this repo's own `mutation-gate` on PATH (see `install.sh --deps`), a commit
touching a `.py` file under `mutation_gate/` or `skills/sol-budget/scripts/` also runs the gate,
and every commit message is checked against `rules/voice.md`'s banned words
and against AI attribution and sign-off trailers — see `rules/testing.md` and
`rules/voice.md`. A branch that adds more than 40 production lines against
the default branch (`origin/HEAD`, falling back to `origin/main`,
`origin/master`, `main`, `master`) needs a ticket reference: an `N-slug`
branch name or `#N` in a commit message — see `rules/diff-discipline.md`.
A newly added `.md` file outside the built-in allowlist needs a `doc_allow`
entry with a reason in `.mutation-gate.toml` — see `rules/tickets.md`. If on
PATH, `mutation-gate` also runs the packaged `no-leaks` check on the staged
diff and the commit message: the same identity, RFC1918 and home-path scan
as `scripts/no-leaks.sh`, plus an optional `banned_names_file` in
`.mutation-gate.toml` pointing outside the repo. Its lines map `X → Y` — an
optional `- ` bullet, the left side optionally backticked and
`/`-separated for more than one banned token, a `→`, then the replacement —
and a line with no `→` is prose and is ignored. A staged line or commit
message line containing a banned `X` is rejected with `Y` suggested; a
missing or unset file skips only that check, and a file that exists but
parses to no mapping refuses the commit rather than passing silently.

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for the standard a PR is held to.

No CLA. No DCO sign-off.
