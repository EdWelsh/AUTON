# w18 R1: memory manager, attempt 2. Result: generated wrong (1, 1, 0)

**Pre-registration:** [w18-r1-mm-9b-preregistration.md](w18-r1-mm-9b-preregistration.md), amendments 1–7.
**Model:** Claude Sonnet 5.5 through the owner's subscription (`claude-cli/claude-sonnet-5-5`).
**Run:** `.artifacts/campaign/r1-mm-attempt2/`, 2026-10-03 00:17Z–07:04Z.
**Stop rules:** this is the last attempt (rule 1). Both attempts ended in exit 1, so the phase
fails (rule 3), with fallback `none`. Its dependants (R2, R10, R11, R12) build on `kernel-base-v5`.

## Verdict

| Gate | Original | After the gate repair | What decided it |
|---|---|---|---|
| `run_mm_test.sh` | 1 | **1** | `pmm.c` halts with x86 `cli; hlt` inline assembly. That's portable code; architecture.md puts halt behind `arch_halt()`, and the host suite (arm64) can't assemble it. |
| `run_vmm_test.sh` | 1 | **1** | `mm.h` defines `phys_to_virt` as `static inline` identity. mm.md makes it a hook the VMM reaches through, declared in `vmm_host.h` so a test can substitute it, so the suite's definition collides. `vmm.c` also calls `arch_write_root`, which isn't in the spec's hook list. |
| boot `[MM]` line | 1 | **0** | `[MM] PMM initialized: 65504 pages total, 363 reserved, 65141 free` (256 MiB, 4 KiB frames). |

The original verdict is kept in `RESULT.json` under `gate_history`.

## Gate defects found and fixed (stop rule 5)

Re-grading exposed four defects in the gates. Fixed in `17e688b`; none of them changes a verdict
the code earned.

1. **The boot gate never booted.** `scripts/e2e.sh` trains, exports and checks SLM parity before
   it boots, and parity fails on the untouched base tree too: the current SLM model doesn't load
   in the base kernel's runtime. It was replaced by `scripts/boot-marker.sh`, which builds the
   plain ISO with the cross toolchain and waits for one serial marker. It was checked on three
   controls: the marker present exits 0, the marker absent exits 1 (`pmm_init` removed from a
   copy), and no tree exits 2. R10's gate had the same defect and uses the new script too.
2. **The allocator suite supplied nothing an allocator that follows the spec must link to:**
   - `kprintf`, for the REQUIRED `[MM]` report line;
   - the `__kernel_start`/`__kernel_end` linker symbols, for the REQUIRED reservation of the
     kernel image;
   - `phys_to_virt`, for the REQUIRED self-placed bitmap;
   - `arch_halt`.

   `tests/kernel/mm_host_env.c` now provides weak host versions. The reference passed only
   because it skips those requirements.
3. **The allocator suite linked `vmm.c`,** whose HAL hooks only the VMM suite provides.
4. **It also linked the seed `phys.c`,** which this tree retires from its build (by a Makefile
   filter, leaving the file unmodified as the goal required), giving a duplicate `dma_alloc`.

**Injected-bug score of the allocator suite:** 5 of 7 both before and after the repair, so the
repair didn't weaken it. The two misses were always missed, and are now on w23:
- a double free that is absorbed rather than caught, which the suite's own header claims to test;
- an off-by-one at the end of RAM in `pmm_alloc_contiguous`.

## How close it came (a diagnostic, not a verdict)

On a copy with the two deviations patched (`phys_to_virt` declared rather than defined, and
`arch_halt()` for the asm), the allocator passes the first 15 checks. It then faults in
`dma_alloc`, zeroing a block through the physical address it returns. mm.md says `dma_alloc`
returns an identity-mapped physical address, so that write is correct on the target and
impossible in a host process. Whether the host suite should model it is a gate question for w23,
not a defect in this code. The VMM suite needs a stub for `arch_write_root` before it gets that
far.

## What the run did

| Measure | Value |
|---|---|
| Sessions | 2: 17,913 s (budget pause) + 6,388 s (terminal) |
| Of that, waiting on the subscription's spend limit | 25 × 15 min ≈ 6.25 h. The work itself took about half an hour |
| Tasks | 6 created, **6 merged**; one review round, on `mm-002` |
| Commits on main | 15 |
| Lines | +1,493 / −32 across 13 files |
| Outside the goal's files | `boot.h`, `boot_info.*`, `init_sequence.h`, HAL and linker additions: all inputs mm.md names (boot handover, kernel-extent symbols, MMU hooks). No scope creep beyond the spec's own dependencies |
| Test task | `tests/mm_pmm_smoke.py` written by the agents; not one of the gates |
| Harness retries | 1 refused native tool call, recovered by a nudge |

## Reading

This is the first R1 to write the whole memory manager. It merged every task, and the result boots
with a working PMM. The two deviations that fail it are interface discipline, not allocator logic:
- a hook hard-coded as an inline identity map;
- architecture-specific assembly in portable code.

Each is one line from conforming, and both are the kind a reviewer agent reading mm.md's
"Those are exactly the hooks" paragraph should catch. Neither the reviewer nor the tester ran
the frozen suites. That's the swarm's gap this result points at, and it's on w23.
