# w24: investigating the eleven failed generation runs

**Written 2026-10-10** from the gate logs and session logs of the first full campaign
(archived in `.artifacts/campaign-invalid-2026-10-10/`). One pass in twelve (R8). This plan
says, for each failure, what the evidence shows, the cause, what was changed, how it is tested,
and what is still unknown. Fixes already made are marked **FIXED**; what still needs a run to
confirm is marked **VERIFY**; what is not understood is marked **OPEN**.

The campaign verdict is each run's *gates*, not the orchestrator's own "success" flag. Several
sessions ended "Orchestration failed: composition check failed" with every task merged; that
message is the engine's extra check and is not what decides a run (see F-8).

## Summary table

| Run | Gate that failed | Cause class | Status |
|---|---|---|---|
| every run | the engine's own verdict, always failed | impossible check | FIXED |
| R1 mm | suite compile, then (attempt 2 of the re-run) no code at all | spec gap + orchestrator crash | FIXED, VERIFY |
| R2 storage | FAT32 suite link | spec gap (link contract) | FIXED, VERIFY |
| R3 fileserver | suite compile; one run died at iteration 0 | interface not seen + git bug | FIXED, VERIFY |
| R4 kvstore | suite compile | interface not seen | FIXED, VERIFY |
| R5 smtp | suite compile; one task lost to a timeout | interface not seen + local timeout | FIXED, VERIFY |
| R6 host-repo | suite compile; run died on checkout | interface not seen + git bug | FIXED, VERIFY |
| R7 ssh | not generated | local timeout; sources not staged (attempt 1) | FIXED, OPEN (cause of slow calls) |
| R9 aarch64 | suite compile | interface not seen | FIXED, VERIFY |
| R10 F00F | marker absent; run died on checkout | gate wrote into the tree + git bug | FIXED, VERIFY |
| R11 conformance | suite compile; run died on checkout | interface not seen + git bug | FIXED, VERIFY |
| R12 Doom | image never built, probe failed | gate defect + spec gaps | FIXED, VERIFY |

## F-1. The frozen suite uses names the spec never declares (R3, R4, R5, R6, R9, R11; part of R1, R2)

**Evidence.** Every gate-1 log is a *compile* failure of `tests/kernel/<x>_test.c` against the
agent's headers, naming identifiers: R3 `http_conn_t.status`, `FS_PATH_MAX`, `FS_HEADER_MAX`;
R4 `kv_reset`, `kv_count`, `kv_log_t`, `KV_SHUTDOWN`, `KV_MAX_VALUE`; R5 `smtp_store_t`,
`smtp_reset`, `smtp_scan_highest`, `smtp_next_seq`, `SMTP_MAX_LINE`, `SMTP_MAX_RCPT`; R6 `hr_conn_t`,
`HR_PATH_MAX`, `.text`; R9 `fdt_bootargs`, `fdt_memory`, `fdt_find_compatible`; R11 `fh_event_t`,
`FH_HALTED`, `FH_RESUMED`, `fh_reset`, `fh_on_fault`. `grep` of each spec finds none of them; each
is in `tests/kernel/<x>_reference/include/<x>.h`. R8, the only pass, was the only run seeded with
its interface header.

**Cause.** The suite was frozen against the reference implementation's header. The spec says "see
the interface" in prose but the identifiers are in a file the session never receives. The agent
cannot guess `KV_SHUTDOWN`.

**Change (done).** `docs/campaign/runs.yaml` seeds `tests/kernel/<x>_reference/include` into each
run's workspace and each goal names it as the frozen interface. **Test:** the second campaign's
gate 1 passes the compile step. **Falsified if** the same identifier error returns.

**Still to do (code).** A static check, so this cannot recur silently: for every frozen suite,
extract the identifiers it takes from headers and assert each appears in either its spec or the
seeded header. Add as `agent/tests/unit/test_suite_interfaces_declared.py`. Without it a new
suite can ship with the same hole.

## F-2. Portable code written with x86 inline assembly (R1)

**Evidence.** `kernel/mm/pmm.c:32: unrecognized instruction mnemonic` for `cli; hlt`; the host
suite compiles the allocator with the Mac's clang (arm64).

**Cause.** `mm.md` said "panics" and not how. The HAL's `arch_halt()` is the portable halt (the
suite's `mm_host_env.c` provides a version that aborts, which is how a panic is observed).

**Change (done).** `mm.md` edge cases: panic halts through `arch_halt()`, never inline assembly.
**VERIFY** on the R1 re-run. **Wider concern (OPEN):** every generated service has the same
exposure to any arch-specific inline asm in portable files. Add a gate step that greps
`kernel/{mm,fs,net,services}/**` for `__asm__`/`asm(` and reports the file and line, so the
failure message is "inline assembly in portable code" and not a clang error.

