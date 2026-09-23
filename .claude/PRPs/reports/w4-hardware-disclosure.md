# Report: Disclosure Pipeline (H11)

**Source PRD**: `auton-hardware-truth.prd.md` — phase 11

> *"A finding with no disclosure path is not a deliverable."*

So this exists **before** the conformance harness, not after. The first real finding should not
have to invent a process in a hurry.

## The refusal that matters most

A finding is private until disclosure, and **a git commit is publication**. So the tool refuses
a tracked destination outright, reusing the path check written for the vendor-document licensing
rule:

```
>>> record(..., store=ROOT / "agent" / "hardware")
REFUSED: refusing to write findings into …/agent/hardware: it is tracked.
A finding is private until disclosure, and a commit is publication.
```

`.disclosure/` is gitignored, and a test asserts against `git ls-files` that nothing under it is
tracked.

## A finding must be a finding

Four fields are refused when empty, each with the reason:

- **`spec_citation`** — a divergence is divergence *from something*. Without it there is only a
  surprise, and a finding without provenance is a rumour. Same rule the errata records carry.
- **`expected`** and **`observed`** — "wrong result" is not reproducible.
- **`reproducer`** — how to see it again, on what silicon.

And `silicon` must be `family:model:stepping` — the key H5 captures:

```
REFUSED: silicon 'some intel chips' must be family:model:stepping[:microcode].
'Some Intel chips' is not a finding.
```

A vendor with no published security contact is refused, listing the ones that have them. A
finding cannot be filed against a vendor nobody knows how to reach, so `contacts.yaml` is data
rather than something to look up in the moment — Intel, AMD, Arm, RISC-V International,
Qualcomm and Apple, all public channels, no credentials.

The Apple entry records something the rest do not: Apple publishes no silicon specifications, so
a divergence there cannot be stated against a vendor document at all. A finding can only cite
third-party documentation and **must say so**.

## Two behaviours worth naming

**The id is derived from the silicon and the divergence**, so recording the same defect twice is
caught rather than producing two records of one thing — while a different stepping is correctly a
different finding.

**`withdrawn` is a status, not a deletion.** A finding that turns out to be our own bug stays on
record. Deleting it loses the evidence that the harness produces false positives, and that rate
is the number deciding whether anyone should trust it.

## The embargo clock

`disclosure.py due` lists findings whose embargo has expired or is close, and exits non-zero on
an expired one. An embargo nobody tracks quietly becomes permanent, and a finding sat on
indefinitely is worse for users than one published on schedule.

`published` and `withdrawn` leave the clock; everything else stays on it.

A dispute is recorded **alongside** the finding rather than escalated, per the PRD. `disputed`
is a terminal state, not a failure.

## Acceptance

- [x] Findings are private by construction; a tracked store is refused
- [x] A finding without spec citation, expected/observed, reproducer or precise silicon is refused
- [x] Vendor contacts are data; a vendor without one cannot be filed against
- [x] The embargo clock is tracked and expiry is visible
- [x] Disputes are recorded alongside; withdrawal is a status, not a deletion
- 24 tests

## What this is not

This does not decide **whether** something is a defect — that is H10's conformance work, which
needs real hardware on multiple steppings and is recorded as partly unobtainable
(`agent/hardware/CONFORMANCE-HARDWARE.md`).

This is what happens to a finding once one exists. It has never processed a real finding, because
none has been produced. The demo record made while testing was deleted rather than left behind
looking like one.
