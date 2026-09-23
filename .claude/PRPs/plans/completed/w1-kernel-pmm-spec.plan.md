# Plan: Physical Memory Manager (F3)

**Source PRD**: `.claude/PRPs/prds/auton-service-kernel-factory.prd.md` — phase 3
**Complexity**: Medium — and the first phase written to be *generated*, not hand-written
**Unblocks**: F7 (storage), every service needing dynamic allocation

## Summary

`[MM] PMM initialized: 32639 pages free` is asserted by the boot marker set and means almost
nothing: the retired tree's `lib/phys.c` provided `dma_alloc` — a bump allocator with no free
— and there was no `kmalloc`/`kfree` at all. Every service beyond a static serve loop needs
real allocation.

This is the first plan where the deliverable is **spec, not code**. `kernels/` is gitignored
as agent-generated output, so the work is: specify the allocator precisely enough that agents
generate it, and define the tests that prove they did.

## Evidence

- `reference/x86_64/graph.json` — the `lib` subsystem was 5 files, 300 lines, 22 functions,
  and provided `dma_alloc(size, align)` as its only allocator. No free path.
- `neural_backend.c` allocated every runtime buffer through `dma_alloc` and never released
  one — correct for a single-model boot, useless for a service that handles requests.
- `subsystems/mm.md` exists (the spec), and the retired implementation covered a fraction of it.
- Boot marker `\[MM\] PMM initialized` is in `SERIAL_MARKER_SETS["boot"]`, so a generated
  kernel must still emit it or the spine's markers stage fails.
- `slm.c`'s backend selection needs `module_size + NEURAL_HEADROOM_MB` — headroom that is
  currently guessed rather than measured, because nothing tracks real free memory.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Existing allocator surface | `agent/kernel_spec/reference/x86_64/graph.json` → `dma_alloc(size, align)` | Signature to preserve; the generated PMM must keep DMA-suitable aligned allocation working |
| Boot marker contract | `acceptance_tests.py` `SERIAL_MARKER_SETS["boot"]` | `\[MM\] PMM initialized` — single-sourced; the generated kernel satisfies it, nobody edits the shell |
| Freestanding constraint | `slm.md` "Degenerate Output Guard (REQUIRED)" | Allocation-free, no libc — the house style for kernel-side requirements |
| Honest failure | `slm.md` "Untrusted Module Validation" | Named reasons, not a single failure code |
| Memory map source | `boot_info.c` Multiboot2 tag walk | Basic-memory tag (type 4) already parsed; the full memory map (type 6) is not |

## Files to Change

| File | Action | Why |
|---|---|---|
| `agent/kernel_spec/subsystems/mm.md` | UPDATE | Specify the bitmap PMM, `kmalloc`/`kfree`, and the reporting contract |
| `agent/kernel_spec/services/` (n/a) | — | Not a service; a subsystem capability |
| `tests/kernel/mm_test.c` + runner | CREATE | Host-side allocator tests, spine-owned |
| `agent/kernel_spec/subsystems/boot.md` | UPDATE | Require the Multiboot2 memory-map tag (type 6), not just basic memory |

## Tasks

### Task 1: Specify the physical allocator
- **Action**: Bitmap over physical frames, sized from the Multiboot2 memory map. Specify:
  frame size, the bitmap's own placement (it must not allocate itself), reserved-region
  handling (kernel image, boot modules, firmware-reserved), and the `[MM]` report format.
- **Critical**: boot modules are reserved. The model runs **in place** from its module, so a
  PMM that hands that memory out corrupts the running model — an easy and catastrophic
  generated bug.
- **Validate**: the spec states which regions are reserved and why, in terms a generator can
  implement without inferring.

### Task 2: Specify `kmalloc` / `kfree`
- **Action**: A small-object allocator over the PMM. Specify alignment guarantees,
  the failure return, and whether `kfree(NULL)` is legal (it should be). Keep `dma_alloc`'s
  contract intact — physically contiguous, caller-specified alignment — since drivers depend on it.
- **Why explicit**: a generated allocator that silently returns unaligned memory to a DMA
  caller produces corruption that looks like a driver bug.
- **Validate**: the spec distinguishes DMA-suitable allocation from general allocation.

### Task 3: Make `[MM]` mean something
- **Action**: The marker currently reports a number nothing verifies. Specify that the PMM
  reports total, reserved, and free frames, and that free-frame count is queryable at runtime
  — which is what lets `slm_init` compute real headroom instead of a constant, and what lets
  the chat answer "how much memory is free" truthfully. Phase 7 recorded that AUTON answers
  that question with the **total**, which the rubric grades as garbage.
- **Validate**: the marker set gains a pattern asserting the richer report; `run-acceptance`
  still passes against a generated kernel.

### Task 4: Host-side allocator tests
- **Action**: `tests/kernel/mm_test.c`, mirroring `degenerate_test.c` — compile the generated
  allocator on the host with a stub memory map and exercise it: exhaustion, fragmentation,
  double-free, `kfree(NULL)`, alignment, and reserved-region integrity.
- **Why spine-owned**: verification must not live inside the artifact it verifies. Kernel tests
  moved to `tests/kernel/` for exactly this reason.
- **Validate**: the suite runs via `KERNEL_TREE=<dir> tests/kernel/run_mm_test.sh` against any
  generated tree.

## Validation

```bash
# once a tree is generated:
KERNEL_TREE=<target> tests/kernel/run_mm_test.sh
scripts/e2e.sh --target <target> --skip-train      # markers stage must still pass
# and the chat answer that motivated Task 3:
scripts/eval.sh --model <model>                    # "how much ram is free" should stop being garbage
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| A generated PMM hands out boot-module memory | **M** | Task 1 makes reserved regions explicit; Task 4 tests reserved-region integrity directly |
| Spec is too loose and each generation differs | **H** | This is the first real test of whether the specs are generation-grade. Divergence between two generations is the signal, and it is worth measuring |
| `dma_alloc` contract broken by the rewrite | **M** | Preserve the signature and test alignment explicitly; drivers depend on physical contiguity |
| Blocked behind the scheduler fix | **H** | It is. Until agents dispatch, this plan produces spec and tests only — which is still the majority of the work |

## Acceptance
- [ ] `mm.md` specifies the bitmap PMM, reserved regions, and `kmalloc`/`kfree` implementably
- [ ] Boot modules are explicitly reserved, with the reason stated
- [ ] `[MM]` reports total/reserved/free, and free memory is queryable at runtime
- [ ] Host-side allocator tests exist in `tests/kernel/` and take `KERNEL_TREE`
- [ ] A generated kernel passes both the allocator tests and the spine's markers stage