## F-2b. R1 re-run: the host environment lacked `boot_get_info` (found 2026-10-11)

**Evidence.** After F-1/F-2 the re-run's `pmm.c` compiled but did not link: `_boot_get_info`,
`_boot_module_reserved_range` undefined. Both exist in kernel-base-v5 (`boot_mm.c`) and the
generated allocator used them, reasonably, to find the boot modules the spec says it must not
hand out. `mm_host_env.c` provided `kprintf`, `kmem*`, `kstr*` but not these.

**Cause.** Same class as the `tftp_stub` gate defect: the suite required what lies outside the
scope it verifies. It also **blinded the swarm**: its reviewers call `run_gate`, saw a link error
every time, and could not see behaviour.

**Change (done).** Weak stubs (no modules) in `mm_host_env.c`; self-test, 9/9 injected bugs still
pass. With the link fixed, the archived tree shows two genuine behavioural bugs and nothing else:
`kmalloc(0)` returns non-NULL, and `vmm_get_physical` on a 2 MiB mapping adds a 4 KiB offset
(`virt & 0xFFF`) instead of `virt & (2 MiB - 1)`. **R1 is re-run** (pre-registered change: the
swarm can now see behaviour through `run_gate`).

## F-2c. R1 re-run result and two more host-environment holes (2026-10-12)

The re-run took 25 h of sessions (three on Claude until its limit, two on the local 27b) and
ended gates [1, -6, 0]. Reading its tree with the gates exposed two more things that were the
harness, not the model, both **FIXED**:

* `hal.h` has ARCH_* constants only under `#if defined(__x86_64__)`, so on this arm64 Mac a
  portable file that includes `hal.h` (as mm.md now directs, for `arch_halt`/`arch_panic`) hits
  `#error`. New `tests/kernel/host_arch_defs.sh` supplies the x86_64 constants to both suites.
* The tree called `arch_panic` and the env had only `arch_halt`. Weak `arch_panic`,
  `arch_{en,dis}able_interrupts`, `arch_{save,restore}_irq_state`, `arch_flush_tlb` added.

With those, the final tree's **behavioural** failures are real model bugs: the allocator does not
hand out exactly its free count nor report empty when drained; the VMM does not adopt the boot
map, allocates one table where three are needed, does not free a table after a failed
intermediate allocation, and cannot protect inside or split a 2 MiB page. Self-test and 9/9
injected bugs still pass. **R1 is therefore a model-capability result at last**, not a harness
one: the swarm needed to see these (it now can) and did not get the chance on this run, since the
gates only became honest at its end. A further R1 attempt is a pre-registered change worth
making once the rest of the ladder has run on today's gates.

## F-3. FAT32 linked against kernel symbols (R2)

**Evidence.** Link error: `_vfs_register_fs`, `_vfs_dentry_alloc`, `_kprintf`, `_kmemset`
referenced from `fat32_init` etc. The boot acceptance gate (`run-storage-acceptance.sh`) passed:
the driver and filesystem worked in the real kernel.

**Cause.** The host suite links `fat32.c` + `fat32_write.c` alone. The agent put VFS registration
and logging inside the file. `fs.md` said "calls nothing else below" but not "calls nothing
else".

**Change (done).** `fs.md` gains a *Link contract (REQUIRED)*; R2's goal repeats it and names
`fat32_vfs.c` for registration. **VERIFY.** Note the advisory VirtIO-block suite also failed with
host-clang x86 asm (`inl` in `io.h`): that suite compiles driver code that includes the x86 port
I/O header on an arm64 host. **OPEN:** decide whether driver suites should build with an x86
target or stub port I/O (`io.h` host shim); until then it stays advisory.

## F-4. The engine's git handling crashed runs (R3, R6, R10, R11, R12; one R1 re-run)

Four distinct defects, all in `agent/orchestrator/comms/git_workspace.py`. **All FIXED**, with
tests in `agent/tests/unit/comms/test_merge_branch.py`.

1. **`git add -A -- . :(exclude).auton :(exclude)build` exits 1** when `build` is in `.gitignore`
   ("paths are ignored"). R3 died at iteration 0 on its first commit. Fix: no pathspec names
   engine paths; `init` writes `.auton/` and `build/` to `.git/info/exclude`; anything already
   tracked is unstaged with `git rm --cached --ignore-unmatch`.
