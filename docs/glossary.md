# Glossary

Every term the docs lean on, in plain words. Hover a term anywhere on the site
to see its short definition.

## Testing and the gate

| Term | What it is | More |
|---|---|---|
| Mutation testing | Seed small deliberate bugs into code and rerun the tests to see if they notice | [Wikipedia](https://en.wikipedia.org/wiki/Mutation_testing), [Techniques](techniques.md#mutation-testing) |
| Mutant | One such deliberate bug: `>=` turned into `>`, `18` into `19` | [Techniques](techniques.md#mutation-testing) |
| Killed | A mutant some test failed on. Good: the tests noticed | [Gate](gate.md#when-it-blocks) |
| Survivor | A mutant every test still passes on. The tests would miss that bug too | [Gate](gate.md#when-it-blocks) |
| Kill rate | Share of mutants killed. The one number that tells a green suite from a blind one | [Rules → Testing](rules.md#testing) |
| Waiver | An entry in `.mutation-gate-waivers.toml` that accepts one survivor, with a reason why no test should kill it | [Gate](gate.md#when-it-blocks) |
| Equivalent mutant | A mutant that changes the code but not its behaviour, so no test can kill it | [Wikipedia](https://en.wikipedia.org/wiki/Mutation_testing) |
| Diff-scoped | Only the lines your change touched are mutated, not the whole repo | [Techniques](techniques.md#diff-scoped-mutants) |
| Baseline | The unmutated test run the gate does first; if it fails, nothing after it means anything | [Config](config.md) |
| Covering test | A test that executes a given line; each mutant runs only against its covering tests | [Techniques](techniques.md#covering-test-map) |
| Code coverage | Which lines a test run executed. The gate records it per test to build the covering-test map | [Wikipedia](https://en.wikipedia.org/wiki/Code_coverage) |
| `closure_depth` | How many import hops from a test to a file still count as covering it | [Config](config.md) |
| Adversary | An isolated review after a pass that sees the intent and the tests, never the code | [Techniques](techniques.md#adversary-review) |
| Blind pass | The reverse: a review of model code that sees the code, never the spec | [Techniques](techniques.md#adversary-review) |
| Slice test | One test per ticket that enters where a real user enters and checks the outcome the ticket asks for | [Techniques](techniques.md#vertical-slice-first) |
| Vertical slice | A thin piece of a feature that works end to end, through every layer | [Wikipedia](https://en.wikipedia.org/wiki/Vertical_slice) |
| Red first | Write the test, watch it fail for the right reason, only then write the code | [Rules → Testing](rules.md#vertical-slice-first) |
| Red loop | One fast command, already run, that shows the bug. `/diagnose` starts here | [Debugging](debugging.md) |
| Metamorphic test | A test that checks a relation between runs, such as "rotating the input rotates the output", when the exact answer is unknown | [Wikipedia](https://en.wikipedia.org/wiki/Metamorphic_testing) |

## Model V&V

| Term | What it is | More |
|---|---|---|
| Model V&V | Verification and validation for estimation and physics code: filters, frames, units, noise | [Techniques](techniques.md#model-vv) |
| `model_paths` | The files a repo declares as model code. Declared, never guessed | [Config](config.md) |
| Model spec | The pinned issue holding what the model covers, what it ignores, and how accurate it must be | [Rules → Model V&V](rules.md#model-verification-validation) |
| `MS-n` | One numbered line of the model spec. Model tests cite it in their docstring | [Gate](gate.md#model-paths) |
| Envelope | The range of states, time steps and manoeuvres the model is claimed to work in | [Rules → Model V&V](rules.md#layer-0-spec) |
| Golden | A generated reference, such as the F and Q matrices, carrying the hash of the SymPy source it came from | [Rules → Model V&V](rules.md#layer-3-symbolic-golden) |
| SymPy | A Python library for symbolic maths. The model is written in it and the matrices are generated | [sympy.org](https://www.sympy.org/) |
| Kalman filter | An estimator that blends a motion model with noisy measurements | [Wikipedia](https://en.wikipedia.org/wiki/Kalman_filter) |
| PSD | Positive semi-definite. A covariance matrix must be, or the filter's maths breaks | [Wikipedia](https://en.wikipedia.org/wiki/Definite_matrix) |
| Jacobian | The matrix of partial derivatives a nonlinear filter linearises with | [Wikipedia](https://en.wikipedia.org/wiki/Jacobian_matrix_and_determinant) |
| NEES / NIS | Normalised estimation error / innovation squared: statistics that say whether a filter's claimed uncertainty matches its real error | [Rules → Model V&V](rules.md#layer-5-consistency-harness) |
| Innovation | The gap between a measurement and what the filter predicted it would be | [Wikipedia](https://en.wikipedia.org/wiki/Kalman_filter) |
| Chi-square band | The range NEES/NIS should fall in if the filter is consistent | [Wikipedia](https://en.wikipedia.org/wiki/Chi-squared_distribution) |
| Monte Carlo | Running many randomised trials and reading the statistics off them | [Wikipedia](https://en.wikipedia.org/wiki/Monte_Carlo_method) |
| Units at every boundary | A distinct type per physical quantity, so mixing metres and seconds fails to compile | [Wikipedia](https://en.wikipedia.org/wiki/Dimensional_analysis) |

## Naming

| Term | What it is | More |
|---|---|---|
| Vocabulary | The dictionary of approved words for names, core plus the repo's own | [Techniques](techniques.md#vocabulary-and-naming) |
| Canonical word | The one word the dictionary picks for a concept | [Rules → Naming](rules.md#naming) |
| Rejected synonym | A word the dictionary maps to its canonical word instead | [Rules → Naming](rules.md#naming) |
| Mold | The word-order pattern a kind of name must fit; `compute_total` fits the function mold | [CLI](cli.md#vocabulary) |
| WordNet | A lexical database of English senses, used to flag new words that mean the same as old ones | [Wikipedia](https://en.wikipedia.org/wiki/WordNet) |

## Workflow

| Term | What it is | More |
|---|---|---|
| Ticket | A GitHub issue that holds the intent. The approved ticket is the plan | [SDLC](sdlc.md) |
| Triage | Deciding a ticket is ready and adding its `model:*` label | [Reporting](reporting.md#triage) |
| `model:<name>` label | `haiku`, `sonnet`, `opus` or `fable`. It approves the ticket and picks the model that runs it | [Reporting](reporting.md#triage) |
| Follow-up | A ticket filed for work deferred or found mid-task, with the `follow-up` label and one category | [Rules → Tickets](rules.md#follow-ups) |
| `size:tiny` | A follow-up that names one location and leaves no design choice. Tiny ones can share one PR | [Rules → Tickets](rules.md#one-ticket-one-branch-one-pr) |
| Kata | The ticket-to-merge loop `/kata` runs. Named after the practice drill | [Commands](commands.md#kata), [Wikipedia](https://en.wikipedia.org/wiki/Kata_%28programming%29) |
| Worker | The fresh agent kata starts for one ticket, in its own worktree | [Commands](commands.md#kata) |
| Worktree | A second checkout of the same repo on its own branch, so parallel work can't collide | [git docs](https://git-scm.com/docs/git-worktree) |
| LGTM | "Looks good to me". Typed at the prompt, it lets kata merge | [Usage](usage.md#7-review-and-merge) |
| Squash merge | All of a PR's commits land on main as one | [GitHub docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-pull-request-merges) |
| `Closes #N` | The PR-body line that closes ticket N when the PR merges | [SDLC](sdlc.md) |
| Handoff | The note `/done` leaves so a fresh session can pick up | [Commands](commands.md#done) |
| Diff discipline | The smallest change that satisfies the ask; no drive-by edits | [Rules → Diff discipline](rules.md#diff-discipline) |
| Pre-registration | Writing down what result would confirm a hypothesis before running the test | [Wikipedia](https://en.wikipedia.org/wiki/Preregistration_%28science%29) |
| Blind test | A test where the process can't see the answer it might be biased towards | [Wikipedia](https://en.wikipedia.org/wiki/Blinded_experiment) |

## Agents and tooling

| Term | What it is | More |
|---|---|---|
| Rule | A file in `rules/` that says how to work. Synced into a repo, the agent reads it every session | [Rules](rules.md) |
| Skill | A `SKILL.md` playbook the agent loads when a task matches, or when you call it | [Skills](skills.md) |
| Command | A slash command in `commands/` that runs a workflow: `/kata`, `/done` | [Commands](commands.md) |
| `<skill-dir>` | The directory a `SKILL.md` was read from; its scripts are called through it | [Skills](skills.md) |
| `AGENTS.md` | The instruction file Codex and other agents read; `rules sync` writes a block into it | [agents.md](https://agents.md/) |
| Hook | A command Claude Code runs on an event, without being asked | [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code/hooks), [Hooks and tools](tools.md) |
| PreToolUse | The hook event before each tool call. The git guardrail runs there | [Hooks and tools](tools.md#git-guardrail) |
| Stop hook | The hook event when the agent finishes a turn. The gate runs there | [Hooks and tools](tools.md#claude-hooks) |
| Git guardrail | The PreToolUse hook that denies `reset --hard`, `add -A`, force-push and unmerged `branch -D` | [Hooks and tools](tools.md#git-guardrail) |
| `--force-with-lease` | A force-push that refuses if the remote moved since you last fetched | [git docs](https://git-scm.com/docs/git-push) |
| pre-commit | The framework that runs checks at `git commit`; this repo ships hooks for it | [pre-commit.com](https://pre-commit.com/), [Hooks and tools](tools.md#pre-commit-hooks) |
| commit-msg stage | The pre-commit stage that runs on the commit message, after you write it | [Hooks and tools](tools.md#pre-commit-hooks) |
| Plugin | A packaged agent add-on. This repo ships one for Claude Code and one for Codex | [Hooks and tools](tools.md#plugins) |
| ast-grep | A search-and-rewrite tool that matches code by syntax tree, not text | [ast-grep.github.io](https://ast-grep.github.io/) |
| tree-sitter | The parser library ast-grep builds on; GDScript needs its grammar built separately | [Wikipedia](https://en.wikipedia.org/wiki/Tree-sitter_%28parser_generator%29) |
| RFC1918 | The private address ranges `10.x`, `172.16–31.x`, `192.168.x`. `no-leaks` blocks them | [Wikipedia](https://en.wikipedia.org/wiki/Private_network) |
| Kokoro | The text-to-speech model `/say` speaks through | [GitHub](https://github.com/hexgrad/kokoro) |

## Performance

| Term | What it is | More |
|---|---|---|
| SOL | Speed of light: the fastest a stage could run on this hardware, measured, not guessed | [Techniques](techniques.md#speed-of-light-budgeting) |
| Ratio | `SOL ÷ measured`. Near 1 means the code is already at the hardware's limit | [Techniques](techniques.md#speed-of-light-budgeting) |
| `MODEL_DEFECT` | A stage measured faster than its own floor, so the machine model is wrong | [Techniques](techniques.md#speed-of-light-budgeting) |
| Budget | The share of the SOL each stage may spend, set in `perf/budget.md` | [Skills](skills.md) |
| Roofline | A chart of whether a kernel is limited by compute or by memory bandwidth | [Wikipedia](https://en.wikipedia.org/wiki/Roofline_model) |
| llvm-mca | An LLVM tool that estimates how a CPU would schedule a block of machine code | [llvm.org](https://llvm.org/docs/CommandGuide/llvm-mca.html) |
