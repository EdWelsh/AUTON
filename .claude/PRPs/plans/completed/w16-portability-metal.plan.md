# Plan: Metal: Boot-Only, then One Real NIC (windows-linux B4, B5)

## Summary
The end of the PRD's strictly serial chain: `0 → B1 → (B2, B3) → B4 → B5`. B4: the ISO on USB,
serial capture, `auton>` on the named machine with a real PCI scan, *"Expect the first attempt
to fail on firmware or serial, not on kernel code."* B5: identify the machine's actual NIC, get
one driver for it through the driver PRD's machinery (V4 strategy → record → verification),
and take a real DHCP lease the router agrees it issued. Every fact about the machine comes from
Phase 0's probed target file.

## User Story
As the project, I want AUTON running on a real computer and answering `what is my ip` with an
address the LAN's router issued, so that "an OS" is literally true.

## Problem → Solution
Emulator-only → a USB-bootable hybrid ISO (B3), serial capture per Phase 0's method, a B4 marker
transcript from real silicon, then a V4-selected NIC driver for the probed NIC id, generated or
ported per the strategy, verified by a lease in the router's table.

## Metadata
- **Complexity**: Large (and hardware-bound)
- **Source PRD**: `auton-windows-linux.prd.md`
- **PRD Phase**: B4, B5
- **Estimated Files**: 5 + a driver record + generated driver
- **Depends on**: `w15-portability-proxmox` (Phase 0: the named machine + target file), `w12-portability-uefi` (B3), `w13-generate-mm` (B2), `w12-loop-review-repair` (for B5's driver generation)
- **GATE**: physical access to the named machine and its serial console

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/kernel_spec/targets/<machine>.md` (from Phase 0) | all | firmware mode, NIC id, serial method |
| P0 | `agent/tools/driver_strategy.py` | 233-285 | B5's first step is `--device <nic id>`, recorded verbatim |
| P0 | `agent/kernel_spec/drivers/README.md` + `e1000.md` | all | the record format; e1000 lessons (`volatile` rings, `hlt` polling, gateway ARP) |
| P0 | `agent/tools/driver_verify.py` | gate | `implemented` only on an observed pass |
| P1 | `docs/HOST-MATRIX.md` | — | the metal row |

## Patterns to Mirror
### SELECTOR_FIRST
// SOURCE: w11 V8 plan Task 1: run the selector first, record its answer before anything else.
### OBSERVED_PASS
// SOURCE: agent/kernel_spec/drivers/README.md rule 4.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `docs/METAL.md` | CREATE | writing the USB (the `install.sh` from `package_image.py` refuses non-block devices and confirms), BIOS/UEFI settings from the target file, serial capture command |
| `scripts/metal-capture.sh` | CREATE | capture serial to `.artifacts/metal/<date>.log`, then run `markers.sh` against it |
| `agent/kernel_spec/drivers/<nic>.md` | CREATE (B5) | the V2 record for the probed NIC, strategy from the selector |
| `<ws>/kernel/drivers/net/<nic>.c` | GENERATED or ported (B5) | per strategy |
| `docs/HOST-MATRIX.md` | UPDATE | the metal row, with the serial log as evidence |

## NOT Building
- Storage, USB, graphics on metal. Boot and one NIC only.
- Supporting a second physical machine.

## Step-by-Step Tasks
### Task 1 (B4): Media + serial; boot; capture
- **GOTCHA**: Many modern boards have no RS-232 header. Phase 0 must have chosen IPMI SoL, a USB-TTL on a header, or (last resort) the EFI GOP framebuffer, photographed. The markers must reach *something* capturable.
- **VALIDATE**: markers through `[DEV] PCI scan: N devices found`, with the IDs matching the probed target file; `auton>` reached and answering.
### Task 2 (B5): The selector on the NIC id; record the decision
- **GOTCHA**: If the selector refuses (no inventoried spec), that is the result; the metal NIC then waits on the vendor documents. Do not fall back to e1000 on a non-e1000 NIC: that is the defect D7 removed.
### Task 3 (B5): The driver, verified by a lease
- **VALIDATE**: `what is my ip` answers with an address, and the router's lease table shows the image's MAC with that address (a screenshot or export as evidence).

## Validation Commands
```bash
scripts/metal-capture.sh /dev/tty.usbserial-XXXX
.venv/bin/python agent/tools/driver_strategy.py --device <nic-id>
```

## Acceptance Criteria
- [ ] B4: a serial transcript from real silicon with the boot markers and a working prompt
- [ ] B5: a router-confirmed DHCP lease, or a recorded selector refusal naming what is missing

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Firmware/serial blocks B4 | H | M | budgeted per the PRD; the hybrid ISO and multiple capture methods |
| The NIC has no open specification | M | B5 blocked | an honest refusal, recorded; choose a machine with an Intel e1000e/igb NIC in Phase 0 if possible |


---

## Closed 2026-09-23

Blocked on bare metal.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