2. **`commit()` used a bare `git add -A`**, so `.auton/tasks/<id>.json` was committed on agent
   branches. The next `git checkout main` then failed ("local changes would be overwritten").
   R6, R10, R11, R12 and the R1 re-run all died on this. Fix: `commit()` uses the same staging;
   `_checkout_discarding_engine_state` restores `.auton/` files git names and retries.
3. **Untracked files block a merge or checkout**: `merge --abort` then raised because no merge had
   begun (R10). Fix: remove the named untracked debris and retry once; abort tolerates "no merge".
4. **A gate wrote its log into the tree**: `scripts/boot-marker.sh` wrote
   `$TREE/.boot-marker-build.log`; the next checkout was refused (R10 attempt 1). Fix: the log
   lives in `$TMPDIR`.

**OPEN:** the engine caught none of these, and it reported each as "Orchestration failed" with
iteration 0 or the last iteration. A crash in workspace plumbing should be retried or
checkpointed, not end the run. Add: wrap the per-task git operations, on `GitCommandError`
save state and return `paused` (resumable) rather than `error`.

## F-5. The local fallback model's calls exceed 1800 s (R5, R7)

**Evidence.** `litellm.Timeout ... Timeout passed=1800.0, time taken=1800.09` ended `smtp-004` and
`ssh-002`; the remaining tasks stayed pending and the run produced nothing.

**Cause (likely, not proven).** When Claude's limit is reached the client falls back to
`qwen3.5:27b-coding-mxfp8` at a 32k context; `max_tokens` is 16384. At the 27b's generation
speed on this machine a long answer alone can exceed 30 minutes; prefill of a 32k prompt adds
more.

**Change (done).** Fallback calls get 3600 s (`FALLBACK_REQUEST_TIMEOUT`). **OPEN, measure:**
tokens/s and prefill time of the 27b at 32k context on this machine, from `ollama` timings, so
`max_tokens` for the fallback is chosen from a number. Also: a timed-out task is failed
outright; it should be retried once, since the model may have been mid-answer.

## F-6. R7 had no crypto sources (attempt 1)

**Cause.** The goal requires Monocypher and BearSSL "vendored unmodified" and the session had no
copy; the reviewer rejected a header-only change three times. **FIXED:** sources staged by
`tests/crypto/fetch_sources.sh`, judged by `run_crypto_gate.sh`, seeded as `third_party/…`.

## F-7. R12 (Doom): the image gate and the spec

1. **Gate defect (FIXED).** `make -C "$KERNEL_TREE" iso` ran with no `grub-mkrescue` (exit 127);
   the gate now sources `scripts/lib/toolchain.sh`.
2. **Spec gaps (FIXED):** `DG_GetKey` belongs in `platform_pure.c` (the frozen suite links it
   there); the engine's libc needs are 49 names, measured (`reference/doom-surface.yaml`), so the
   spec requires `libc_min.c`.
3. **VERIFY, and expected to be hard:** `libc_min.c` includes `sscanf`, `snprintf` family and a
   `malloc` over the kernel allocator; the engine's `Z_Init` wants one large contiguous block
   (`pmm_alloc_contiguous` must serve megabytes). If R1's allocator is the empty tree the run
   starts from, R12 cannot work: it depends on R1 (below).

## F-8. The engine's own "composition check failed" (every run) — FIXED

**Evidence.** Sessions ended "Orchestration failed: composition check failed" with every task
merged. Running `CompositionValidator` by hand on an archived R9 tree: the build passed, the unit
tests passed, and the integration step reported *"Kernel image not found:
…/build/kernel-integration.bin"* as a **critical Frankenstein effect**.

**Cause.** Nothing in the repository builds `build/kernel-integration.bin` (`git grep` finds only
the validator naming it). The check could never pass, so it failed every run's engine verdict
whatever the code was. It was not what decided a run (the gates do), but it was the first thing a
reader saw and it pointed away from the real causes.

**Change (done).** No integration image means "integration tests not run", with the reason in
the summary, not a failure; test in `test_composition_validator.py`. **OPEN:** decide whether an
integration image should exist (a kernel built with the test harness) or the step be removed.

## F-9. Dependencies make one failure cascade

