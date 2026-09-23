# Implementation Report: Storage Unlock, Part 1: FAT32 Spec with a Host Oracle (F7)

**Plan**: `plans/completed/w12-factory-storage-fat32-spec.plan.md`

## Summary

FAT32 is specified in `fs.md` (13 REQUIRED rules, each mapped to the test that checks it) and
proved by a reference that is itself proved against **mtools**. mtools builds the volumes, the
reference reads and writes them, and mtools reads back every file written. `fsck.fat -n`
(dosfstools) is a second structural check. 34 C checks, 5 oracle read-backs and fsck all pass
under ASan/UBSan. Five injected bugs are each caught.

## What the tests found in the reference

**A looping chain returned wrong data with success.** The reference bounded chain walks by
cluster count, which stops a hang. A loop inside a file's first N clusters instead yields N
clusters of the wrong data and a success code. Reads now validate the chain first with Brent's
cycle detection (constant memory): exactly ⌈size/cluster⌉ clusters, no loop. This is now a
REQUIRED rule.

## What the injected bugs found in the tests

The first injection run caught 3 of 5:

| Bug | First run | Why | Fix |
|---|---|---|---|
| FAT entry not masked to 28 bits | not caught | mtools always writes the reserved bits as zero, so masking never matters on its volumes, and the check "entry ≤ 0x0FFFFFFF" passed for the wrong reason | a new test sets the reserved bits in a live chain; the vacuous check was removed |
| FSInfo next-free trusted | reported "not caught" | **my injection did not compile**, and my harness counted zero FAIL lines as zero failures | the injection was fixed; the injection runner now reports a compile failure as such |

Final: 5/5 caught (unmasked 1 check; single FAT 2, including fsck; FSInfo trusted 3, including
the mtools read-back of SEED.TXT; LFN checksum 2; cluster→LBA off by one 19).

## Tasks

| # | Task | Result |
|---|---|---|
| 1 | Oracle harness | `tests/kernel/run_fat32_test.sh`: 64 MiB FAT32 (1 sector/cluster), a FAT16 control, a scratch copy for corruption; SKIPs naming mtools when absent |
| 2 | Spec | `fs.md` "FAT32": the split, the interface (`fat32.h` normative), 13 rules with fatgen103 sections and tests, markers for Part 2 |
| 3-4 | Tests + reference | `fat32_test.c`; `fat32_reference/fat32.c` (read) + `fat32_write.c` (write), freestanding-shaped, write-through |
| 5 | Injected bugs | 5/5 (above) |
| 6 | Capability + CI | `fat32` in `fs.md` front-matter, optional; `writable` is the write half; slice tests; CI installs mtools + dosfstools on both hosts |

`fatgen103` is inventoried in `vendors.yaml` (Microsoft, `standards`, not redistributable).
`fat32` stays unmapped in `source_map.yaml` until a tree implements it (w13).
