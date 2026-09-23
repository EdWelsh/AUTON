# Plan: Virtual Memory Manager Spec, Host-Proved

## Summary
`vmm` is phantom: `source_map.yaml:72` maps it to `kernel/mm/vmm.c`, which has never existed, and
the seed tree identity-maps 4 GiB with **2 MiB** pages from `boot.S`. H7's F00F mitigation needs a
read-only **4 KiB** page, so hardware-truth is blocked on a VMM. This plan does for the VMM what F3
did for the PMM: REQUIRED spec sections a generator cannot misread, and a host-run test suite
proved against a reference. The implementation itself is generated (w13), not hand-written.

## User Story
As the agent loop generating a kernel, I want a VMM spec with executable tests, so that a
generated page-table implementation is either proved or refused, and H7 has something to mitigate
F00F with.

## Problem → Solution
`mm.md` lists a VMM interface with no page-split rule, no permission-change call, and a phantom
mapping → REQUIRED sections (huge-page split, permission change, TLB rule, intermediate-table
allocation and OOM), `tests/kernel/vmm_test.c` + `vmm_reference/` under ASan/UBSan, and the
phantom mappings removed until a tree implements them.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-service-kernel-factory.prd.md` (mm subsystem); unblocks `auton-hardware-truth.prd.md` H7
- **PRD Phase**: none by number; recorded in `prds/ELIGIBILITY.md` §3
- **Estimated Files**: 8

---

## UX Design
Internal. Before, `resolve(["vmm"])` → `phantom_capabilities: [slab, vmm]`. After, `vmm` and `slab`
are **unmapped** (honest), and `tests/kernel/run_vmm_test.sh --self-test` prints PASS for every
REQUIRED clause.

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/reports/w1-kernel-pmm-spec.md` | all | the pattern: spec + tests, not code |
| P0 | `agent/kernel_spec/subsystems/mm.md` | 37-63, 197-280 | VMM types and interface; the PMM's REQUIRED sections to mirror |
| P0 | `tests/kernel/run_mm_test.sh` | 1-62 | `--self-test` vs `KERNEL_TREE`: verification lives outside the artifact |
| P0 | `tests/kernel/mm_test.c` | 1-60 | `ok()` style, a synthetic machine, ragged-edge cases |
| P1 | `agent/kernel_spec/arch/hal.md` | 70-95 | `arch_mmu_init`, `arch_map_page`, `arch_unmap_page` |
| P1 | `agent/kernel_spec/mitigations/f00f-idt-remap.md` | all | the first consumer: a 4 KiB read-only page inside a 2 MiB mapping |
| P1 | `agent/kernel_spec/source_map.yaml` | 1-45, 68-74 | the phantom rule and its header |
| P2 | `tests/kernel/mm_reference/pmm.c` | all | the reference style |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| x86-64 4-level paging | Intel SDM Vol. 3A §4.5 (inventoried as `intel-sdm`) | PTE bits: P=0, RW=1, US=2, PWT=3, PCD=4, PS=7 (in PDE/PDPTE), XD=63 (needs EFER.NXE) |
| TLB invalidation | Intel SDM Vol. 3A §4.10.4 | `invlpg` per page; a PS-bit change (split) needs the old 2 MiB entry invalidated |

KEY_INSIGHT: splitting a 2 MiB page means allocating one PT, filling 512 PTEs with the huge page's
frame + i·4 KiB and its flags minus PS, then swapping the PDE and invalidating.
APPLIES_TO: Task 2 (split rule), Task 4 (tests).
GOTCHA: PAT (bit 7 in a PTE) sits where PS sits in a PDE. Copying the PDE flags verbatim into the
PTEs sets PAT, not "huge". The reference must mask it.

---

## Patterns to Mirror

### SPEC_REQUIRED_SECTION
// SOURCE: agent/kernel_spec/subsystems/mm.md:197-215 ("Reserved Regions (REQUIRED)")
A table of rules, each with the reason and the failure symptom a generator would otherwise hit.

### TEST_STRUCTURE
// SOURCE: tests/kernel/mm_test.c:30-38
```c
static void ok(const char *name, int cond, const char *detail)
{
	if (cond) { printf("PASS  %-46s\n", name); }
	else { printf("FAIL  %-46s  %s\n", name, detail ? detail : ""); fails = 1; }
}
```

### RUNNER
// SOURCE: tests/kernel/run_mm_test.sh:15-27. `--self-test` builds against the reference with
`clang -O1 -g -fsanitize=address,undefined`; otherwise it builds against `$KERNEL_TREE`.

