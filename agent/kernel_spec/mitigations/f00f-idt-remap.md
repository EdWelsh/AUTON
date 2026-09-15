---
mitigation: f00f-idt-remap
addresses: [intel-pentium-f00f]
class: fault
requires: [vmm, arch, allocator]
cost: one 4 KiB page and one TLB entry; no measurable runtime cost after boot
verify: the page holding the first seven IDT entries is mapped read-only, and a
        deliberate `lock cmpxchg8b` against a non-writable operand raises #UD
        rather than hanging the processor
status: implementable
---

# F00F — Invalid Operand with Locked CMPXCHG8B

## The defect

On Intel Pentium (family 5) processors, the instruction sequence
`lock cmpxchg8b` with a register operand — encoded `F0 0F C7 C8`, which is where the name comes
from — causes the processor to hang. The locked bus cycle is issued before the invalid-operand
exception is raised, and the exception's own descriptor fetch cannot complete while the bus is
locked.

Any unprivileged program could execute it. The machine stops until power-cycled.

This is a **fault-class** defect: the machine misbehaves visibly. That is what makes it
mitigable — the failure can be provoked on purpose, so a fix can be proven.

## The mitigation

The hang is a deadlock between the locked cycle and the descriptor fetch. Break it by making
the fetch fail *first*, in a way the processor can handle.

1. Allocate a page and place the IDT so that its **first seven entries** (through vector 6,
   `#UD`) sit at the very end of that page, with the remainder of the IDT on the next page.
2. Map the first page **read-only**.
3. The faulting descriptor fetch now takes a page fault (#PF, vector 14) before the
   invalid-opcode path deadlocks. #PF's descriptor lives on the second, writable page, so its
   fetch completes.
4. The page-fault handler recognises the address as an IDT descriptor fetch, and delivers #UD
   to the offending task itself.

The program dies. The machine does not.

## Requirements

`vmm` — the mitigation is a page-permission change, so it needs virtual memory. `arch` for IDT
placement. `allocator` for the page.

An image without `vmm` cannot apply this, and must report the erratum as **declined — the image
lacks the capability**, not as mitigated. See [README.md](README.md) rule 1.

## Cost

One 4 KiB page, one TLB entry, a page-fault handler branch that is not taken in normal
operation. No measurable runtime cost after boot.

Cheap enough that the honest recommendation for affected silicon is to apply it unconditionally
— but the cost is written down so that is a decision rather than an assumption.

## Verification

Mechanical, on the running machine:

1. Read the IDT base from `sidt`. Assert the page containing entries 0–6 is mapped read-only.
2. Execute `lock cmpxchg8b` with a register operand in a context whose fault is recoverable.
3. Assert `#UD` was delivered and execution continued.

Step 3 is the one that matters. Steps 1 and 2 confirm the arrangement; only step 3 shows the
processor did not hang, which is the entire claim.

**On silicon that does not have the defect**, step 2 raises `#UD` directly and the test passes
trivially. That is not a false pass: the claim being verified is "this sequence does not hang
this machine", and on unaffected silicon it does not.

## Acceptance Criteria

1. The IDT's first page is read-only after `idt_init`.
2. A deliberate F00F sequence raises `#UD` and the machine continues.
3. An image lacking `vmm` reports the erratum as declined, naming the missing capability.
4. The cost is reported alongside the claim, so a reader can see what was spent.
