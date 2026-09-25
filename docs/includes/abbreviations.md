*[mutant]: A deliberate small bug the gate seeds into changed code, such as >= turned into >
*[mutants]: Deliberate small bugs the gate seeds into changed code, such as >= turned into >
*[survivor]: A mutant every test still passes on; the tests would miss that bug too
*[survivors]: Mutants every test still passes on; the tests would miss those bugs too
*[kill rate]: Share of mutants some test fails on
*[waiver]: An accepted survivor in .mutation-gate-waivers.toml, with a reason no test should kill it
*[waivers]: Accepted survivors in .mutation-gate-waivers.toml, each with a reason no test should kill it
*[covering test]: A test that executes the mutated line
*[covering tests]: Tests that execute the mutated line
*[adversary]: A review after a pass that sees the intent and the tests, never the code
*[blind pass]: A review of model code that sees the code, never the spec
*[slice test]: One test per ticket that enters where a real user enters and checks the outcome the ticket asks for
*[vertical slice]: A thin piece of a feature that works end to end, through every layer
*[red loop]: One fast command, already run, that shows the bug
*[metamorphic]: Checks a relation between runs when the exact answer is unknown
*[envelope]: The state, time-step and manoeuvre range the model is claimed to work in
*[SymPy]: A Python library for symbolic maths
*[NEES]: Normalised estimation error squared: does the filter's claimed uncertainty match its real error
*[NIS]: Normalised innovation squared: does the filter's predicted measurement spread match reality
*[PSD]: Positive semi-definite, required of every covariance matrix
*[Jacobian]: The matrix of partial derivatives a nonlinear filter linearises with
*[Jacobians]: Matrices of partial derivatives a nonlinear filter linearises with
*[WordNet]: A lexical database of English word senses
*[mold]: The word-order pattern a kind of name must fit
*[molds]: The word-order patterns each kind of name must fit
*[SOL]: Speed of light: the fastest a stage could run on this hardware, measured
*[RFC1918]: The private address ranges 10.x, 172.16-31.x and 192.168.x
*[LGTM]: Looks good to me; typed at the prompt, it lets kata merge
*[PreToolUse]: The Claude Code hook event before each tool call
*[worktree]: A second checkout of the same repo on its own branch
*[worktrees]: Extra checkouts of the same repo, each on its own branch
*[triage]: Deciding a ticket is ready and adding its model label
*[ast-grep]: A tool that searches and rewrites code by syntax tree, not text
*[tree-sitter]: The parser library ast-grep builds on
*[Kokoro]: The text-to-speech model /say speaks through
*[roofline]: A chart of whether a kernel is limited by compute or memory bandwidth
*[llvm-mca]: An LLVM tool that estimates how a CPU would schedule machine code
*[pre-registration]: Writing down what result would confirm a hypothesis before running the test