R2–R7, R10–R12 start from `run:r1-mm`'s tree (its fallback is the last session's tree, which
had no allocator source in the re-run). A failed R1 poisons everything after it. **Plan:** R1 is
the critical path. Fix order: R1 → R2 → R3/R4/R5/R6/R7 → R10/R11/R12, and re-run a dependant only
when its base run's gates are green. The campaign already does the former; it should *not*
start dependants on a base whose main has no source for what they extend (a "base has the
files" precondition in `base_for`).

## F-10. Host memory guard pauses (R7, R11, R12, R9)

Sessions of 3–16 hours show `memory_paused`. Probable causes: the local 27b resident (~30 GB)
plus Docker/Rancher VMs plus my own test runs. **Change:** none yet. **OPEN:** record free
memory with each guard firing; run no Docker work alongside a campaign.

## F-12. A timeout on `make run` hung the orchestrator for good (R1, local-model attempt 1) — FIXED

**Evidence.** 2026-10-19, 11 minutes with no model call; `ps` showed `qemu-system-x86_64 -cdrom
build/auton.iso -serial stdio` at 100% CPU with PPID 1, and the orchestrator idle. The developer had called
`build_kernel(target=run)`: `make run` starts QEMU in the foreground and never returns.

**Cause.** `core/proc.py: communicate()` killed `make` on the timeout, then awaited `proc.wait()`. asyncio
wakes `wait()` only after the child's pipes close, and QEMU, a grandchild, still held them. The wait never
returned, so the run stopped making progress without an error. The earlier 27b-era campaigns would have had
the same hole whenever an agent ran a foreground target; it was never seen because the agents rarely did.

**Change (done).** Children start with `start_new_session=True` (four sites); `communicate()` kills the whole
process group, and bounds the reap at 10 s. **Test:** `test_proc_grandchild.py` starts `sh -c "sleep 60 & wait"`,
times out at 1 s and requires the call to return in under 8 s with nothing left running; against the old code
it hangs. **Falsified if** a run again sits idle with an orphaned QEMU. The run was resumed from its saved
state (`run --resume`): branches and commits intact, the first session's console transcript overwritten.

## F-13. Attempt 2 of R1 died on the engine's own header check and the reviewer's use of `run_gate` (local-model campaign) — FIXED

**Evidence.** `r1-mm-attempt2` ended after 3 iterations and 43 minutes: `mm-001` (the headers) was rejected three
times and its 12 dependants never started. Rounds 1 and 2: "change fails its mechanical checks ... `kernel/include/mm.h:7:10:
fatal error: boot.h: No such file or directory`". Round 3: "the implementation files are missing. The test suites require
actual implementations". Gates then read exit 2, 2, 0 and the campaign began R2 on the bare base.

**Cause (two harness defects).** (1) `syntax_gate.py` compiled a header against the tree's own include directories only;
`mm.md` has `mm.h` include `boot.h`, which belongs to a subsystem an mm goal does not produce. The host suites already
substitute the seeded reference (`BOOT_INCLUDE` in `run_mm_test.sh`); the engine's gate did not: the "gate demands what it
does not gate" class again. (2) The reviewer was told to run `run_gate` "before approving", and `run_gate` reports the finished
run's suites; on a headers-only first task they are exit 2 by construction, and the model treated that as a reason to reject.

**Change (done).** `syntax_gate.fallback_dirs`: seeded `tests/kernel/*_reference/include` are searched last (`-idirafter`), so
the tree's own header always wins (`test_syntax_gate_fallback.py`: found, still fails when unseeded, the tree's header wins).
The review prompt gains "Reading run_gate on one task": exit 2 for parts other tasks produce is expected; reject on a gate result
only when this change causes it. **Not counted as an attempt** (the pre-registration's own rule for a harness defect); the
directory is `.artifacts/campaign-invalid-2026-10-20/r1-mm-attempt2-harness-defects/`. Attempt 1 stays counted: its rejections were
implementation faults (missing `PAGE_SIZE`, `pmm_free_page`), and it ran under the old reviewer text. The aborted
`r2-storage-attempt1` (it started on a bare base after R1 "failed") is archived beside it.

**Open.** `campaign.py` starts a dependant on the dependency's own base when the dependency fails with `fallback: none`; for R2 that
is a base with no allocator, which its goal says exists. The pre-registration says a dependant runs only on a green base. Until
this is decided (a labelled human R1, or skipping the dependants), a failed R1 will start R2 on nothing.

## F-11. What no run has yet tested

Behaviour. No run got past the compile step of its frozen suite except R6 (clone over dumb-HTTP
passed) and R2 (storage acceptance end to end). The suites' *behavioural* checks, and the
injected-bug scores on references, are the next layer of risk; expect new failures there and
treat each as a finding, not a surprise.

## Execution order

1. (done) git plumbing, gate defects, fallback timeout, interface seeding, specs.
2. Re-run the campaign (R8 stays passed) with the pre-registration
   `w23-campaign-rerun-preregistration.md`.
3. Per run that still fails: read its gate log first, then fill the matching section above.
4. Write F-1's static check and F-2's inline-assembly gate message; investigate F-8.
