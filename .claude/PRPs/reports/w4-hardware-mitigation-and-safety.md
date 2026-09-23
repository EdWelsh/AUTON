# Report: Mitigation Registry (H6) and "Is This Machine Safe?" (H8)

**Plans**: `w4-hardware-mitigation-registry.plan.md`, `w4-hardware-is-this-safe.plan.md`
**Source PRD**: `auton-hardware-truth.prd.md` — phases 6 and 8

H4 answers whether an erratum applies. These answer what can be done about it, and what to tell
the person asking.

## The registry

`kernel_spec/mitigations/` — front-matter plus prose, in the services format's voice. Seven
fields, two of them mandatory for reasons worth stating:

**`cost`** — a mitigation with unstated cost gets applied everywhere and degrades every image.
F00F's remap costs one page and one TLB entry; a Spectre-class flush costs a measurable
fraction of every syscall. An image should be able to decline on cost, and cannot if nobody
wrote it down. Stated even when zero, so "no cost" is a measurement rather than an omission.

**`verify`** — an image that claims a mitigation it did not apply is worse than one that
declines it, because the claim is the part a user acts on. Must be executable on the running
machine, not a code-review step.

`class` is `fault` or `semantic`, and the distinction is load-bearing: a fault can be provoked
on purpose, so its fix can be proven. A wrong answer can only be found by comparing the machine
against a reference — which is a different kind of check, and the one that generalises to
defects nobody has documented.

## Two entries, deliberately opposite

**`f00f-idt-remap`** — the Pentium F00F hang. `lock cmpxchg8b` with a register operand issues
the locked bus cycle before the invalid-operand exception, and the exception's own descriptor
fetch cannot complete while the bus is locked. Any unprivileged program could stop the machine.

The fix breaks the deadlock by making the descriptor fetch fail *first*: put the first seven IDT
entries at the end of a read-only page, so the fetch takes a page fault — whose own descriptor
is on the next, writable page — and the handler delivers `#UD` to the offending task. The
program dies; the machine does not.

**`fdiv-reference-check`** — the Pentium FDIV defect, and it is in the registry precisely
because **no software mitigation exists.** The processor returns a wrong quotient in hardware.
A registry that only recorded fixable defects would have no way to say the most important thing
it can say: *this machine computes incorrectly, we detected it, and we cannot fix it.*

Its verification is a comparison against a reference — `4195835.0 / 3145727.0`, the pair Thomas
Nicely used — rather than provoking a fault. That is what makes it the template for finding
defects nobody has documented yet.

## Four categories, and the one that matters most

| category | meaning |
|---|---|
| `mitigable` | a mitigation exists and this image has what it needs |
| `declined` | a mitigation exists and the image lacks its capabilities |
| `unmitigatable` | no software fix exists |
| `applicable` | applies, and nothing in the registry addresses it |

Measured on the same errata against two image shapes:

```
full image:  mitigable 1, declined 0, unmitigatable 1
no vmm:      mitigable 0, declined 1, unmitigatable 1
             [declined] intel-pentium-f00f -> f00f-idt-remap: image lacks vmm
```

A Doom-shaped slice has no `vmm`, so it **cannot** apply the F00F remap — and says so, rather
than claiming a fix that was never applied. That is the failure the `declined` category exists
to prevent.

An applicable erratum with no mitigation is reported, never omitted. The registry's job includes
saying what it cannot fix.

## Unknown is never folded into safe

The single most important behaviour here, and the easiest to get wrong.

```
$ machine_safety.py --family 25 --model 33
No ingested document covers GenuineIntel family 25 model 33.
This machine has not been examined — that is not the same as safe.
```

"No known issues" and "no knowledge" read identically in a summary and are opposite statements.
A machine for which nothing was ingested is unexamined. Reporting it as safe would be the most
damaging thing this tool could do, because that summary is exactly what a user acts on.

Three tests hold it: silicon no document covers, no documents at all, and a sweep asserting the
summary never contains "is safe" without the examination caveat.

The report also states **what it consulted** — which documents, how many errata, and whether
each covers this silicon. An errata list six months stale reads as current unless it says when
it was retrieved.

One further test asserts every erratum lands in exactly one bucket: `counts() + unknown +
not_applicable` equals the document's total. An erratum falling through a gap is one nobody is
told about.

Measured on a real Alder Lake identity against the ingested Specification Update: 66 applicable,
28 not applicable, 0 undetermined, all 94 accounted for.

## Acceptance

**H6**
- [x] Format carries errata, capability, cost and verification, each justified
- [x] Expresses two structurally different mitigations without new fields
- [x] The F00F remap is written and implementable
- [x] Applicable errata with no mitigation are reported, never dropped

**H8**
- [x] Four categories reported separately; unknown never folded into safe
- [x] An identity with no ingested document reports no-knowledge rather than safe
- [x] The report states which documents it consulted
- [~] **Answered from the table, before the model** — the tooling is deterministic and
      table-driven, but nothing wires it into the kernel's chat path yet. `dev.md` specifies
      that pattern for `what cpu is this`; the same hook is where this belongs, and it needs
      the kernel side written
- 25 tests

## Follow-on

- H7 implements the F00F remap from its spec. That needs agents, and the loop still cannot be
  trusted with a workspace (the `net.h` overwrite).
- No ingested document names `intel-pentium-f00f` or `intel-pentium-fdiv` — they predate the
  Specification Updates fetched. The registry entries are keyed on identifiers that H2's
  ingestion does not yet produce, so the join works only for errata named by hand. Ingesting a
  Pentium-era document, or mapping these to their modern identifiers, closes it.
- `verify` is prose today. It should become executable, which is what makes "mitigated" a
  measurement rather than a claim.
