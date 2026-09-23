# R1 — memory manager, qwen3.5:27b: the run did not finish

**Pre-registration**: [w15-mm-qwen-preregistration.md](./w15-mm-qwen-preregistration.md), written before the run.
**Run**: 2026-09-23 12:40:38Z → 17:40:38Z. Exactly `ORCH_TIMEOUT=18000`, so the
run was **cut off, not completed**. 60 turns allowed, `ollama_chat/qwen3.5:27b`.

## Verdict, by the gates named before the run

| Gate | Exit | Meaning |
|---|---|---|
| `run_mm_test.sh` | **1** | generated wrong |
| `run_vmm_test.sh` | **2** | not generated |
| `[MM]` boot line | n/a | nothing links; the line exists in `pmm.c` and has never run |

Exit 2 on VMM is correct and uninteresting: `vmm.c` was never reached. Exit 1 on
MM is the result worth reading.

## What five hours produced

| Task | State |
|---|---|
| `kernel/include/mm.h` | **approved** |
| `kernel/mm/pmm.c` | in progress — 13,982 bytes on disk, never committed |
| `vmm.c`, `slab.c`, `slm_pool.c`, `mm_test.c` | never started |

One of six tasks closed. Three commits, 524 lines, all additions, all on-topic —
`mm.h`, `arch_memory.h`, `arch_context.h`. **No scope creep**, which is the
second data point for Open Question 4: the TFTP run's architect rewrote a
709-line unrelated header, and this one did not.

The decomposition included a test task. The TFTP run never produced one, so
Open Question 1 ("does the swarm's own verification hold up?") now has a plan
behind it and still no evidence — the task never ran.

## The two real defects

Both are in `pmm.c`, and both are the agent's:

1. **It invented the dependency's type.** `mm.md` says *"boot: provides
   `boot_mmap_t`"* and `boot.md` says that type is declared in
   `kernel/include/boot.h`. The agent declared its own `boot_mmap` inside
   `mm.h` instead, with a Multiboot2-shaped layout — `entry_count`,
   `entry_size`, `entry_version`, `entries[256]` — where the spec says `count`,
   `total_available`, `highest_address`, `entries[128]`.

2. **`pmm_free_pages` is internally inconsistent.** Called at line 407 before
   any declaration, then defined at 462 with a conflicting signature
   (`uint64_t` where the call passes a pointer). Also discards `const` on
   `mmap->entries` in two places.

## The gate could not say any of that until it was fixed

On the first run both gates were blocked at a wall: `run_mm_test.sh` exited 1
with *"no kernel/include/boot.h"* and never compiled anything. That check
demanded an artifact from the **boot** subsystem — a different subsystem, not in
this goal's scope, not in the base tree, and not mentioned in the goal.

This is the `tftp_stub` defect again: a gate requiring something outside the
scope of what it verifies. There it shadowed `libk` and hid a working TFTP
server for a day. Here the grade was accidentally right — exit 1 is the correct
grade — but the diagnosis was absent, and for a project whose thesis is *"the
gate decides and says why"*, a right grade with no reason is half a result.

The fix follows the established pattern: when the tree has no `boot.h`, the gate
falls back to the spec-derived reference header and says so on stderr. A
tree-supplied `boot.h` still wins, because `-I` puts the tree first. The
self-test still passes against the reference, so the suite is unchanged as
evidence.

## What this does not tell us

- Whether the allocator is *correct*. It never compiled, so no assertion ran.
- Whether 60 turns is enough. The run was cut by wall-clock, not by turns.
- Whether a faster model would do better. `qwen3.5:9b` also qualifies 4/4 and is
  roughly twice as fast; on this evidence, throughput is the binding constraint,
  not capability, and that is now the more interesting experiment.

## Recommendation

R1 is **not done**. Re-run with a longer budget or a faster model, and treat the
five-hour ceiling as the thing to change: one approved task and one
half-written file in five hours is a throughput result, not a capability one.
