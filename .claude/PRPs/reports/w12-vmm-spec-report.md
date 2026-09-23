# Implementation Report: VMM Spec, Host-Proved

**Plan**: `plans/completed/w12-vmm-spec.plan.md`

## Summary

`vmm` is no longer phantom. `mm.md` carries five REQUIRED sections written alongside a reference,
and a 31-check host suite proves them under ASan/UBSan. Five injected bugs are all caught.
`source_map.yaml` no longer maps `vmm`/`slab` to files that never existed, so F00F now resolves
to **declined: image lacks vmm** for an honest reason rather than a phantom one. The VMM itself is
generated in `w13-generate-mm`.

## Tasks

| # | Task | Result |
|---|---|---|
| 1 | Tests first | `tests/kernel/vmm_test.c`, 31 checks; hooks in `vmm_reference/include/vmm_host.h`: a PMM with failure injection, `phys_to_virt` over a host arena, an `invlpg` **log**, the boot root, NX support |
| 2 | Spec | `mm.md`: Boot Handover, Huge-Page Split, Permission Change (`vmm_protect`, new), Intermediate Tables and OOM, a TLB invalidation table, and No-Execute |
| 3 | Reference | `vmm_reference/vmm.c`, x86-64 4-level over the hooks; PASS 31/31 |
| 4 | Injected bugs | 5/5 caught (below) |
| 5 | Source map | `vmm`, `slab` removed with the w8-style comment; unmapped, not phantom, against `kernel-base-v2` |
| 6 | CI | "VMM suite" step on both hosts |

## Injected bugs

| Bug | Checks failing |
|---|---|
| no invalidation when remapping a present page | 2 |
| PS copied into split PTEs, where bit 7 is PAT | 2 |
| a split drops the neighbours' RW | 2 |
| OOM leaks the first intermediate table | 3 |
| translation drops the page offset | 3 |

## What writing the reference found

`vmm_get_physical` returns 0 for both "unmapped" and "mapped to frame 0". That is `mm.md`'s
interface, and it makes the function unusable as a presence test. The reference uses a separate
walk. A generated VMM that tests presence with `vmm_get_physical(v) == 0` breaks on the first page
of physical memory. The spec keeps the interface and states the ambiguity.

## Deviations

- `x86_64.md` already had the full PTE table, including the PS/PAT duality. It gained a pointer to
  the split rule and its SDM citation, not a second table.
