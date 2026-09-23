# Implementation Report: virtio-blk (V6)

## Summary

V9's join reported the gap without being asked — a Firecracker target has `virtio-mmio:2`,
`device_drivers` resolves it to `virtio-blk`, and nothing described what would drive it. Factory
phase 7, the storage unlock, and F8–F11 behind it were waiting on this.

**V5 was the control, and the reuse was real:**

| | V5 virtio-net | V6 virtio-blk | ratio |
|---|---|---|---|
| Specification lines | 113 | 84 | 0.74 |
| New shared-reference C | 135 | **24** | **0.18** |
| Host test lines | 160 | 136 | 0.85 |
| Host checks | 29 | 16 | 0.55 |

The reference line count is the one that matters: the virtqueue arithmetic was written once and
proved once. The 24 new lines are a per-descriptor-flag variant that the block chain forced —
see below.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Complete the specification | Complete | MMIO transport, request protocol, markers |
| 2 | Reuse the ring reference rather than copying it | Complete | renamed; **zero** ring arithmetic in the block test |
| 3 | The record and its verification | Complete | three device ids, two transports |
| 4 | Advertise it honestly | Complete | phantom mapping **removed** |
| 5 | Measure against V5 | Complete | above |

## What the second consumer found in the first one's work

The shared reference exposed `vnr_add_chain(..., int device_writable)` — **one flag for the whole
chain**. That is correct for a network driver, where every buffer in a chain runs the same
direction. A block request does not:

| # | Contents | Device-writable |
|---|---|---|
| 0 | `virtio_blk_req_t` header | no |
| 1 | data buffer | only on `VIRTIO_BLK_T_IN` |
| 2 | status byte | always |

My first attempt stitched three uniform-flag chains together in the test and unwound the publish
counter after each — a ring operation performed in a test rather than in the thing that owns the
ring. That is the shape of a duplicated abstraction even though no code was literally copied.

`vnr_add_chain_mixed()` now takes a per-descriptor flag array, and the uniform form calls it. The
block test does one call and contains **zero** ring arithmetic (`grep -c` for `vnr_ring_slot`,
`avail_idx`, `free_head`: 0). The network suite is unchanged and still passes.

A shared component whose API assumes its first consumer's shape is how the second one ends up
with a copy. So is a directory named after the first consumer — `virtio_net_reference/` is now
`virtio_reference/`.

## The bug this specification exists to prevent

A chain built with one flag value is wrong in **both** directions, and the two failures look
nothing alike:

- **Uniformly writable** — the device may overwrite the request header it is meant to read. A
  memory-corruption primitive.
- **Uniformly read-only** — the device has nowhere to report status, so every request appears to
  succeed. Silent data loss.

And a flush has no data buffer, making it a **two**-descriptor chain. A driver that assumes three
corrupts it.

Five bugs injected, five caught:

| Injected | Failures |
|---|---|
| uniform flags, everything writable | 3 |
| uniform flags, nothing writable | 4 |
| a write's data buffer marked writable | 1 |
| a flush builds three descriptors anyway | 2 |
| the per-descriptor flag ignored in the shared reference | 5 |

## Task 1: the section was PCI-only

`drivers.md`'s VirtIO Block section predates both driver phases and specified only the legacy PCI
register block. Firecracker's disk is `virtio-mmio:2` and has no PCI bus — the same gap V5 found
in the network case, in a section written before either. The MMIO register map, status-bit order
and feature-negotiation discipline are specified once under *VirtIO Network* and referenced, not
restated.

## Task 4: the phantom mapping, removed

`virtio-blk: [kernel/drivers/blk/**]` pointed at a directory that has never existed. V1a made that
detectable; this removed it. The refusal is now the honest one:

```
    virtio-blk  — (drivers) Red Hat, Inc. Virtio block device (1af4:1001)   no source mapping
```

rather than a message about a glob. Five phantom-mapping tests had pinned themselves to
`virtio-blk` as the example and broke when it was fixed — they now use `framebuffer`, the
remaining real instance, with a new test asserting `virtio-blk` is no longer in the map at all.

Two V9 tests also broke because the gap they documented is closed: Firecracker no longer has an
undeclared driver, and now carries two specified ones.

## Validation

1415 unit tests pass, 111 SLM tests, 16 block host checks + 29 network host checks under
ASan/UBSan. Five injected chain bugs, all caught.

```
$ driver_verify.py --target agent/kernel_spec/targets/firecracker.md
  virtio-net   synthesize  specified  unverified
  virtio-blk   synthesize  specified  unverified
      unverified  cmd: tests/kernel/run_virtio_blk_test.sh — exit 2, nothing to check
```

## Files

| File | Action |
|---|---|
| `agent/kernel_spec/subsystems/drivers.md` | UPDATED — VirtIO Block completed |
| `agent/kernel_spec/drivers/virtio-blk.md` | CREATED |
| `tests/kernel/virtio_reference/` | RENAMED from `virtio_net_reference/`; `vnr_add_chain_mixed` |
| `tests/kernel/virtio_blk_test.c` | CREATED — 16 checks |
| `tests/kernel/run_virtio_blk_test.sh` | CREATED |
| `agent/kernel_spec/source_map.yaml` | UPDATED — phantom entry removed |
| `agent/tests/unit/test_phantom_mappings.py` | UPDATED — example moved to `framebuffer` |
| `agent/tests/unit/test_driver_verify.py` | UPDATED — the gap it documented is closed |

## Acceptance

- [x] The VirtIO Block section covers both transports and the three-descriptor request chain
- [x] Nothing restated from VirtIO Network or from the ring layout above it
- [x] The ring reference is shared, renamed, and not duplicated — zero ring arithmetic in the block test
- [x] `virtio-blk.md` validates at `status: specified` with three device ids
- [x] No `source_map` entry; `gate_capabilities` refuses as unmapped
- [x] V9's join no longer reports `virtio-blk` as undeclared
- [x] Cost recorded beside V5's
