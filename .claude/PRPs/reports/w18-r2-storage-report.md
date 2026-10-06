# w18 R2: storage (VirtIO block + FAT32). Result: generated wrong, with storage working end to end

**Model:** Claude Sonnet 5.5 through the owner's subscription. **Base:** `kernel-base-v5`, because
R1 did not pass. **Gates (amended 2026-10-05, stop rule 5):**
- `run_fat32_test.sh`, using the normative header when the tree has none;
- `run-storage-acceptance.sh`.

The ring suite `run_virtio_blk_test.sh` is advisory: it judges an API that neither drivers.md nor
the goal names.

## Verdict: both attempts fail (stop rule 3), and the phase fails

| | FAT32 suite | Storage acceptance (boots, mounts, reads, writes, host reads back) | Ring suite (advisory) | Tasks | Work / waiting on limits |
|---|---|---|---|---|---|
| Attempt 1 | **1** | **2** | 1 | 5 of 9 merged | 1.8 h / 30 h |
| Attempt 2 | **1** | **0 (PASS)** | 1 | **10 of 10** merged | 2.2 h / 13 h |

**Attempt 2 built working storage.** On QEMU's VirtIO disk, the kernel mounts FAT32, reads
`/SEED.TXT`, creates `/AUTON.TXT`, and the host reads back "written by AUTON" with `fsck.fat`
clean. It fails the FAT32 suite on interface conformance, not on behaviour:
- fs.md makes `fat32_reference/include/fat32.h` normative. The tree has no `fat32_create` or
  `fat32_append`; its own write API is `fat32_create_root`.
- It calls `blk_flush`, which drivers.md's block interface (`blk_read`, `blk_write`,
  `blk_get_info`) doesn't have. fs.md says FAT32 "calls nothing else below it".

**Attempt 1 failed differently:**
- `blk_read`/`blk_write` drop drivers.md's `dev_id` argument.
- `fs-004` (the write half) was rejected by the reviewer three times, which blocked the boot
  wiring behind it, so nothing printed `[FS]`.

## Harness and gate defects found on R2, all fixed

- **The host slept mid-call** ("Your computer went to sleep mid-response") and failed `fs-004`.
  Transient API errors are now retried (`615d30a`), and the task was requeued; it then failed on
  review, which is a real result.
- **Usage-limit waits counted against the budget.** Budgets now count work only (`e301754`).
- **The ring suite needs a `vnr_*` API the spec never names.** It is advisory for R2
  (`d062116`); w23 G6 covers naming it in drivers.md.
- **The FAT32 suite required a `fat32.h` in the tree** that the spec never places there. The
  normative header now stands in (`d062116`).

## Scope

Both attempts added headers well outside storage: `ahci.h`, `display.h`, `drivers.h`, `fb.h`,
`e1000.h`, and in attempt 1 `boot.h`/`boot_entry.h`. These came from the architect's design phase,
which designs every subsystem the specs touch, not just the goal's. Lines: attempt 1 +3,493,
attempt 2 +4,699.

## Reading

When R2 gets the time, its storage works. Both attempts fail on the same thing as R1: keeping to
the normative interface. That covers argument lists, function names, and what may be called
below the layer. The reviewer approves code that works and doesn't check it against the frozen
header, which is w23 G4 again. The fix is to make the swarm's tester run the frozen suites, not
to loosen the gates.
