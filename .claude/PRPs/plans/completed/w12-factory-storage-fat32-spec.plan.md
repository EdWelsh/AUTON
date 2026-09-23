# Plan: Storage Unlock, Part 1: FAT32 Spec with a Host Oracle (F7)

## Summary
F7 is the single unlock behind three service rows (file server, KV database, email). The PRD
chose FAT32 behind a small VFS interface so an image can be inspected from the host
(`auton-service-kernel-factory.prd.md:359-365, 423`). `fs.md` specifies ext2 and initramfs, not
FAT32. This plan writes FAT32 into the spec with REQUIRED sections and proves a host reference
against an **independent oracle**: mtools reads what the reference wrote, and the reference
reads what mtools wrote. Generating it into a tree and booting against a disk is Part 2
(`w13-generate-storage`).

## User Story
As the loop generating a storage-capable image, I want a FAT32 spec whose every rule has a test
checked against a real FAT implementation, so that a generated filesystem is proved
interoperable, not merely self-consistent.

## Problem → Solution
`fs.md` has ext2 and no FAT; no block-backed filesystem has ever been tested → `fat32`
capability in `fs.md` (REQUIRED: BPB validation, FAT chain walk, 8.3 + LFN read, create, write,
extend, free-cluster search, FSInfo hint as advisory, dirty-shutdown flag), host reference over a
file-backed block device, and a round-trip test against mtools in both directions.

## Metadata
- **Complexity**: Large
- **Source PRD**: `auton-service-kernel-factory.prd.md`
- **PRD Phase**: 7, Storage unlock (spec half)
- **Estimated Files**: 9

---

## UX Design
```
Before:  "be a file server" → roles.c: CAP_ROADMAP "needs a filesystem"
After (this plan):  tests/kernel/run_fat32_test.sh --self-test
   PASS  reference reads a volume mformat created
   PASS  mtools reads a file the reference wrote (mtype matches byte-for-byte)
   PASS  a file spanning a fragmented chain reads back intact
   ...
After (Part 2): a booted image writes /HELLO.TXT; the host runs `mtype -i disk.img ::HELLO.TXT`
```

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/prds/auton-service-kernel-factory.prd.md` | 359-365, 423, 270 | scope, and why FAT32 |
| P0 | `agent/kernel_spec/subsystems/fs.md` | 1-60, 229-280, 412-520 | VFS types; fs registration; the interface FAT32 plugs into |
| P0 | `agent/kernel_spec/subsystems/drivers.md` | 706-730 | `blk_read`/`blk_write`/`blk_get_info`, the only thing FAT32 may call below |
| P0 | `tests/kernel/run_mm_test.sh`, `tests/kernel/mm_test.c` | 1-62, 30-60 | the spec-plus-tests pattern and runner |
| P1 | `agent/kernel_spec/drivers/virtio-blk.md` | all | the block device that will sit under it |
| P1 | `agent/kernel_spec/services/fileserver.md` | 1-40 | first consumer; currently `excludes: [writable]` and reads a CPIO module |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| FAT32 on-disk format | Microsoft "FAT: General Overview of On-Disk Format" v1.03 (2000), the *fatgen103* document | BPB fields; cluster-count thresholds decide FAT12/16/32 (**not** the label); FAT entries are 28 bits, top 4 reserved; EOC ≥ 0x0FFFFFF8 |
| LFN entries | fatgen103 §"FAT Long Directory Entries" | attribute 0x0F; checksum over the 8.3 name; stored in reverse order |
| mtools | gnu.org/software/mtools, 4.0.49 | `mformat -F -i img`, `mcopy -i img src ::DST`, `mtype -i img ::F`; no root, no mount |

KEY_INSIGHT: the FAT type is decided by cluster count, not by the "FAT32" string in the BPB.
APPLIES_TO: Task 2's BPB-validation rule.
GOTCHA: fatgen103 is a Microsoft document. Add it to `agent/hardware/vendors.yaml` as an inventoried
standard with its licence before citing it, as every other normative citation in this repo is. It
is freely downloadable; check redistribution before committing any copy (do not commit it).

---

## Patterns to Mirror

### SPEC_REQUIRED_SECTION
// SOURCE: agent/kernel_spec/subsystems/mm.md:197-243. REQUIRED headings, each a rule table with
the failure symptom.

### HOST_REFERENCE
// SOURCE: tests/kernel/mm_reference/pmm.c + include/: the reference implements the spec's header
exactly, so a generated tree's file compiles against the same test.

### TEST_STRUCTURE
// SOURCE: tests/kernel/mm_test.c:30-38 (`ok(name, cond, detail)`, PASS/FAIL columns, `fails`).

### CAPABILITY_FRONTMATTER
// SOURCE: agent/kernel_spec/subsystems/fs.md:1-7
```yaml
provides: [vfs, initramfs, ext2, devfs, writable]
optional: [ext2, devfs, writable]
```

---

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/subsystems/fs.md` | UPDATE | `fat32` in `provides`/`optional`; a FAT32 section with REQUIRED rules |
| `agent/hardware/vendors.yaml` | UPDATE | inventory fatgen103 (publisher, licence, access) |
| `tests/kernel/fat32_reference/{fat32.c,include/fat32.h,include/blk.h}` | CREATE | reference over a file-backed `blk_*` |
| `tests/kernel/fat32_test.c` | CREATE | a test per REQUIRED rule |
| `tests/kernel/run_fat32_test.sh` | CREATE | `--self-test` / `KERNEL_TREE`; requires mtools, SKIP naming it when absent |
| `agent/tests/unit/test_capability_slice.py` | UPDATE | `fat32` resolves; requires `vfs`, not `ext2` |
| `.github/workflows/portability.yml` | UPDATE | install mtools; run the suite |

