# Reference Graphs

Structural graphs of kernel trees, extracted by `agent/tools/kernel_graph.py`.

## What these are for

AUTON's premise is that **agents write the kernel** (`README.md:11`). A hand-written tree is
therefore a *reference*, not a product — and what is worth keeping from a reference is its
structure, not its text.

`graph.json` holds every function with its real signature, call edges in both directions,
structs, enums, macros, per-file includes, and a subsystem dependency graph.
`spec-to-implementation.jsonl` pairs each spec section with the symbols that implement it.

Two uses, both of which the source serves badly:

**Fine-tuning.** `(spec section → symbols, signatures, call shape)` is a far denser training
signal than raw C, and it survives a rewrite in a different style or for a different
architecture. A model trained on the text of one x86_64 implementation learns that
implementation; a model trained on the graph learns the *contract*.

**Vendor-documentation alignment.** Vendor docs describe registers, offsets and protocols. The
graph records which function touched which constant, so doc text can be aligned to real
binding code — the training pair becomes `(vendor doc excerpt → the driver shape that binds
it)` rather than a guess.

## Regenerating

```bash
python agent/tools/kernel_graph.py --arch x86_64 --output agent/kernel_spec/reference/x86_64
```

The graph records `source_commit`, so a graph can always be traced to the tree it came from —
including after that tree is retired.

## Caveats

- Call edges come from clang's AST. Indirect calls through function pointers (the driver
  `ops` tables, the SLM backend vtable) do **not** appear; those relationships live in the
  spec, not the graph.
- Macros are preprocessor-only and never appear in an AST, so they are extracted textually
  and carry no type information.
- A graph is not buildable or bootable. It preserves what a working implementation looked
  like; it does not preserve a working implementation.

## Bases

Two tagged trees exist. Neither is in `main`; `kernels/` is gitignored and a test
(`test_scaffold.py::TestTheRepoContainsNoKernel`) keeps it out of the index.

| Tag | Commit | What it is | Use it for |
|---|---|---|---|
| `kernel-reference-v1` | the retired hand-written tree | the source of this directory's graph and training pairs | reading, never as an experiment base |
| `kernel-base-v2` | `70f3e49` (`5fb2777^`) | v1 + F4's factory hooks: the static-IP branch in `net/setup.c` (+22) and a weak `service_main` in `boot/kernel_main.c` (+10) | **every generation experiment** |

`scripts/kernel-base.sh <dir> [--git] [--rev TAG]` extracts one. The difference matters:
seeded from v1, a TFTP service is refused at `[gate: link closure] no stub signature for:
dhcp_run` before any service code is considered; from v2 it is refused only at `undefined:
tftp_serve`, which is the agent's job. `test_kernel_base.py` pins both.
