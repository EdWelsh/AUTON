# Implementation Report: virtio-net, Human-Authored (V5)

## Summary

`e1000` was the only network driver in the capability index, so the only machines AUTON could
build a network image for were machines with an Intel 82540EM, and a Firecracker target was
refused outright. That is no longer true.

**The headline outcome:**

```
$ intent_manifest.py "hand out addresses" --target targets/firecracker.md
CHOSE: virtio-net for network — virtio-mmio:1 (derived)
requires: [boot, allocator, pci, terminal, scoped, ipv4, udp, virtio-net]
```

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | The specification | Complete | 113 lines, both transports |
| 2 | The host reference | Complete | ring arithmetic, ASan/UBSan clean |
| 3 | The verification command V9 runs | Complete | exits 2 with no tree |
| 4 | Advertise it only once it exists | Complete | `provides` yes, `source_map` **no** |
| 5 | Record the cost | Complete | below |

## The deliverable changed shape, and the plan said so first

F4's control was C code in `kernels/x86_64`, compiled into a 53 KB image. That tree is gone,
deleted deliberately because this project does not write the kernel. So V5 delivers the
specification, a host-testable reference, the capability-index entry, and the verification
command — all real, none of it the tree. Pretending otherwise would have produced code with
nowhere to live.

## Task 4: the trap, avoided on purpose

`source_map.yaml` already maps `framebuffer` to `kernel/drivers/fb/**`, a directory that has never
existed, and a glob matching nothing is not an error. Adding `virtio-net → kernel/drivers/net/
virtio_net.c` before anything generates that file would repeat the defect exactly.

So `virtio-net` went into `drivers.md` `provides` — the capability is genuinely *specified* — and
**no `source_map` entry was added**. The result is that planning works and building refuses:

| Layer | Behaviour |
|---|---|
| `intent_manifest` join | selects `virtio-net` from `virtio-mmio:1` |
| `driver_spec --validate` | passes at `status: specified`, reports `net` unmapped |
| `[gate: capabilities]` | **refuses** — "the image would simply not contain the driver" |

That refusal now names the device, which it never did before: *"virtio-net — (drivers) Red Hat,
Inc. Virtio network device (1af4:1000)"*. V1's report recorded that the friendly-name path could
not fire because no unmapped capability carried a device id. This phase made one.

## What the host tests caught

Six bugs injected into the reference; all six caught. Two only after the tests were strengthened:

| Injected bug | Caught |
|---|---|
| free list wraps to descriptor 0 (double-free of a DMA buffer) | first try |
| receive buffers not marked device-writable | first try |
| reclaim stops at the first descriptor | first try |
| full queue overwrites instead of refusing | after bounding the loop |
| **stored available index masked by queue size** | **only after a better case** |
| **publishes the chain's tail instead of its head** | **only after a better case** |

The fifth is the interesting one. My first test set `avail_idx = 65535` and asserted it wrapped to
0 — but masking gives 0 there too, so the two are indistinguishable at exactly the value that
looks like the edge case. A queue of 8 and a stored index of 10 separates them: wrapping gives 11,
masking gives 3. Masking the stored index is invisible for 65536 packets and then silently
overwrites live ring entries.

The sixth: the published-head check ran on a *single*-descriptor chain, where the head and the
tail are the same descriptor, so publishing either passed. Moved to a three-descriptor chain.

A third problem was in the test itself: an unbounded `while (vnr_add_chain(...) >= 0)` loop hung
for two minutes when the free-list bound was removed, instead of failing. A test that hangs is
worse than one that fails — it stops the suite instead of reporting. Now bounded, with the bound
asserted.

## Six tests that asserted the old world

Advertising `virtio-net` broke six existing tests, every one of which documented the state this
phase exists to change. One was written for exactly this:

> *"If a second network driver ever appears in the index, that test fails and is deleted."*

It did. The others moved to `e1000e` — a driver `device_drivers` resolves and `drivers.md` still
does not provide — so the mechanism stays tested while Firecracker moves out of that role. Two
packaging tests were rewritten around the real change: the refusal **moved down a layer** rather
than disappearing.

## Task 5: the cost, as V8's control

| | |
|---|---|
| Specification | **113 lines** (`drivers.md`) — against 63 for e1000 |
| Host reference | **135 lines** C (`virtio_net_reference/`) |
| Host test | **160 lines**, 29 checks |
| Harness | **55 lines** |
| Elapsed | one session, no blockers |
| Bugs the tests caught | 6 injected, 6 caught; 2 needed better cases |

The specification is larger than e1000's because it carries two transports. That is the point of
the driver, not overhead: MMIO is what every microVM uses, and a spec describing only PCI could
not serve the case that motivates it.

## What is not claimed

Under emulation a driver is verified against QEMU's model of the device, not the device. The ring
arithmetic is proved on the host; register programming is not, and the harness says so rather
than implying otherwise. This is the gap `CONFORMANCE-HARDWARE.md` records for silicon and it
applies here with full force.

The record's `specification` cites VIRTIO 1.2, now inventoried as `oasis-virtio/virtio-spec` by
V4 — but **not ingested**. `driver_strategy.py` therefore still refuses to justify `synthesize`
for this device, saying which command would fix it. That is an honest precondition, not an
oversight.

## Validation

1396 unit tests pass (was 1393), 111 SLM tests, 29 host checks under ASan/UBSan.

```
$ tests/kernel/run_virtio_net_test.sh            # no tree
exit 2 — nothing to verify
$ tests/kernel/run_virtio_net_test.sh --self-test
PASS (0 failures)
```

## Files

| File | Action |
|---|---|
| `agent/kernel_spec/subsystems/drivers.md` | UPDATED — VirtIO Network section, `provides` |
| `tests/kernel/virtio_net_reference/` | CREATED — reference + header |
| `tests/kernel/virtio_net_test.c` | CREATED — 29 checks |
| `tests/kernel/run_virtio_net_test.sh` | CREATED |
| `agent/tests/unit/test_target_join.py` | UPDATED — 3 tests moved to the new world |
| `agent/tests/unit/test_package_image.py` | UPDATED — the refusal moved down a layer |
| `agent/tests/unit/test_driver_verify.py` | UPDATED — synthetic absent command |

## Acceptance

- [x] A VirtIO Network section citing VIRTIO 1.2 by section, restating nothing from VirtIO Block
- [x] Both transports specified — MMIO discovery is not an afterthought
- [x] A host-testable reference for the ring arithmetic, marked not-shipped, ASan/UBSan clean
- [x] `run_virtio_net_test.sh` exists and exits 2 when there is nothing to check
- [x] `virtio-net` in `provides`; **no** `source_map` entry
- [x] A Firecracker target is no longer refused by D7
- [x] Cost recorded as V8's control
