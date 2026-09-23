# Report: Generate the Memory Manager (PMM + VMM), gemma4

**Plan**: `plans/w13-generate-mm.plan.md` · **Pre-registration**: `w13-generate-mm-preregistration.md`
(12:45:13Z, before the run) · **Artifacts**: `.artifacts/authorship/2026-09-22-generate-mm/`

## Result: one header, which does not compile. No allocator

| Gate (in pre-registered order) | Result |
|---|---|
| `run_mm_test.sh` (tree mode) | **exit 2: not generated** (no `kernel/mm/pmm.c`) |
| `run_vmm_test.sh` (tree mode) | **exit 2: not generated** (no `kernel/mm/vmm.c`) |
| `make iso`, `[MM]` boot line | not reached |

The manager planned 4 tasks: interface, pmm, vmm, boot. The run ended at 12:54:26Z, 9 minutes
into a 60-minute budget: `pmm-001 failed (no output …); vmm-001 ended pending; boot-001 ended
pending`.

## What the agent did (tool calls, reconstructed from the transcript)

```
interface-001: read_spec(mm) → write_file(kernel/include/mm.h, 8672 bytes) → success() ×18
               → hit max turns (20) → committed → reviewer approved in 10 s → MERGED
pmm-001:       read_spec(mm) → read_file(mm.h) → pmm_init(...)  (a spec function called as a tool)
               → no output → FAILED
```

This is the **first agent-written file the loop has merged**. In F6 the model never called
`write_file` at all.

## The merged header

- **Interface: 30 of 30 of `mm.md`'s function prototypes present**, 29 exact. The one that
  differs: `pmm_init(const void *mmap)` in place of `const boot_mmap_t *`.
- **It does not compile**: 7 errors. The model's output has token-level corruption
  (`t/* Sub-region …`, `ttypedef enum`), and it uses `slm_region_type_t` where it declared
  `slm_region_t`.
- The reviewer (gemma4) approved it anyway, and nothing mechanical checked it.

## Defects found (fixed after the run, not during it)

| Defect | Fix |
|---|---|
| Nothing compiled a branch before it merged: a model reviewer approved non-compiling C | `syntax_gate.py`: every changed `kernel/` `.c`/`.h` passes `-fsyntax-only` first; a failure goes back to the author with the compiler's errors (`6b349a9`). All 44 base-v5 C files pass it; this `mm.h` does not |
| The mm gate included a `boot.h` that only its reference shipped, with field names `boot.md` does not use: a tree built to spec failed | `boot.md` names `kernel/include/boot.h`; the reference uses the spec's names (`88e0ebf`) |
| Tree mode said "wrong" (exit 1) with no allocator, because the base's `kernel/lib/phys.c` counted as a source | no `kernel/mm/pmm.c` → exit 2 (`88e0ebf`) |
| The wrapper hung 50 minutes after the run ended (`auton_timeout` orphaned `sleep`) | `8c0a368` |

Scored before these fixes, the gate said exit 1 ("wrong") for a tree with no allocator. The
exit-2 result above uses the fixed gate. Both are recorded, and the fixed one is the true one.

## Injected bugs, mapping, mitigation registry

Not applicable: there is no generated `pmm.c` or `vmm.c` to inject into or map.

## Conclusion

The same as F6, one step further: gemma4 can write one file from a spec, but not correct C,
and not past the first task. It stays the owner's gate to choose a capable model. The loop
now refuses what this run merged.

**Fallback, per the plan's risk table**: the downstream plans (storage's DMA pages, H7) need a
memory manager. If one is provided, it is **human-written, labelled human** in the harness, in a
new base tag, so no later authorship count includes it.
