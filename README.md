# agent-sdlc

Software development lifecycle as installable agent config: skills, slash
commands, rules and a diff-scoped mutation gate, for Claude Code and Codex.

Extracted from a private dotfiles setup and sanitized. Content lands one
themed PR at a time; the [issue tracker](https://github.com/PavelGuzenfeld/agent-sdlc/issues)
is the roadmap.

Layout: `skills/ commands/ rules/ bin/ mutation_gate/` at the root, no agent
home baked in.

Install: `./install.sh --target claude|codex|all [--deps]` symlinks the
directories into `~/.claude` and `~/.codex`. Not yet implemented; see the
tracker.

CI runs `scripts/no-leaks.sh` on every PR. It flags emails, RFC1918
addresses, `user@host`, `/home/<user>/` paths and non-personal `ghcr.io/`
paths, and prints only `file:line`.

MIT, see [LICENSE](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
