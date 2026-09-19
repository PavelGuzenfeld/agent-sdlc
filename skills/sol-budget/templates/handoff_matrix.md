# Handoff matrix

§3 of the machine model. One cell per producer/consumer pair the pipeline actually
uses: `inplace`, `convert` or `copy`, and the memory type the buffer lands in.

Every cell that is not `inplace` becomes an explicit node in `dataflow.yaml`, and the
edge names it with `via:`. An unpaid handoff is bytes moving that no floor accounts
for, and `sol.py` lists it under **Hidden handoffs** in the SOL table.

| producer \ consumer | cpu | gpu | dla | vic |
|---|---|---|---|---|
| cpu | inplace / dram | copy / dram | copy / dram | convert / nvmm |
| gpu | copy / dram | inplace / dram | convert / nvmm | inplace / nvmm |
| dla | copy / dram | convert / nvmm | inplace / nvmm | convert / nvmm |
| vic | convert / nvmm | inplace / nvmm | convert / nvmm | inplace / nvmm |

method: <how each cell was established — an API's documented semantics is not
evidence; a measured pointer comparison or a bandwidth delta is>
date: <YYYY-MM-DD>
