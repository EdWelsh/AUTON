# Plan: Generate the Memory Manager (PMM + VMM) into the Base

## Summary
F3 specified a bitmap PMM (`w1-kernel-pmm-spec`) and `w12-vmm-spec` specifies the VMM. Both are
host-proved, and neither exists in any tree. The base (`kernel-base-v5`) still runs a 12 MiB
bump allocator (`kernel/lib/phys.c`) and prints a `[MM]` marker that "finally means something"
only once this lands. This plan has the loop generate `kernel/mm/pmm.c` and `kernel/mm/vmm.c`
under the Generation Experiment Protocol, gated by `run_mm_test.sh` and `run_vmm_test.sh` in
tree mode and a QEMU boot. It unblocks H7 (F00F) and windows-linux B2 (the same PMM).

## User Story
As the hardware-truth track, I want a tree with a real VMM, so that a page-permission
mitigation can be applied and verified instead of declined.

## Problem → Solution
`vmm` unmapped; `[MM]` reports a bump arena → generated `pmm.c`/`vmm.c` passing both host
suites in tree mode, `source_map.yaml` mapping `pmm`/`vmm` to them **for the generated tree
only**, and a boot printing mm.md's exact `[MM] PMM initialized: <total> … <reserved> … <free>`.

## Metadata
- **Complexity**: Large
- **Source PRD**: `auton-service-kernel-factory.prd.md` (phase 3's implementation); `auton-windows-linux.prd.md` B2
- **PRD Phase**: F3 implementation, B2 (same deliverable), H7 prerequisite
- **Estimated Files**: 5 generated + report
- **Depends on**: `w12-loop-review-repair`, `w12-kernel-base`, `w12-vmm-spec`

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/plans/w13-factory-f6-rerun.plan.md` | "Generation Experiment Protocol" | the protocol this follows, step by step |
| P0 | `agent/kernel_spec/subsystems/mm.md` | 136-280 + w12 REQUIRED sections | the contract |
| P0 | `tests/kernel/run_mm_test.sh` | 28-62 | tree mode: looks for `kernel/include/mm.h` and `kernel/mm/{pmm,vmm,slab}.c` |
| P0 | base `kernel/lib/phys.c`, `kernel/include/phys.h` | all | `dma_alloc` callers (e1000 rings, the neural KV cache) must keep working |
| P1 | base `kernel/boot/kernel_main.c` | 30-60 | where `[MM]` is printed today (`pmm` is a stub count) |
| P1 | `.claude/PRPs/reports/w1-kernel-pmm-spec.md` | "Reserved Regions" | the boot-module region a generator is most likely to hand out |

## Patterns to Mirror
### HOST_SUITE_TREE_MODE
// SOURCE: tests/kernel/run_mm_test.sh:34-61
```bash
for candidate in kernel/mm/pmm.c kernel/mm/slab.c kernel/mm/vmm.c kernel/lib/phys.c; do
	[ -f "$KERNEL_TREE/$candidate" ] && SOURCES="$SOURCES $KERNEL_TREE/$candidate"
done
```
### BOOT_MARKER
// SOURCE: agent/kernel_spec/subsystems/mm.md:233-236: the exact `[MM] PMM initialized:` line.

---

## Files to Change
| File | Action | Justification |
|---|---|---|
| `<ws>/kernel/include/mm.h`, `kernel/mm/pmm.c`, `kernel/mm/vmm.c` | GENERATED | the deliverable |
| `<ws>/kernel/boot/kernel_main.c` | GENERATED (edit) | call `pmm_init`/`vmm_init`; print the exact marker |
| `agent/kernel_spec/source_map.yaml` | UPDATE, after the gates pass | map `pmm`, `vmm` to `kernel/mm/*.c` with a note: *present in generated trees from w13; phantom against `kernel-base-v5`* |
| `agent/tests/unit/test_phantom_mappings.py` | UPDATE | phantom-ness is per tree: the base reports them phantom, a generated tree does not |
| `.claude/PRPs/reports/w13-generate-mm-{preregistration,report}.md` | CREATE | protocol 1, 8 |

## NOT Building
- Removing `phys.c`/`dma_alloc`. DMA callers keep the arena until a DMA-aware allocator is
  specified (mm.md *General vs DMA allocation*). Replacing it is out of scope.
- Slab.
- User-space address spaces beyond the interface.

## Step-by-Step Tasks

### Task 1: Pre-register (protocol 1)
- **GOAL TEXT**: "Implement the physical and virtual memory managers specified in `mm.md` (read_spec mm) in this tree: kernel/include/mm.h, kernel/mm/pmm.c, kernel/mm/vmm.c, and call pmm_init then vmm_init from kernel_main, printing the [MM] marker exactly as mm.md specifies. Do not change kernel/lib/phys.c."
- **VALIDATE**: file timestamped before the run.

### Task 2: One run, archive (protocol 3-4)

### Task 3: Gates (protocol 5)
- **ORDER**: `KERNEL_TREE=<ws> tests/kernel/run_mm_test.sh`, then `run_vmm_test.sh`, then `make -C <ws> iso`, then a QEMU boot asserting the exact `[MM]` line and `[BOOT] OK`.
- **GOTCHA**: `run_mm_test.sh` also picks up `kernel/lib/phys.c` as a candidate source. If the generated `pmm.c` and `phys.c` both define a symbol the test calls, the compile fails. That is a real conflict to report, not a harness bug.
- **GOTCHA**: The boot check needs `-m 256M` or more, or the reserved-regions arithmetic is trivial.

### Task 4: Injected bugs (protocol 6)
- **SET**: the PMM bugs F3 recorded, plus the 5 VMM bugs from `w12-vmm-spec` Task 4, applied to the *generated* files.

### Task 5: Map, measure, report (protocol 7-8)
- **ACTION**: Only after all gates pass, update `source_map.yaml`, then `mitigation_registry.py --capabilities vmm,arch,allocator` reports F00F `mitigable` against the generated tree's slice.
- **VALIDATE**: harness rows against the human references (`mm_reference/pmm.c` 254 lines, `vmm_reference`).

## Validation Commands
```bash
KERNEL_TREE=<ws> tests/kernel/run_mm_test.sh
KERNEL_TREE=<ws> tests/kernel/run_vmm_test.sh
make -C <ws> iso && scripts/e2e.sh --target <ws> --skip-train     # [MM] exact line, [BOOT] OK
```

## Acceptance Criteria
- [ ] Protocol followed, one run
- [ ] Both host suites pass in tree mode, or the report names the failing clause
- [ ] Boot prints the exact `[MM]` line
- [ ] `source_map` updated only if the gates pass

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The loop cannot produce a VMM | H | H for H7 | Reported. Fallback, **stated as such**: a human-written `vmm.c` in the generated tree, labelled human in the harness, so H7 can proceed and F6's question stays uncontaminated |
| The generated PMM hands out the model's module memory | M | H | the "Reserved Regions" test exists precisely for this |
