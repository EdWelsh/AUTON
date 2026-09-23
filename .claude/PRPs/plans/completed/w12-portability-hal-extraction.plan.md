# Plan: HAL Extraction, with a Build-Time Gate (windows-linux D1)

## Summary
`kernel_spec/arch/hal.md` specifies the boundary (*"All kernel subsystems call HAL interfaces —
never raw architecture instructions"*), and the base breaks it in exactly these places:
`__asm__ volatile("hlt")` at `net/dhcp.c:153` and `net/setup.c:79, 93`; `cli; hlt` at
`boot/kernel_main.c:24`; and `dev/pci.c` including the x86 port-I/O header for config space.
This plan adds the HAL headers to the scaffold templates, adds a **`[gate: hal]`** to
`build_service.py` that refuses arch instructions or arch headers in portable code, and cuts
`kernel-base-v5` with those sites routed through `arch_halt()`, `arch_idle()` and
`arch_pci_config_*()`. Behaviour must not change: e2e stays green. D2 (aarch64) is impossible
without this.

## User Story
As whoever ports AUTON to a second architecture, I want portable code that provably contains no
x86, so that a port implements `hal.md` and changes nothing else.

## Problem → Solution
The HAL exists on paper; 5 violations in the base; nothing checks → `[gate: hal]` (objdump-free:
a source scan of `kernel/` excluding `kernel/arch/**` for inline asm, `io.h`, and a list of x86
mnemonics); `kernel-base-v5` passing it; the gate applied to every generated tree.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-windows-linux.prd.md`
- **PRD Phase**: D1
- **Estimated Files**: 7 + a new base tag
- **Depends on**: `w12-kernel-base` (v3 is the pre-refactor control)

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/kernel_spec/arch/hal.md` | all (43 `arch_*` functions) | the contract |
| P0 | base (`kernel-base-v4`) `kernel/net/dhcp.c:153`, `net/setup.c:79,93`, `boot/kernel_main.c:24`, `dev/pci.c` | — | the violations |
| P0 | `agent/tools/build_service.py` | 256-300 | gate order and `GateFailure` style |
| P1 | `agent/kernel_spec/arch/aarch64.md` | all | confirm each HAL function D1 introduces has an aarch64 meaning (`wfi` for halt, ECAM for PCI config) |

## Patterns to Mirror
### GATE
// SOURCE: agent/tools/build_service.py: `raise GateFailure(f"[gate: capabilities] …")`. Name the gate, name the file:line, say why.
### SCAN_NOT_GUESS
// SOURCE: agent/tools/build_manifest.py phantom detection: a mechanical check, with reasons in the message.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/arch/hal.md` | UPDATE | add `arch_idle()` (wait for interrupt), `arch_halt()` (stop forever), `arch_pci_config_read32/write32`, if absent |
| `agent/kernel_spec/templates/x86_64/arch/hal_x86_64.h` | CREATE | inline implementations for x86 |
| `agent/tools/hal_gate.py` | CREATE | scan `kernel/**` minus `kernel/arch/**`: `__asm__`/`asm(`, `#include "io.h"`/`<arch/`, and bare mnemonics in macros; report file:line |
| `agent/tools/build_service.py` | UPDATE | `[gate: hal]` after `[gate: sources]` |
| `agent/tests/unit/test_hal_gate.py` | CREATE | each of the 5 base violations detected; an arch file ignored; a comment containing "hlt" not flagged |
| git tag `kernel-base-v5` | CREATE | v4 + the refactor; the e2e control run on both |
| `scripts/kernel-base.sh` | UPDATE | default to v3 once it is green; v2 stays reachable via `--rev` |

## NOT Building
- The aarch64 port (D2).
- Moving drivers under the HAL beyond PCI config. Serial and the NIC stay as they are; they already live in `drivers/`.

## Step-by-Step Tasks
### Task 1: Gate first, run against v2 (RED: reports 5)
- **GOTCHA**: `hlt` appears in comments ("hlt-yielding poll loops"). Strip comments before scanning, or the gate trains people to ignore it.
### Task 2: HAL additions + x86 header
### Task 3: Refactor the base into v3
- **ACTION**: extract v2, route the 5 sites through the HAL, commit on a scratch branch holding only `kernels/x86_64`, and tag it. `kernels/` stays out of `main`: the tag lives on a detached commit, as v1 and v2 do.
- **GOTCHA**: The `hlt` in `dhcp.c:153` is load-bearing: *"yield to QEMU until next tick"*. `arch_idle()` must be `hlt` on x86 exactly, not a spin, or DHCP under SLIRP regresses (the w0/F4 lessons).
- **VALIDATE**: `hal_gate.py` clean on v3; `e2e.sh --target <v3> --skip-train` equals v2's markers; `run-acceptance.sh` net checks still pass.
### Task 4: Gate in the factory

## Validation Commands
```bash
.venv/bin/python agent/tools/hal_gate.py --tree <v2-ws>     # 5 violations
.venv/bin/python agent/tools/hal_gate.py --tree <v3-ws>     # 0
scripts/e2e.sh --target <v3-ws> --skip-train
cd agent && ../.venv/bin/python -m pytest tests/unit/test_hal_gate.py -q
```

## Acceptance Criteria
- [ ] Zero direct arch use in portable code of v3, by gate
- [ ] E2E and network acceptance unchanged between v2 and v3
- [ ] Every generated tree passes `[gate: hal]`

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A subtle timing change in the net polling | M | M | `arch_idle` is exactly `hlt`; network acceptance in Task 3 |
| The gate misses a macro-hidden instruction | M | L | a mnemonic list inside macros; aarch64 compile (D2) is the final proof |
