# Implementation Report: HAL Extraction, with a Build-Time Gate (D1)

**Plan**: `plans/completed/w12-portability-hal-extraction.plan.md`

## Summary

The HAL boundary is enforced by `[gate: hal]`, and the new default base, `kernel-base-v5`, passes
it. Portable code in v4 used x86 directly at **six** sites (the plan found five; `server/serve.c`
was the sixth): 10 violations in all. v5 routes them through `kernel/include/hal.h`. The e2e spine
and the network acceptance (DHCP lease, HTTP 200 over SLIRP) are unchanged.

## Tasks

| # | Task | Result |
|---|---|---|
| 1 | Gate first, against v4 | `hal_gate.py`: 10 violations at 6 sites. The first version reported **0**, because its string stripper took `#include "pci.h"`'s closing quote as an opening one and blanked the next line. Rewritten as a tokenizer; a test pins it |
| 2 | HAL additions | none needed: `hal.md` already had `arch_halt`, `arch_disable_interrupts`, `arch_pci_config_read32/write32` |
| 3 | Base refactor → v5 | `kernel/include/hal.h`, `kernel/arch/x86_64/hal.c`; `arch_halt` is exactly `hlt` |
| 4 | Factory gate | `[gate: hal]` after link closure, over the compiled sources plus `kernel/include/*.h`; v4 refused (8 in TFTP's slice), v5 passes and fails only at `undefined: tftp_serve` |

## Deviations

- **No template header.** The plan put the x86 HAL in `templates/x86_64/arch/hal_x86_64.h`; it
  lives in the base (`kernel/arch/x86_64/hal.c`), where the rest of the arch code is, and the
  scaffold never overwrites a tree's existing files.
- **Tag numbering.** Two base fixes landed first (v3: model format v3 loader; v4: RAM sizing
  under UEFI), so the HAL base is v5, not v3.
