# agent-sdlc

Software development lifecycle as installable agent config: skills, slash
commands, rules and a diff-scoped mutation gate, for Claude Code and Codex.

Extracted from a private dotfiles setup and sanitized. Content lands one
themed PR at a time; the [issue tracker](https://github.com/PavelGuzenfeld/agent-sdlc/issues)
is the roadmap.

Layout: `skills/ commands/ rules/ bin/ mutation_gate/` at the root, no agent
home baked in.

Install: `./install.sh --target claude|codex|all [--deps|--deps=say]` symlinks
the directories into `~/.claude` and `~/.codex`, renders `commands/` as Codex
skills, merges the hooks from `settings.example.json` and, with `--deps`,
installs the tooling (`--deps=say` adds the Kokoro TTS stack). A second run
changes nothing. It installs `ast-grep-cli` via pipx, which puts an `sg`
shim on `$PATH`; if `~/.local/bin` precedes `/usr/bin`, it shadows the
system `sg` (execute as a different group).

Plugin install: `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` and
`.agents/plugins/marketplace.json` ship at the repo root.

- Claude Code: `claude --plugin-dir /path/to/agent-sdlc`
- Codex: add this repo as a marketplace source; its
  `.agents/plugins/marketplace.json` lists one plugin entry with
  `source.path` set to the repo root.

CI runs `scripts/no-leaks.sh` on every PR. It flags emails, RFC1918
addresses, user-at-host references, `/home/<user>/` paths and
non-personal `ghcr.io/` paths, and prints only `file:line`.

MIT, see [LICENSE](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
