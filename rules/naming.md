# Naming

Word order in every name follows spoken English order — the reader parses a
name the way they parse a sentence.

A name is made in three steps: pick the concept, take the dictionary's
canonical word for it, assemble the words in the mold for the declaration
kind.

Before naming anything, run `mutation-gate vocabulary lookup <word>`. It
reports canonical (use it), a rejected synonym (use the canonical word it
names), vague (follow the hint), or unknown — add the concept, with a
`meaning`, to the repo's vocabulary file in the same diff.

Once the words are picked, run `mutation-gate vocabulary lookup --kind <kind>
<name>` against the candidate. It checks the name against the mold for that
kind and prints the fix when it does not fit.

## Kinds

`--kind` takes one of: function, method, variable, field, constant, local,
parameter, property, bool, type, namespace, enumerator, event. Each kind
opens a fixed set of molds; `lookup --kind` is the grammar, this file is not.
