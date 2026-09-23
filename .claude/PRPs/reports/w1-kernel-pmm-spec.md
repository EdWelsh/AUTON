# Report: Physical Memory Manager (F3)

**Plan**: `.claude/PRPs/plans/w1-kernel-pmm-spec.plan.md`
**Source PRD**: `auton-service-kernel-factory.prd.md` — phase 3

The first plan whose deliverable is **spec and tests, not code**. `kernels/` is generated
output, so the work is to specify the allocator precisely enough that agents generate it, and
to define the tests that prove they did.

## Spec

`mm.md` gained four REQUIRED sections. The interface was already reasonable — bitmap PMM,
`pmm_free_count`, `pmm_mark_used`; what was missing was everything a generator would have to
infer.

**Reserved Regions.** A table of six, each with the reason. The one that matters:

> **Boot modules** — the model runs in place from its module. It is never copied; that is the
> whole point of the flat format. A PMM that hands this memory out corrupts the running model,
> and the symptom is degenerate output much later, which looks like a bad model rather than an
> allocator bug.

This is the region a generator is most likely to miss, because the memory map reports module
memory as available RAM — from the firmware's point of view it is. Only the module tags say
otherwise, which is why `boot.md` now requires parsing tag type 3, and type 6 (the full memory
map) rather than type 4 (basic memory totals, which says nothing about usability — and is all
the retired tree parsed).

**Bitmap Placement.** The bitmap cannot allocate its own storage, since it is what allocation
depends on. Three steps, with the subtle one stated: after placing and zeroing it, mark the
frames the bitmap itself occupies. A bitmap that does not mark itself is handed out on the
first allocation that reaches it, and every allocation afterwards reads corrupted state.

**General vs DMA allocation.** A table separating them on five axes. `dma_alloc`'s contract is
marked PRESERVED — the retired `lib/phys.c` was a bump allocator with no free, and every
driver plus the neural backend calls it. A generated allocator that silently returns unaligned
or discontiguous memory to a DMA caller produces corruption that presents as a driver bug, far
from its cause.

**kmalloc semantics.** `kmalloc(0)` is NULL, returned memory is not zeroed, failure allocates
nothing, `kfree(NULL)` is legal, and double-free panics rather than being absorbed. `kfree(NULL)`
is called out because every error path ends in a cleanup that frees whatever it got — making
NULL illegal turns each into a branch a generator will eventually forget.

## `[MM]` now means something

The marker was `\[MM\] PMM initialized: \d+ pages free` — satisfied by any number at all,
including a wrong one. It asserted that the line was printed.

It is now `\d+ pages total, \d+ reserved, \d+ free`, and the three must add up. A PMM that
forgot to reserve the boot modules reports `reserved` far too low and fails here, rather than
corrupting a model some minutes later. The acceptance test, the marker set, and the known-good
serial fixture were changed together — the repo already enforces that every marker is claimed
by a real `AcceptanceTest`, and that check caught a half-applied edit during this work.

`pmm_reserved_count()` was added, and `pmm_free_count()` is documented as queryable at runtime
rather than only at boot — which is what lets `slm_init` compute real headroom instead of a
constant, and what lets the chat answer "how much ram is free" with the free figure. It
currently answers with the total, which the eval rubric grades as garbage, and did.

## Tests, and the tests of the tests

`tests/kernel/mm_test.c` + `run_mm_test.sh`, spine-owned and parameterised by `KERNEL_TREE`
for the reason every kernel test is: an agent that generates both an allocator and its tests
can satisfy itself.

23 checks. But these are the deliverable for an allocator that does not exist yet, so a suite
that had never been executed would be an assertion. `tests/kernel/mm_reference/` is a
reference bitmap PMM + slab — not kernel code, never shipped — that the suite runs against
with `--self-test`. All 23 pass.

Writing the reference also pinned an ambiguity in the spec. `mm.md` says `pmm_free_page`
"panics on double-free (bit already clear)", but a *reserved* frame's bit is also set, so the
naive reading lets `pmm_free_page` release the kernel image. Recorded in the reference:
freeing a frame that was never allocated is the same class of bug and is treated the same way.

Then the suite was mutation-tested — a test that passes against a correct implementation but
does not fail against a broken one is worth nothing:

| Mutation | Caught |
|---|---|
| PMM ignores `pmm_mark_used` | 3 failures |
| Frame 0 becomes allocatable | 3 failures |
| `dma_alloc` ignores alignment | 1 failure |
| `kmalloc(0)` returns a pointer | 1 failure |
| `kzalloc` does not zero | 1 failure |
| `free_count` ignores reserved | 4 failures |
| `pmm_alloc_contiguous` ignores reserved frames | 4 failures |
| `kfree(NULL)` traps | process aborts |
| `mark_used` rounds start up, not down | **initially missed** |
| `mark_used` rounds end down, not up | **initially missed** |

The last two were a real hole: both reserved regions in the test were page-aligned, so the
spec's "round start down, end up" rule was never exercised. A third reserved region was added
at a deliberately ragged offset (`0x3001123`, length `0x1456`). Both mutations are now caught.

## Acceptance

- [x] `mm.md` specifies the bitmap PMM, reserved regions, and `kmalloc`/`kfree` implementably
- [x] Boot modules explicitly reserved, with the reason stated
- [x] `[MM]` reports total/reserved/free; free memory queryable at runtime
- [x] Host-side allocator tests in `tests/kernel/`, taking `KERNEL_TREE`
- [ ] **A generated kernel passes both the allocator tests and the markers stage** — cannot be
      met yet. No tree contains `kernel/include/mm.h`; the runner exits 2 ("not generated")
      rather than 1 ("generated wrong"), because an absent allocator must not read as a
      failing one.

## Follow-on

- The last acceptance item is the real test of whether these specs are generation-grade, and
  it needs agents that dispatch and a workspace they cannot clobber (the F6 blocker).
- Two generations from the same spec diverging is the signal worth measuring when that lands.
- `mm.md`'s `pmm_free_page` wording should be tightened to say "a frame that is not currently
  allocated", which covers both double-free and freeing a reserved frame.
