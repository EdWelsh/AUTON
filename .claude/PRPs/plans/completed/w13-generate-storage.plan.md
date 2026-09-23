# Plan: Storage Unlock, Part 2: Generate virtio-blk + FAT32, Host-Verified Disk (F7)

## Summary
Part 1 (`w12-factory-storage-fat32-spec`) specifies FAT32 against an mtools oracle. V6 specified
virtio-blk. This plan generates both into `kernel-base-v5` under the Generation Experiment
Protocol and meets the PRD's success signal literally: **the kernel writes a file that the host
then reads back** from the disk image with `mtype`. Promoting both to `status: implemented`
waits on V9's gate observing a pass.

## User Story
As the service ladder (F8 file server, F9 KV, F11 email), I want a booted image that reads and
writes a host-inspectable disk, so that every storage-dependent service has somewhere real to
keep data.

## Problem → Solution
No block driver or filesystem in any tree → generated `virtio_blk.c` + `fat32.c`, host suites
passing in tree mode, a QEMU boot with `-drive if=virtio` writing `/AUTON.TXT`, and
`mtype -i disk.img ::AUTON.TXT` matching.

## Metadata
- **Complexity**: Large
- **Source PRD**: `auton-service-kernel-factory.prd.md` phase 7; `auton-driver-development.prd.md` V6 (implementation)
- **Estimated Files**: 6 generated + test harness + report
- **Depends on**: `w12-loop-review-repair`, `w12-kernel-base`, `w12-factory-storage-fat32-spec`, `w13-generate-mm` (DMA-safe pages for the virtqueue)

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `w13-factory-f6-rerun.plan.md` | "Generation Experiment Protocol" | protocol |
| P0 | `agent/kernel_spec/subsystems/drivers.md` | 163-300, 706-730 | virtio-blk + the `blk_*` interface |
| P0 | `agent/kernel_spec/drivers/virtio-blk.md` | all | markers `[BLK] virtio-blk up`, `[BLK] capacity 1048576 sectors` (a 512 MiB disk) |
| P0 | `tests/kernel/run_virtio_blk_test.sh`, `run_fat32_test.sh` | tree mode | the gates |
| P1 | `agent/tools/driver_verify.py` | gate | how `status: implemented` becomes admissible |
| P1 | `scripts/run-acceptance.sh` | 45-70 | the pattern for a boot with an extra QEMU device |

## Patterns to Mirror
### QEMU_EXTRA_DEVICE
// SOURCE: scripts/run-acceptance.sh:48-60: a second boot with an extra device, bounded by `auton_timeout`, markers grepped from serial.
### RECORD_PROMOTION
// SOURCE: agent/kernel_spec/drivers/README.md rule 4: `implemented` needs a mapping and an observed pass.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `<ws>/kernel/drivers/blk/virtio_blk.c`, `kernel/include/blk.h` | GENERATED | driver + interface |
| `<ws>/kernel/fs/vfs.c`, `kernel/fs/fat32.c`, `kernel/include/fs.h` | GENERATED | minimal VFS + FAT32 per `fs.md` |
| `<ws>/kernel/boot/kernel_main.c` | GENERATED (edit) | mount the first block device; write and read `/AUTON.TXT`; markers |
| `scripts/run-storage-acceptance.sh` | CREATE (human) | `mformat` 512 MiB image → boot with `-drive file=disk.img,if=virtio,format=raw` → markers → `mtype` check |
| `agent/kernel_spec/drivers/virtio-blk.md` | UPDATE | `provides: [fs]` → `provides: [virtio-blk]` (a block driver does not provide a filesystem; check `device_drivers.DRIVER_CAPS` agrees) |
| `agent/kernel_spec/source_map.yaml` | UPDATE, after gates | `virtio-blk`, `vfs`, `fat32` → generated paths, per-tree note |
| report + pre-registration | CREATE | protocol |

## NOT Building
- ATA PIO (the PRD allowed either; virtio-blk is specified and host-proved already).
- Directories beyond the root, a page cache, async I/O.
- Any service (F8/F9 consume this).

## Step-by-Step Tasks

### Task 1: The acceptance script (human, before the run)
- **IMPLEMENT**: `run-storage-acceptance.sh <tree>`: build the ISO; `mformat -F -C -T 1048576 -i disk.img` (512 MiB = 1048576 sectors, which is what the marker asserts); `mcopy` a seed file `SEED.TXT`; boot for ≤60 s; assert `[BLK] virtio-blk up`, `[BLK] capacity 1048576 sectors`, `[FS] mounted fat32`, `[FS] read SEED.TXT <n> bytes`, `[FS] wrote AUTON.TXT`; then `mtype -i disk.img ::AUTON.TXT` equals the expected content.
- **GOTCHA**: QEMU caches writes. The guest must flush and the script must wait for QEMU to exit (`-no-reboot`, guest halts after writing) before running `mtype`. Killing QEMU mid-write reads a stale image.
- **VALIDATE**: against the base (no driver), it exits 2 naming the missing marker.

### Task 2: Spec addendum
- **ACTION**: Add the `[FS]` markers above to `fs.md`'s FAT32 section, before pre-registration.

### Task 3: Pre-register, run once, archive (protocol 1-4)
- **GOAL TEXT**: names `read_spec drivers`, `read_spec fs`, the files above, and the markers.

### Task 4: Gates (protocol 5)
- **ORDER**: `run_virtio_blk_test.sh` (tree mode) → `run_fat32_test.sh` (tree mode, mtools oracle) → `run-storage-acceptance.sh <ws>`.

### Task 5: Injected bugs (protocol 6)
- **SET**: V6's 5 chain bugs plus Part 1's 5 FAT bugs, on the generated files.

### Task 6: Promote, measure, report (protocol 7-8)
- **ACTION**: `driver_verify.py` observes the pass, then `virtio-blk.md` → `status: implemented` for the generated tree. Update factory PRD row 7 and driver PRD V6.

## Validation Commands
```bash
KERNEL_TREE=<ws> tests/kernel/run_virtio_blk_test.sh
KERNEL_TREE=<ws> tests/kernel/run_fat32_test.sh
scripts/run-storage-acceptance.sh <ws>
.venv/bin/python agent/tools/driver_spec.py --validate agent/kernel_spec/drivers/virtio-blk.md
```

## Acceptance Criteria
- [ ] The host reads, with mtools, a file the booted kernel wrote
- [ ] Both host suites pass in tree mode
- [ ] Injected-bug ratios beside V6's 5/5 and Part 1's
- [ ] `virtio-blk` promoted only on an observed pass

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The loop produces the driver but not FAT32 (or vice versa) | H | M | gates are per component; the report says which. The fallback is human-written, labelled, as in `w13-generate-mm` |
| Write caching makes the host check flaky | M | M | Task 1's gotcha: guest flush plus a halt, then wait for QEMU |
