# R1 memory manager, attempt 1 on the local model (w25 attempt 3, amended 2026-10-19)

**Run:** `r1-mm-attempt1`, `ollama_chat/qwen3-coder:30b`, one 5 h session: 16,784 s of work, 0 s waiting. Context 65,536 for
the first hour and a half, then 32,768 (see the pre-registration's amendments). Two harness defects were found and fixed on the way
(w24 F-12: a timeout left a QEMU grandchild holding the pipe and hung the run; and the 64k-token window made every compaction a
9 minute re-read). Neither changed the goal, the gates or the stop rule. The orchestrator was restarted twice and resumed from its
saved state; the first session's console transcript was overwritten.

**Verdict: did not pass** (gate exits -6, 1, 0). Attempt 2 started automatically.

| Gate | Exit | What it said |
|---|---|---|
| `run_mm_test.sh` | -6 (abort) | compiled and ran 23 checks. FAIL: hands out exactly the free count, reports empty when drained, returns NULL when exhausted, a freed frame is reusable, a run ending at the last frame is found, contiguous allocation (3), `dma_alloc` alignment, kmalloc distinct pointers, kmalloc pointer alignment. PASS: `kmalloc(0)` is NULL, `kzalloc` zeroes. Then `phys_to_virt(0x10a629000): outside the test's RAM` and abort |
| `run_vmm_test.sh` | 1 | 11 compile errors: `PAGE_SIZE` undeclared. `mm.md` line 21 defines it (`#define PAGE_SIZE ARCH_PAGE_SIZE`); the model's `mm.h` does not |
| `[MM] PMM initialized` boot marker | 0 | passes on the untouched base kernel, which prints that line itself; not evidence of generation |

**What the tree held:** `kernel/mm/{mm,pmm,slab,vmm}.c`, `kernel/include/{mm,vmm}.h`, 27 commits on main, and a committed `vmm.o`
(the kernel base has no `.gitignore` for objects). Eleven tasks created, four then six merged, two failed review after three rounds
(mm-009: missing `pmm_free_page`, undefined `PAGE_SIZE`, link errors).

**Against the pre-registered hypothesis** ("R1's earlier failure was lost feedback, not capability"): the swarm saw behaviour
through `run_gate` 87 times, and the final tree still fails the allocator's basic accounting. Falsifier ("the final tree fails the
same behavioural checks after the swarm was shown them every iteration") is **met by this attempt**. Attempt 2 is the second and last
under the stop rule; the conclusion is drawn after it. The first reading is model capability at 30B-A3B, not a harness fault.

**Harness observations worth keeping:** the interface the model must match was in the goal and the spec (`PAGE_SIZE`), and the model
missed it for five hours while the reviewer named it; the reviewer's "approved" and the gate's verdict disagreed in both directions;
every compaction cost minutes at 60k tokens of context.
