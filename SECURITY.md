# Security Policy

## Scope

In scope: code here doing something it doesn't say it does — exfiltrating
data, `no-leaks.sh` failing open, the gate or `install.sh` reaching for a
privilege they never claimed.

Not a vulnerability: this pack executes shell, symlinks into `~/.claude`
and `~/.codex`, and runs Docker. That is the advertised product, not a
finding.

## Reporting

Use GitHub's private vulnerability reporting: the Security tab on this
repo, "Report a vulnerability". No email, no form, no SLA.

Include what makes it exploitable, not just what looks wrong.
