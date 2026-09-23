# Plan: Validation and Refusal (D6)

**Source PRD**: `auton-hardware-definition.prd.md` — phase D6
**Depends on**: D1
**Pairs with**: D1 — the format and its refusals are one idea

## Summary

The failure this exists to prevent: an underspecified target silently becoming the QEMU PC,
which is how every image would end up built for a machine nobody owns.

A target that cannot support a bootable image is refused, naming what is missing.

## Evidence

- `SLM/tools/build_corpus.py` `BUS_DEVICES` — the QEMU PC is the hardcoded default today, so
  "defaults to QEMU" is the current behaviour, not a hypothetical.
- `agent/tools/build_service.py` `gate_spec` — the precedent: a spec that validates but is not
  implementable (intent-C's stub) is refused with the reason, because it "passes every
  structural check and is not implementable, which is what makes it dangerous".
- `tests/kernel/run_leakage_test.sh` — exit 2 (*nothing to check*) is deliberately distinct from
  exit 0 (*clean*). Same three-state discipline applies here.
- `agent/tools/machine_safety.py` — *"no ingested document covers this silicon… that is not the
  same as safe"*. A target nobody described is not a QEMU PC.

## Tasks

### Task 1: What makes a target buildable
- **Action**: State the minimum per class. Bare metal needs devices and silicon; a microVM needs
  a hypervisor and machine type; an AUTON-hosted target needs a host image. Each minimum is
  justified by what a driver decision requires.
- **Validate**: each class's minimum is stated with its reason, not asserted.

### Task 2: Refuse, naming what is missing
- **Action**: `target_spec.py --validate` refuses an underspecified target and lists the absent
  facts. Never a bare "invalid"; never a default.
- **Validate**: `class: bare-metal` with no devices is refused naming `devices`; the message says
  how to supply them (probe, state, or derive).

### Task 3: Three states, not two
- **Action**: *valid*, *unverifiable*, *refused*. Unverifiable is when the ingested registry is
  absent so device ids cannot be checked — the target may be fine and we cannot say.
- **Why**: collapsing unverifiable into valid is how an unchecked target ships; collapsing it
  into refused makes the tool unusable without a populated cache.
- **Validate**: with `.cache/vendor` removed, a well-formed target reports unverifiable with a
  distinct exit code.

### Task 4: A target must not silently become another
- **Action**: A regression test asserting that no code path substitutes a default device set. The
  QEMU PC is a target like any other and must be *named*, never assumed.
- **Why a test**: this is the defect the phase exists for, and a defect with no test is an
  intention.
- **Validate**: the test fails if a default is reintroduced.

## Validation

```bash
python agent/tools/target_spec.py --validate <bare-metal, no devices>   # refused, names 'devices'
python agent/tools/target_spec.py --validate <microvm, no machine type> # refused, names it
rm -rf .cache/vendor && python agent/tools/target_spec.py --validate <valid>  # unverifiable, exit 3
cd agent && python -m pytest tests/unit/test_target_spec.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Refusals are so strict nothing validates | **M** | Minimums are per class and justified by what a driver decision needs — not by what would be nice to know |
| Unverifiable is treated as valid downstream | **H** | A distinct exit code, and the driver PRD's V4 must check it before selecting a strategy |
| A default creeps back in later | **M** | Task 4 is a regression test, not a convention |

## Acceptance
- [ ] Minimum viable target stated per class, each with its reason
- [ ] An underspecified target is refused naming the missing facts and how to supply them
- [ ] Three states — valid, unverifiable, refused — with distinct exit codes
- [ ] A regression test proves no path substitutes a default device set
