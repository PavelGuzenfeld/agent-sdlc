# agent-sdlc

[![CI](https://github.com/PavelGuzenfeld/agent-sdlc/actions/workflows/ci.yml/badge.svg)](https://github.com/PavelGuzenfeld/agent-sdlc/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/PavelGuzenfeld/agent-sdlc)](LICENSE)

A software development lifecycle shipped as agent config: rules, skills, slash
commands and a diff-scoped mutation gate, installable into Claude Code and
Codex.

## Install

`./install.sh --target claude|codex|all [--deps|--deps=say]` symlinks
the directories into `~/.claude` and `~/.codex`, renders `commands/` as Codex
skills, merges the hooks from `settings.example.json` and, with `--deps`,
installs the tooling (`--deps=say` adds the Kokoro TTS stack). A second run
changes nothing. It installs `ast-grep-cli` via pipx, which puts an `sg`
shim on `$PATH`; if `~/.local/bin` precedes `/usr/bin`, it shadows the
system `sg` (execute as a different group).

The `mutation-gate` CLI alone can be installed from a tagged
[release](https://github.com/PavelGuzenfeld/agent-sdlc/releases)'s wheel:
`pip install <release .whl URL>`.

Plugin install: `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` and
`.agents/plugins/marketplace.json` ship at the repo root.

- Claude Code: `claude --plugin-dir /path/to/agent-sdlc`
- Codex: add this repo as a marketplace source; its
  `.agents/plugins/marketplace.json` lists one plugin entry with
  `source.path` set to the repo root.

## What's inside

`skills/ commands/ rules/ bin/ mutation_gate/` at the root, no agent home
baked in. CI runs `scripts/no-leaks.sh` on every PR — it flags emails, RFC1918
addresses, user-at-host references, `/home/<user>/` paths and non-personal
`ghcr.io/` paths, and prints only `file:line`.

## Docs

The SDLC, the gate, debugging, reporting, rules and skills, in depth:
<https://pavelguzenfeld.com/agent-sdlc/>.

MIT, see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) for one vendored
third-party skill. Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