---

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/subsystems/mm.md` | UPDATE | REQUIRED: huge-page split, `vmm_protect`, TLB rule, table allocation/OOM, the boot handover |
| `agent/kernel_spec/arch/x86_64.md` | UPDATE | PTE bit table, cited to SDM §4.5 |
| `tests/kernel/vmm_reference/{vmm.c,include/vmm.h}` | CREATE | a page-table implementation over a simulated physical arena |
| `tests/kernel/vmm_test.c` | CREATE | a test per REQUIRED clause |
| `tests/kernel/run_vmm_test.sh` | CREATE | mirrors `run_mm_test.sh` |
| `agent/kernel_spec/source_map.yaml` | UPDATE | remove `vmm`/`slab` phantom entries, with a comment as w8 did for `framebuffer` |
| `agent/tests/unit/test_phantom_mappings.py` | UPDATE | no capability is phantom against `kernel-base-v2` |
| `.github/workflows/portability.yml` | UPDATE | run `run_vmm_test.sh --self-test` beside `run_mm_test.sh` |

## NOT Building
- `kernel/mm/vmm.c` in a tree. That is generated in `w13-generate-mm` and measured.
- User address spaces beyond the interface already in `mm.md`. Nothing consumes them yet.
- The slab allocator. It stays unmapped and specified; no consumer needs it.

---

## Step-by-Step Tasks

### Task 1: Tests first (RED)
- **ACTION**: `vmm_test.c` against a `vmm.h` declaring the `mm.md` interface plus `vmm_protect`. The simulated machine is a 64 MiB arena standing in for physical memory, a `phys_to_virt` shim, and a frame allocator that can be told to fail after N frames.
- **IMPLEMENT**: map→translate; unmap→0; a map needing 3 new intermediate tables allocates exactly 3; OOM on the 2nd intermediate returns -1 and frees the 1st; protect a 4 KiB page inside a 2 MiB mapping → 512 PTEs, the target read-only, its 511 neighbours unchanged, the old PDE invalidated; NX set/clear; `vmm_map_page` over an existing mapping replaces it and records one invalidation.
- **MIRROR**: TEST_STRUCTURE; the synthetic machine from `mm_test.c:40-60`.
- **GOTCHA**: Record `invlpg` in the shim as a call log, because the tests assert *which* addresses were invalidated. A VMM that forgets the TLB passes every translate test.
- **VALIDATE**: fails to link with no reference (RED).

### Task 2: Spec, REQUIRED sections
- **ACTION**: Add to `mm.md`:
  - *Huge-page split (REQUIRED)*: when a 4 KiB operation lands in a PS mapping, split first; PAT vs PS masking; invalidate the 2 MiB entry.
  - *Permission change (REQUIRED)*: `int vmm_protect(uint64_t virt, uint64_t flags)` changes flags only, keeps the frame, and invalidates. F00F is the named consumer.
  - *Intermediate tables and OOM (REQUIRED)*: tables come from `pmm_alloc_page`, are zeroed, and a partial allocation is unwound.
  - *Boot handover (REQUIRED)*: `vmm_init` adopts the boot identity map (4 GiB, 2 MiB pages) rather than rebuilding it, and says which ranges it keeps.
- **MIRROR**: SPEC_REQUIRED_SECTION. Each rule carries its failure symptom.
- **VALIDATE**: `capability_slice.py` still parses `mm.md`; each REQUIRED heading has at least one test in Task 1.

### Task 3: The reference (GREEN)
- **ACTION**: `vmm_reference/vmm.c` implementing x86-64 4-level tables over the arena.
- **GOTCHA**: The XD bit is only valid with EFER.NXE. The reference asserts the HAL reports NX support before setting bit 63, and the spec says what happens without it (the flag is ignored and logged once).
- **VALIDATE**: `tests/kernel/run_vmm_test.sh --self-test` gives PASS, 0 failures, under ASan/UBSan.

### Task 4: Inject bugs, publish the ratio
- **ACTION**: Inject, one at a time: forgotten invalidation; PS copied into PTEs as PAT; split drops the neighbours' W bit; OOM leaks the first table; `vmm_get_physical` ignores the page offset.
- **VALIDATE**: each is caught. Record caught/injected in the report, as V5 and V6 did.

### Task 5: Truth up the source map
- **ACTION**: Delete `vmm:` and `slab:` from `source_map.yaml:72-73`, with the w8-style comment (*specified, not implemented; an absent mapping refuses honestly*).
- **GOTCHA**: `mitigation_registry.assess` then reports F00F **declined (image lacks vmm)** for every image, which is correct until w13 generates one. Check `test_machine_safety.py` expectations.
- **VALIDATE**: `resolve(["vmm"], [], base)` reports `vmm` unmapped, not phantom.

### Task 6: CI
- **ACTION**: Add a step to `portability.yml` after "Allocator suite".
- **VALIDATE**: the workflow YAML parses; the step runs on both matrix hosts.

## Testing Strategy
| Test | Input | Expected | Edge? |
|---|---|---|---|
| translate | map 0x400000→0x1234000 | `vmm_get_physical(0x400123) == 0x1234123` | offset |
| split | protect one page in a 2 MiB map | 512 PTEs, 1 changed, PDE invalidated | yes |
| PAT trap | split | no PTE has bit 7 set | yes |
| OOM unwind | fail the 2nd table alloc | -1, frame count restored | yes |
| NX | set, then clear | bit 63 tracks the flag | |

## Validation Commands
```bash
tests/kernel/run_vmm_test.sh --self-test
tests/kernel/run_mm_test.sh --self-test
cd agent && ../.venv/bin/python -m pytest tests/unit/test_phantom_mappings.py tests/unit/test_machine_safety.py -q
cd agent && ../.venv/bin/python -m pytest -q
```

## Acceptance Criteria
- [ ] Four REQUIRED sections in `mm.md`, each with tests
- [ ] Reference passes under ASan/UBSan; the 5 injected bugs are caught
- [ ] `vmm`/`slab` no longer phantom
- [ ] CI runs the suite on both hosts

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The host simulation diverges from real paging | M | H | tests assert PTE bit patterns from SDM §4.5, not just behaviour; w13 boots the generated VMM under QEMU |
| Adopting the boot map carries 2 MiB assumptions forward | M | M | the split rule makes 4 KiB work possible inside it |
