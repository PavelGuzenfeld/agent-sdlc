# Config

Every key `.mutation-gate.toml` accepts. An unknown top-level, `languages.*`
or `[[golden]]` key is a `GateError` at load time.

## A starting file

An empty `.mutation-gate.toml` works: every key below has a default. A typical
Python repo with tests in Docker:

```toml
test_paths = ["tests"]
test_command = 'docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/repo -w /repo my-image python -m pytest -q {tests}'
exclude_paths = ["vendor/"]

[[doc_allow]]
glob = "docs/**/*"
reason = "mkdocs site content"
```

A repo with model code:

```toml
model_paths = ["filters/"]
model_spec = "issue:19"
model_test_paths = ["tests/filters/"]
```

A repo gating two languages:

```toml
[languages.python]
test_paths = ["tests"]
test_command = "python -m pytest -q {tests}"

[languages.typescript]
test_paths = ["web/tests"]
test_command = "npm --prefix web run test"
```

- Each table overrides `test_paths`, `test_globs`, `test_command`,
  `coverage_command` and `coverage_data_file` for that language.
- `.tsx` files are their own language, `tsx`, and need their own table.

## Keys

| Key | Default | What it does |
|---|---|---|
| `enabled` | `true` | Opts this repo out of the gate entirely when `false`. |
| `language` | `"python"` | Language the flat fields below describe. |
| `test_paths` | `["tests"]` | Repo-root-relative directories; everything under them counts as a test. |
| `test_globs` | `[]` | `Path.glob` patterns for tests that sit beside their sources, not under `test_paths`. |
| `test_command` | `"pytest -q {tests}"` | Shell command that runs the tests; `{tests}` is the full candidate set for the baseline run, or the covering test ids per mutant, falling back to the full set. |
| `coverage_command` | `"pytest -q --cov={file} --cov-context=test --cov-report= {tests}"` | Shell command that runs the candidate tests under coverage; `{file}` is the mutated file's containing directory, not the file itself. |
| `coverage_data_file` | `".coverage"` | Where the coverage command writes its data; read per line to map which tests cover the mutated file. |
| `languages` | `{}` | `[languages.<name>]` tables, each a `test_paths`/`test_globs`/`test_command`/`coverage_command`/`coverage_data_file` override, for a repo gating more than one language. |
| `exclude_paths` | `[]` | Path prefixes the gate never touches; announced on every skip. |
| `model_paths` | `[]` | Path prefixes in scope for model V&V, declared, never inferred; `rules sync` also builds `model-vv.md`'s `paths:` frontmatter from this. |
| `model_spec` | `"docs/model-spec.md"` | Where the model spec's `MS-n` lines live: `issue:N`, a GitHub issue. Required once `model_paths` is set; a file path, including this default, is refused there. |
| `model_test_paths` | `[]` | Test paths that must cite an `MS-n` spec line. |
| `model_exclude` | `[]` | `[[model_exclude]]` entries, each a `path` and a `reason`: a keyword-probe hit outside `model_paths` that isn't model code. |
| `golden` | `[]` | `[[golden]]` entries, each a `source` and an `artifact`: a generated F/Q artefact and the SymPy source its hash is checked against. |
| `pass_pattern` | `""` | Regex the test output must contain to count as green; empty trusts the exit code. |
| `force_gate` | `false` | Gates a fork or an out-of-namespace checkout anyway. |
| `baseline_timeout` | `900.0` | Seconds allowed for the unmutated baseline run, and for the coverage run that maps tests to lines. |
| `mutant_timeout` | none (derived from the baseline) | Seconds allowed per mutant, when the derived cap is wrong. |
| `closure_depth` | `1` | Import hops from a test to the mutated file that still count as covering it. |
| `import_roots` | `[]` | Extra repo-root-relative import roots for a src layout with no `sys.path.insert` in the test files. |
| `no_comments` | `false` | Blocks on a comment line the diff added. |
| `vocabulary` | `""` | Path to the repo's own vocabulary file, layered over the packaged core dictionary; empty turns the gate's vocabulary checks off, and `vocabulary lookup` uses the core dictionary alone. |
| `vocabulary_molds` | `{}` | Per-kind naming molds `vocabulary lookup --kind` checks names against; narrows the built-in set, never widens. |
| `vocabulary_synonyms` | `"report"` | `"report"` prints a WordNet-synonym collision on a dictionary addition as a report line; `"block"` fails it. |
| `own_namespaces` | `[]` | Origin substrings this checkout is allowed to gate under; outside all of them reads as a fork. The `MUTATION_GATE_OWN_NAMESPACES` env var overrides this when set. |
| `doc_allow` | `[]` | `[[doc_allow]]` entries, each a `glob` and a `reason`: a new `.md` file the built-in allowlist doesn't cover. |
| `banned_names_file` | `""` | Path to a file of `X → Y` lines `no-leaks` must reject from the staged diff and commit message. |

Source: [`mutation_gate/repo.py`](https://github.com/PavelGuzenfeld/agent-sdlc/blob/main/mutation_gate/repo.py).
