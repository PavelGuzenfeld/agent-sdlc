# Code clarity

Code is the documentation. It is written for humans and only incidentally for
machines. Clarity comes from naming, types, and structure — never from prose
sitting next to the code.

Reach for a better name, a smaller function, or an explicit type before reaching
for a comment. A comment that explains *what* the code does means the code is
unclear: fix the code, then delete the comment.

## Hard limits

- Comments: **zero.** No hand-written `#` or `//` comments in new code, in this
  repo. Carve-outs: pragmas (`# pyright: ignore`, `# noqa`, `NOLINT`), shebangs,
  license/SPDX headers, and vendored or generated files — their comments are
  upstream's; check with a diff against the skeleton before assuming a config is
  yours.
- Docstrings: **3 lines maximum.** They are now the only remaining prose carrier.
- Upstream trees: match the host project's pattern instead of this ban.

If it does not fit, the thing being explained belongs in a name, a type, a test,
or a design doc — not in the file.

## Docstrings: only what the code cannot say

**The bar: a docstring must carry context the code cannot.** If the code
could say it — with a name, a type, or structure — say it there and delete the docstring.

Why a non-obvious choice was made. A spec or ICD constraint. A workaround and the
bug it dodges. A unit, frame of reference, or coordinate convention. A deliberate
simplification — only when it names both the ceiling it hits and the trigger to
revisit; without the trigger it is the unowned TODO below.

Never write: a restatement of the line below it, a docstring that restates the name or
the signature, a section banner, a changelog, a commented-out block, or an unowned TODO.

If the name and the signature already say it, write no docstring. A docstring is for the
invariant, the unit, or the caller obligation you would otherwise have to read the body
to find. Where a tool demands a summary line (pydocstyle, numpydoc, Doxygen), keep it
minimal and put the real content after it.
