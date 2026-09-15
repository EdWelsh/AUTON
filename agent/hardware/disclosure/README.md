# Disclosure

The conformance harness can find real silicon defects. This is the path a finding takes before
anyone outside sees it.

The PRD's framing: *"A finding with no disclosure path is not a deliverable."* So this exists
before the harness does, not after.

## The rules, and why each is enforced rather than advised

**1. Nothing is published on discovery.** A divergence goes to a private record with the
reproducer, the silicon identity, and the spec citation. `disclosure.py` writes into
`.disclosure/`, which is gitignored — the tool refuses a tracked path, the same way
`vendor_inventory.py` refuses to cache a non-redistributable document into one.

**2. Vendor first**, through their published security contact, 90-day default embargo,
negotiable on request. Contacts live in [contacts.yaml](contacts.yaml) so a finding cannot be
filed against a vendor nobody knows how to reach.

**3. Mitigate quietly.** A mitigation may ship during embargo if it does not disclose the
defect. This is normal practice — Linux shipped several transient-execution mitigations before
announcement. `kernel_spec/mitigations/` entries may therefore exist for embargoed findings, and
the registry does not link back to a private record.

**4. Reproducers are not weapons.** A reproducer demonstrates divergence from a specification.
It is not built into an exploit and not distributed during embargo. The record holds it; the
package does not.

**5. Credit the vendor's timeline.** A disputed finding is recorded *alongside* the dispute, not
escalated. `status: disputed` is a terminal state, not a failure.

## What a record must carry

A finding without provenance is a rumour, exactly as an erratum without a citation is:

| Field | Why |
|---|---|
| `silicon` | family/model/stepping/microcode, as H5 captures it. "Some Intel chips" is not a finding |
| `spec_citation` | Document, revision, section. A divergence is divergence **from something**, and without the citation there is only a surprise |
| `expected` / `observed` | Both values. "Wrong result" is not reproducible |
| `reproducer` | How to see it again, on what silicon |
| `class` | `fault` or `semantic`, as the mitigation registry uses |
| `reported_at` / `embargo_until` | The clock, so an embargo that has expired is visible rather than forgotten |
| `status` | `private`, `reported`, `acknowledged`, `disputed`, `published`, `withdrawn` |

`withdrawn` matters: a finding that turns out to be our own bug must be recorded as withdrawn,
not deleted. Deleting it loses the evidence that the harness produces false positives, which is
the number that decides whether anyone should trust it.

## The embargo clock

`disclosure.py --due` lists findings whose embargo has expired or is close. An embargo nobody
tracks is an embargo that quietly becomes permanent, and a finding sat on indefinitely is worse
for users than one published on schedule.

## What this is not

This does not decide *whether* something is a defect. That is H10's conformance work. This is
what happens to a finding once one exists — and it exists now so that the first real finding
does not have to invent it in a hurry.
