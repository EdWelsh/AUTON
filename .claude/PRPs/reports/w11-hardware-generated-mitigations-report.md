# Implementation Report: Generated Mitigations (H7)

## Summary

**Not run, on the plan's own terms.** H7's Task 2 requires the chosen mitigation to be
`implementable` **and** its `requires` to be in the image's slice before the loop starts. The
only implementable entry, `f00f-idt-remap`, requires `vmm`. No tree AUTON can build has a VMM.
The registry's own `assess()` answers **declined, image lacks vmm**, and the plan says a
declined mitigation is not an agent result and must not be recorded as agent failure.

So the answer to *"can an agent implement a mitigation from its spec?"* is **not yet
askable**. The blocker is a VMM, which is generation work in its own right, and it belongs in
the next PRD session (below).

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Reuse F6's harness, add the verify row | Complete | `measure_authorship.py --mitigation f00f-idt-remap` produces H6's row, the first time one has existed. See below |
| 2 | Choose, and check it is implementable first | **Complete: precondition fails** | `implementable`, but `vmm` is phantom |
| 3 | Run the loop once | **Not run** | Task 2 gates it. Pre-registered in `w11-authorship-preregistration.md` before any run |
| 4 | Verify decides | Not reached | The analysis of what could run here is below, because it will matter when this *is* run |
| 5 | Report against H6, F6, V8 | Complete | below |

## Task 2: the precondition, checked mechanically

| Check | Result |
|---|---|
| `f00f-idt-remap` status | `implementable` |
| `fdiv-reference-check` status | `unmitigatable`: the only other entry, correctly not chosen |
| `requires` | `[vmm, arch, allocator]` |
| `build_manifest.resolve(["vmm","arch","allocator"], [], <last tracked tree>)` | `phantom_capabilities: [slab, vmm]`. `kernel/mm/vmm.c` does not exist |
| What the tree does instead | `boot.S` identity-maps 4 GiB with **2 MiB** pages. No 4 KiB page exists to make read-only, which is the entire mitigation |
| `mitigation_registry.py --errata intel-pentium-f00f --capabilities arch,allocator` | `[declined] … (image lacks vmm)` |
| Same, with `vmm` claimed | `[mitigable]`. The registry is right; the tree is what is missing |

`source_map.yaml` maps `vmm` to `kernel/mm/vmm.c`, a file that has never existed in any tracked
tree. The phantom detection added in w8 reports it correctly. Nothing had asked.

## Task 1: H6's control row, first measured here

```
f00f-idt-remap — H6 control, human-authored spec; never implemented
  spec_lines               80
  implementation_lines     0
```

H6 recorded no cost row. It wrote the specification, and nothing implements it. The control
is therefore a spec with no implementation and a verify that has never run. When H7 does run,
the agent's figure is compared with *zero human implementation lines*. The honest reading of
any result is then "an agent did what no human here has done", not "an agent matched a human".

## Task 4, in advance: what the verify can and cannot prove on this host

The verify has three steps. Step 3 is the claim: `lock cmpxchg8b` with a register operand
raises `#UD`, and the machine continues.

- **This Mac cannot execute x86**, as `preflight.sh` has said since w2.
- **Under QEMU TCG the verify passes trivially, and that is not evidence.** TCG does not emulate
  the Pentium's locked-bus deadlock, so the sequence raises `#UD` whether or not the IDT was
  remapped. The spec already says this for unaffected silicon (*"passes trivially … not a false
  pass"*). Under emulation it proves only that the remap did not break `#UD` delivery. Steps 1–2
  (the IDT page is read-only) remain meaningful under QEMU.
- **Only a family-5 Pentium can make step 3 non-trivial.** `CONFORMANCE-HARDWARE.md` already
  lists that as partly unobtainable.

So a future H7 run should score steps 1–2 under QEMU as **passed** and step 3 as
**could-not-run-here**, never as passed. That is V9's rule, and the plan's.

## Against F6 and V8

| | F6 (service) | V8 (driver) | H7 (mitigation) |
|---|---|---|---|
| Ran? | yes, once | yes, once | **no: precondition** |
| Outcome | see the F6 report | see the V8 report | declined: image lacks `vmm` |

Three subjects across three PRDs were meant to start answering whether `README.md:11` holds.
Two ran. Neither produced authored output (see their reports). The third cannot be asked until
there is a VMM.

## For the next PRD session

1. **A VMM is on the critical path of hardware-truth**, not just the factory. Every
   page-permission mitigation (F00F, and any W^X-class hardening) needs 4 KiB mappings. The
   seed tree's 2 MiB identity map is a boot convenience, not a design.
2. **`vmm` and `slab` are phantom in `source_map.yaml`.** They should either be removed, as
   `framebuffer` and `virtio-blk` were in w8, or implemented. A mapping to a file that never
   existed is the defect the map's own header warns about.
