# Plan: Generated Mitigations (H7)

**Source PRD**: `auton-hardware-truth.prd.md` — phase H7
**Depends on**: H4 (landed), H6 (landed), w9 workspace safety (landed)
**Its control**: H6's `f00f-idt-remap.md`, written by hand

## Summary

H6 built the mitigation registry: mitigations as spec, with `cost` mandatory, `verify` mandatory
and mechanical, and `status` admitting `unmitigatable` as a real answer. Two entries exist, both
human-authored.

H7 asks whether an agent can implement one from that spec — and it is the third instance of the
same experiment F6 and V8 run, on the subject with the sharpest verification story: **a
mitigation's `verify` field already says exactly how to prove it was applied.** Neither a service
nor a driver has that.

## Evidence

- `agent/kernel_spec/mitigations/README.md:24-34` — the field table. `verify` is *"Mandatory, and
  mechanical. An image that claims a mitigation it did not apply is worse than one that declines
  it, because the claim is the part a user acts on."*
- `agent/kernel_spec/mitigations/f00f-idt-remap.md` — `status: implementable`, `requires: [vmm,
  arch]`, and a `verify` that is provocable: *"the first IDT page is read-only and a deliberate
  F00F sequence raises #UD rather than hanging the machine."* This is the worked example the PRD
  names.
- `agent/kernel_spec/mitigations/fdiv-reference-check.md` — `status: unmitigatable`. The registry
  already carries one of each, so an agent cannot assume every entry is implementable.
- `agent/tools/mitigation_registry.py:128-160` `assess()` — sorts applicable errata into
  `mitigable`, `declined`, `unmitigatable`. *"A mitigation needing `vmm` in an image without it is
  **declined**, not mitigated — and saying so is the point, because the alternative is claiming a
  fix that was never applied."*
- `agent/tools/errata_join.py` (D8) — the join that reports applicable errata before a build, and
  `spec/errata.json` in every targeted package.
- `agent/tools/machine_safety.py:58` — *"has not been examined — that is not the same as safe."*

## Patterns to Mirror

- **The same experiment shape as F6 and V8**: choose first, one run, gates decide, cost published
  against a recorded control.
- **`verify` is the referee**: unlike a service or a driver, a mitigation's spec already states
  the mechanical check. The agent does not get to propose its own.
- **Declined is not mitigated**: `assess()` already distinguishes them, and a generated mitigation
  must not blur it.

## Tasks

### Task 1: Reuse F6's harness, and add the row that matters here
- **Action**: Same cost rows, plus: did the generated mitigation's `verify` actually pass?
- **Why that row**: for a service, "it works" is a judgement. For a mitigation, the spec states
  the check, so the answer is mechanical and there is no room to argue.
- **Gotcha**: a mitigation that applies cleanly and whose `verify` fails is **worse than one that
  declines** — it makes a claim a user acts on. The harness must report a failed verify as a
  failure, not as a partial success.
- **Validate**: the harness reproduces H6's row from `f00f-idt-remap.md` and its verification.

### Task 2: Choose the mitigation, and check it is implementable first
- **Action**: Name it, and confirm `status: implementable` and that the image will carry the
  capabilities its `requires` names.
- **Gotcha**: picking `fdiv-reference-check` would measure the agent against an entry the registry
  says cannot be mitigated. That is a different and much shorter experiment.
- **Gotcha**: `assess()` will mark it **declined** if the image lacks `vmm` or `arch`. An agent
  producing a correct mitigation into an image that cannot apply it is not a failure of the agent,
  and the report must not record it as one.
- **Validate**: the chosen entry is `implementable` and its `requires` are in the image's slice.

### Task 3: Run the loop, once, as F6 does
- **Action**: One run, transcript and diff kept, budget recorded up front.
- **Gotcha**: a mitigation touches the IDT — `f00f-idt-remap` remaps a page and makes it
  read-only. w9's guards mean the agent cannot blind-overwrite `arch/x86_64/idt.c`; if it tries
  repeatedly, that is a finding about agent behaviour and goes in the report.
- **Validate**: the transcript is kept pass or fail.

### Task 4: The verification decides, and a failed verify is a failure
- **Action**: Run the mitigation's own `verify`. Record the outcome.
- **Why**: the whole registry rests on this field being load-bearing. H7 is where it either is or
  is revealed not to be.
- **Gotcha**: `f00f-idt-remap`'s verify needs a **deliberate F00F sequence**, which is an x86
  instruction sequence this host cannot execute — `scripts/preflight.sh:103-116` already records
  that this Mac cannot run x86 CPUID live and says so rather than passing silently. If the verify
  cannot run here, it is **unverified**, which V9 established is not a pass.
- **Validate**: the verify's outcome is one of passed / failed / could-not-run-here, and
  could-not-run-here is not counted as passed.

### Task 5: Report against H6, and against the other two experiments
- **Action**: Cost beside H6's, and the caught/attempted picture beside F6's and V8's.
- **Why three**: one experiment is an anecdote. Three subjects — a service, a driver, a mitigation
  — across three PRDs is the beginning of an answer to whether `README.md:11` holds.
- **Validate**: the report states all three, including where the agent did worse.

## Validation

```bash
scripts/measure_authorship.sh --mitigation f00f-idt-remap     # reproduces H6's control row
auton run "Implement kernel_spec/mitigations/<name>.md against the arch spec"
python agent/tools/mitigation_registry.py --errata <id> --capabilities <slice>
python agent/tools/machine_safety.py --family 6 --model 151 --stepping 2
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| A mitigation that applies but does not work is recorded as success | **H** | Task 1's gotcha and Task 4 — a failed verify is a failure |
| The verify cannot run on this host and is scored as a pass | **H** | Task 4's gotcha; `preflight.sh` already sets the precedent of announcing what a host cannot check |
| An unmitigatable entry is chosen | **M** | Task 2's first gotcha |
| `declined` is recorded as agent failure | **M** | Task 2's second gotcha — `assess()` already distinguishes them |
| Three experiments, three harnesses, no comparison | **H** | Task 1 reuses F6's |

## Acceptance
- [ ] The harness reproduces H6's cost row from its own artifacts
- [ ] The chosen mitigation is `implementable` and its `requires` are in the image
- [ ] One run, transcript kept regardless of outcome
- [ ] The mitigation's own `verify` decides; could-not-run-here is not a pass
- [ ] Cost published against H6's, and the picture stated beside F6's and V8's