## NOT Building
- Generating FAT32 or virtio-blk into a tree (Part 2).
- exFAT, FAT12/16 writing, timestamps beyond "set on create", permissions, journaling.
- Changing `fileserver.md` (F8 does).

---

## Step-by-Step Tasks

### Task 1: The oracle harness first
- **ACTION**: `run_fat32_test.sh` creates `disk.img` (64 MiB) with `mformat -F`, populates it with `mcopy`, runs the test binary against it, then verifies the binary's writes with `mtype`/`mdir`.
- **GOTCHA**: `mformat -F` on a 64 MiB image can produce FAT16-sized cluster counts unless the cluster size is forced (`-c 1`). Assert the volume is really FAT32 by cluster count (≥ 65525) before testing anything.
- **VALIDATE**: with a stub reference, the harness reports FAIL, not a crash, and SKIPs naming `mtools` when it is absent.

### Task 2: Spec, REQUIRED sections in `fs.md`
- **ACTION**: Add *FAT32 (`fat32`)* with:
  - BPB validation: bytes/sector ∈ {512…4096}, type by cluster count, refuse otherwise.
  - Chain walk: mask to 28 bits, EOC ≥ 0x0FFFFFF8, loop/overrun detection (a cycle must not hang).
  - Directory read: 8.3 + LFN assembly with checksum check; deleted (0xE5) and end (0x00) markers.
  - Create/write/extend: first-fit free cluster; FSInfo `free_count`/`next_free` are **hints**, never trusted.
  - Mirrored FATs: every FAT write goes to all `BPB_NumFATs` copies.
  - Dirty flag: cluster 1's clean-shutdown bit set on mount-rw and cleared on unmount.
- **MIRROR**: SPEC_REQUIRED_SECTION, citing fatgen103 by section.
- **VALIDATE**: each rule maps to ≥1 test name (a table at the end of the section).

### Task 3: Tests (RED)
- **IMPLEMENT**: read an mformat volume; read an LFN file mcopy wrote; write a file, then `mtype` matches; extend across a deliberately fragmented chain (create A, B, delete A, write C > A); a corrupt chain with a cycle returns an error within N steps; all FATs identical after a write; FSInfo lying about free space is ignored; a 0-byte file and an exactly-cluster-sized file.
- **VALIDATE**: all FAIL against a stub.

### Task 4: The reference (GREEN)
- **ACTION**: `fat32_reference/fat32.c` implementing `fat32.h` over `blk.h` (file-backed in tests).
- **GOTCHA**: Keep the reference freestanding-shaped: no `malloc` in the read path, caller-supplied sector buffers. A generated kernel version must be able to mirror it without libc.
- **VALIDATE**: `run_fat32_test.sh --self-test` PASS under ASan/UBSan.

### Task 5: Injected bugs
- **ACTION**: Inject: 32-bit FAT entry (no 28-bit mask); only FAT #1 updated; FSInfo trusted; LFN checksum skipped; off-by-one in the cluster→LBA formula.
- **VALIDATE**: every one caught; ratio recorded for the report.

### Task 6: Wire the capability and CI
- **ACTION**: `fat32` in `fs.md` front-matter, optional, depends via `vfs`. Unmapped in `source_map.yaml` (no tree yet). CI installs mtools.
- **REQUIRED SPLIT**: the FAT32 **write** path (create/extend/free-cluster search/FAT mirroring) sits behind the existing `writable` capability, in a separate source file (`fat32_write.c` in the reference). F8's file server `excludes: [writable]` while F9 and F11 require it. A single-file FAT32 would make "read-only file server" unfalsifiable, which is the leakage `excludes` exists to catch.
- **VALIDATE (split)**: the reference's read-only test subset links without `fat32_write.c`.
- **VALIDATE**: `capability_slice` test; workflow parses.

## Testing Strategy
| Test | Input | Expected | Edge? |
|---|---|---|---|
| mformat volume | 64 MiB, `-c 1` | mount OK, type FAT32 by count | |
| LFN read | `mcopy "A long name.txt"` | name and bytes match | yes |
| write → mtype | 3000 bytes | identical | |
| fragmented extend | A/B/delete A/C | C intact per mtype | yes |
| chain cycle | FAT[5]=5 | error, no hang | yes |
| FAT mirror | any write | FAT1 == FAT2 | yes |

## Validation Commands
```bash
brew install mtools   # or apt-get install mtools
tests/kernel/run_fat32_test.sh --self-test
cd agent && ../.venv/bin/python -m pytest tests/unit/test_capability_slice.py -q && ../.venv/bin/python -m pytest -q
```

## Acceptance Criteria
- [ ] `fat32` specified with REQUIRED rules, citing an inventoried document
- [ ] Reference round-trips with mtools in both directions
- [ ] Injected-bug ratio published
- [ ] CI runs it on Linux and macOS

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The reference and the tests share a misunderstanding | M | H | mtools is the oracle, not the reference |
| FAT32 is regretted later | M | M | the PRD's contained-swap design: FAT32 sits behind `fs_type_t` |
| mtools behaves differently across versions | L | M | pin the version in CI; the harness records `mtools --version` |
