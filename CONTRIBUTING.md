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
runs on every commit; it has no dependencies beyond `sh` and `awk`. If you have
this repo's own `mutation-gate` on PATH (see `install.sh --deps`), a commit
touching `mutation_gate/` or `skills/sol-budget/scripts/` also runs the gate,
and every commit message is checked against `rules/voice.md`'s banned words
and against AI attribution and sign-off trailers — see `rules/testing.md` and
`rules/voice.md`.

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for the standard a PR is held to.

No CLA. No DCO sign-off.
