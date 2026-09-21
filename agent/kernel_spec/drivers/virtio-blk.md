---
driver: virtio-blk
devices: ["virtio-mmio:2", "1af4:1042", "1af4:1001"]
provides: [fs]
strategy: synthesize
specification: "VIRTIO 1.2 §5.2 — Block Device"
verification:
  - "marker: [BLK] virtio-blk up"
  - "marker: [BLK] capacity 1048576 sectors"
  - "cmd: tests/kernel/run_virtio_blk_test.sh"
status: specified
---

# virtio-blk

The storage unlock. Factory phase 7 — *"block driver + minimal FS"* — and with it F8–F11, the
whole service ladder, waits on this and nothing else.

V9's join reported the gap without being asked: a Firecracker target has `virtio-mmio:2`,
`device_drivers` resolves it to `virtio-blk`, and until now no record described what would drive
it.

## Why this cost less than virtio-net

Deliberately measured — V5 exists as this phase's control. The virtqueue arithmetic is shared:
the descriptor chains, the available/used ring indices and their wrap are specified once under
*VirtIO Network* and proved once in `tests/kernel/virtio_reference/`, which was renamed from
`virtio_net_reference/` when this became its second consumer. A shared component named after one
of its consumers is how the second one ends up with a copy.

What is block-specific is small and is all this record adds: one queue instead of two, a request
type, and a three-descriptor chain whose flags are not uniform.

## The three-descriptor chain

| # | Contents | Device-writable |
|---|---|---|
| 0 | `virtio_blk_req_t` header | no |
| 1 | data buffer | only on `VIRTIO_BLK_T_IN` |
| 2 | status byte | always |

A chain built with one flag value is wrong in both directions. Uniformly writable lets the device
overwrite the header it is meant to read — a memory-corruption primitive. Uniformly read-only
leaves it nowhere to report status, so every request appears to succeed — silent data loss.

A flush has no data buffer and is a **two**-descriptor chain, which is what a driver assuming
three will corrupt.

## Verification

Two markers and a command. `tests/kernel/run_virtio_blk_test.sh` exists and exits 2 against a tree
with no generated driver — *nothing to check*, which V9 reports as unverified rather than passed.
It does not retest the rings; those are covered by the network suite against the same reference.
