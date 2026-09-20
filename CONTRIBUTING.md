# Contributing

Bugs and feature requests go through the issue templates: a bug report asks
what happened, how to reproduce it and what you expected; a feature request
asks what outcome you are after and why.

PRs are welcome. One ticket, one branch, one PR, with `Closes #N` in the body.
Merges are squash-only.

CI must be green. It runs a growing set of checks — see
`.github/workflows/ci.yml` for the current jobs. Run `sh tests/no-leaks.sh`
and `sh scripts/no-leaks.sh` locally before pushing.

No CLA. No DCO sign-off.
