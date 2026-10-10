# Pre-registration: campaign re-run with frozen interfaces seeded (w23)

**Written 2026-10-10, before the run.** A *different experiment* from the 2026-10-03..10 campaign,
labelled as one. The first campaign's verdicts (1 of 12 passed) are kept in
`.artifacts/campaign-invalid-2026-10-10/` and are not overwritten.

**What the failures showed** (gate logs, not guesses):

| Run(s) | Cause | Kind |
|---|---|---|
| R3, R4, R5, R6, R9, R11 | the frozen host suite compiles against identifiers (`conn.status`, `KV_SHUTDOWN`, `smtp_reset`, `HR_PATH_MAX`, `fdt_bootargs`, `fh_event_t`) the spec does not declare and the session never saw | spec/harness |
| R1 | `pmm.c` halted with inline `cli; hlt`; the host suite builds the allocator on the Mac, where `arch_halt()` is the only portable halt | spec gap (now in mm.md) |
| R2 | its FAT32 suite compiled against `vfs_register_fs` etc. not in the spec; boot acceptance passed | spec/harness |
| R7 | the local fallback's single request exceeded the 1800 s timeout after Claude's limit | capacity |
| R10 | the orchestrator crashed on `git merge --abort` when git refused a merge over untracked files | orchestrator bug (fixed, tested) |
| R12 | the gate's `make iso` found no `grub-mkrescue` (127) | gate defect (fixed) |

**Change:** each run whose suite has a reference implementation is seeded with
`tests/kernel/<x>_reference/include` (as R8, the only pass, was) and its goal names it; mm.md
requires `arch_halt()`; R12's gate uses the toolchain's tools; the merge fix; resume-after-pause.

**Prediction:** the compile-interface failures disappear (R3–R6, R9, R11 get past gate 1's
compile step). I do not predict they all pass: behavioural bugs in the generated code are
untested so far, and R7 may still hit the local timeout. A pass on any run is a result; a
failure at a *later* gate than before is progress; the same compile failure again would
falsify this diagnosis. Stop rule unchanged: two attempts each.
