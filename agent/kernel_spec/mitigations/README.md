# Mitigation Registry

H4 answers *does this erratum apply to this machine*. This says *what can be done about it*,
what that costs, and **how to prove it was applied**.

A mitigation is a spec, in the same voice as `kernel_spec/services/`. It is not code: agents
implement from these, and validators gate the result.

## Shape

```yaml
---
mitigation: f00f-idt-remap
addresses: [intel-pentium-f00f]
class: fault
requires: [vmm, arch]
cost: one page of physical memory and one TLB entry; no measurable runtime cost
verify: after applying, the first IDT page is read-only and a deliberate F00F
        sequence raises #UD rather than hanging the machine
status: implementable
---
```

## Why each field exists

| Field | Why |
|---|---|
| `mitigation` | Its identity; must match the filename, as service specs do |
| `addresses` | The errata it mitigates, keyed as H4 keys them. A mitigation that names no erratum is a change without a reason |
| `class` | `fault` (the machine misbehaves visibly — F00F hangs) or `semantic` (the machine computes a wrong answer — FDIV). They need different verification: a fault can be provoked, a wrong answer must be compared against a reference |
| `requires` | Capabilities the mitigation itself needs. Applying one that needs `vmm` to an image without it is a build failure, not a runtime surprise |
| `cost` | **Mandatory.** A mitigation with unstated cost gets applied everywhere. F00F's remap costs a page; a Spectre-class flush costs a measurable fraction of every syscall. An image should be able to decline on cost, and cannot if nobody wrote it down |
| `verify` | **Mandatory, and mechanical.** An image that claims a mitigation it did not apply is worse than one that declines it, because the claim is the part a user acts on |
| `status` | `implementable`, `needs-microcode`, `unmitigatable`. The third is a real answer: some errata have no software fix, and saying so is more useful than silence |

## Rules

1. **Never claim what was not verified.** `verify` must be executable on the running machine,
   not a code review step. H8 reports "mitigated" only for mitigations that verified.
2. **Cost is stated even when it is zero**, so "no cost" is a measurement rather than an
   omission.
3. **An applicable erratum with no mitigation is reported, not omitted.** The registry's job
   includes saying what it cannot fix.
4. **A mitigation addresses errata, not vulnerabilities in general.** If no ingested document
   names it, it does not belong here — that is the same provenance rule the errata records carry.

## Entries

| Mitigation | Class | Addresses | Status |
|---|---|---|---|
| [f00f-idt-remap.md](f00f-idt-remap.md) | fault | Intel Pentium F00F | implementable |
| [fdiv-reference-check.md](fdiv-reference-check.md) | semantic | Intel Pentium FDIV | unmitigatable in software |

The two are deliberately different shapes. F00F is a fault with a real software fix; FDIV is a
wrong answer with none. A registry that only expressed fixable things would have no way to say
the most important thing it can say.
