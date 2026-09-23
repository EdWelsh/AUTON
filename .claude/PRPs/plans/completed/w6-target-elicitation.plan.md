# Plan: Elicitation (D5)

**Source PRD**: `auton-hardware-definition.prd.md` — phase D5, the last
**Depends on**: D1–D4, all landed
**Why last, on purpose**: the metric is how rarely it is reached. Building it first would have
made a form the product.

## Summary

D2 derives a target from an AUTON host's provenance. D3 derives one from a hypervisor and machine
type. D4 reads one off a running machine. D5 asks about **what is left** — and the PRD's
hypothesis is that what is left is usually nothing.

So this phase is as much a measurement as a feature: for each target class, how many questions
does a complete definition actually need?

## Evidence

- `agent/tools/target_spec.py:318-360` `check_completeness` — already computes the missing-fact
  list and names each one with its reason. Elicitation does not need to decide what to ask; it
  needs to turn that list into questions. Re-deriving the list would be a second copy of the rule.
- `agent/tools/target_spec.py` `PLATFORM_IMPLIES_DEVICES` — what each class takes from its
  platform rather than from an enumeration. This is why a microVM needs two answers and bare
  metal needs many.
- `agent/tools/probe_ingest.py` `probe()` — what a paste answers. D5 must not ask anything a
  probe would have answered; the honest first move for an unreachable-but-describable machine is
  *"can you run `lspci -nn`?"*, not twelve questions.
- `agent/tools/intent_manifest.py:125-136` `DEFAULTS` — *"Applied when the sentence does not say.
  Recorded, never silent."* The same rule, one level out: an elicited answer is recorded with
  `source: user-stated`, which is what makes it contestable later.
- `auton-hardware-definition.prd.md:52-66` — **the container case.** *"A kernel cannot run inside
  a container."* The request means a microVM the runtime schedules, or an OCI image shipping the
  ISO as an artifact. *"Guessing between these produces either an unbootable image or a useless
  one"*, so D5 must surface the distinction rather than resolve it.
- `agent/tools/machine_safety.py:58` — *"has not been examined — that is not the same as safe"*.
  A user who does not know an answer must be able to say so, and "unknown" must not become a
  default.
- `agent/tools/probe_ingest.py:255` — the only interactive pattern in the tooling is reading
  stdin. There is no prompt loop to mirror, so this plan sets one.

## Patterns to Mirror

- **Refusal names the field**: `target_spec.TargetError`.
- **Recorded, never silent**: `intent_manifest.DEFAULTS`.
- **A third state that is a real answer**: `errata_table.Verdict.UNKNOWN`, `status:
  unmitigatable`. "I don't know" is an answer, not a failure to answer.
- **Deterministic before interactive**: `subsystems/slm.md`'s shell-idiom table puts the
  deterministic path *before* the model. Same shape: derive, then probe, then ask.

## Tasks

### Task 1: Ask only what is left
- **Action**: `agent/tools/elicit.py` — take a partial target (or none), run `check_completeness`,
  and turn each missing fact into one question.
- **Why from the validator**: the list of what is missing already exists and is already justified
  per class. Writing a second list of questions would drift from it, and the drift would show up
  as either asking for something the format does not need or failing to ask for something it
  does.
- **Gotcha**: `check_completeness` raises on the *first* set of problems it finds, with all of
  them named in one message. Parse the structured list, not the string — a question generator
  built on message text breaks the moment a refusal is reworded.
- **Validate**: a target missing only `firmware` asks exactly one question.

### Task 2: Offer the cheaper path first
- **Action**: Before asking about devices, ask whether the user can run `lspci -nn`. If they can,
  hand off to D4 and ask nothing further about devices.
- **Why**: the PRD's hypothesis says *"even then `lspci -nn` output answers most of it"*. A tool
  that asks twelve device questions when one paste would do has made the form the product.
- **Validate**: answering "yes" to the probe offer reduces the remaining question count to the
  non-device ones; measured, not asserted.

### Task 3: The container case is surfaced, never resolved
- **Action**: When the user says *container*, *docker*, *k8s* or *pod*, ask which of the two
  meanings they intend, stating plainly that a kernel cannot run inside a container.
- **Why it cannot be defaulted**: the two answers produce different artifacts — a `microvm`
  target, or an OCI image carrying an ISO. Guessing yields an unbootable image or a useless one,
  and the user cannot tell which they got until it fails.
- **Gotcha**: do not "helpfully" pick the microVM reading because it is the more common one. The
  PRD names this risk as **H** and the mitigation is that D5 surfaces the distinction.
- **Validate**: the word "container" in any answer produces the disambiguation question, and
  neither branch is chosen without an answer.

### Task 4: Every answer carries `source: user-stated`
- **Action**: Facts from elicitation are written with `source: user-stated` and a provenance
  block naming the session.
- **Why**: D3 forbids a derivation writing `probed`; D4 is the only tool that may. This is the
  third leg — a stated fact must be distinguishable from an observed one, because a user
  describing hardware they do not have is a recorded risk, and D8's errata join will often
  contradict a wrong claim.
- **Validate**: no fact from elicitation says `probed` or `derived`; a round-trip through
  `target_spec.load` shows `user-stated` on each.

### Task 5: "I don't know" is an answer
- **Action**: A user may decline any question. The fact is then left unstated, and the target is
  refused by D6 naming it — not filled with a plausible default.
- **Why**: this is `machine_safety.py:58`'s rule in the interactive path. A form that will not let
  you say "I don't know" collects a guess and records it as a statement.
- **Validate**: declining every question produces no target file and a refusal naming what is
  still missing.

### Task 6: Measure the hypothesis
- **Action**: Count questions per class, end to end, and write the number into the report.
- **Why this is the deliverable**: the PRD says *"If this holds, the interactive path is a
  fallback rather than the main road. If it does not, the elicitation UX is the product and
  should be designed as such."* That is a claim with a number behind it, and this is the phase
  that can finally produce it.
- **Validate**: a table — `auton-hosted`, `microvm`, `vm` with a probe, `vm` without, `bare-metal`
  with a probe, `bare-metal` without — each with its question count.

## Validation

```bash
python agent/tools/elicit.py --class microvm --answers hypervisor=firecracker,machine=default
python agent/tools/elicit.py --name my-box --answers-file answers.txt --out targets/my-box.md
python agent/tools/target_spec.py --validate targets/my-box.md
python agent/tools/elicit.py --measure          # the hypothesis, as a table
cd agent && python -m pytest tests/unit/test_elicit.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| It becomes a 40-question form | **H** | Tasks 1, 2 and 6. Questions come from the validator's own list, the probe is offered first, and the count is measured and published |
| The container case is resolved silently | **H** | Task 3; the PRD names this as the mitigation for that exact risk |
| An elicited guess is indistinguishable from a probe | **H** | Task 4. D3 and D4 already hold the other two legs by test |
| "I don't know" is not offered, so a guess is recorded | **M** | Task 5 |
| The question generator drifts from the format | **M** | Task 1 reads the validator's structured list rather than duplicating it |
| Interactive code is untestable | **M** | Answers are suppliable non-interactively; the prompt loop is a thin shell over a pure function |

## Acceptance
- [ ] Questions come from `check_completeness`, not a second list
- [ ] A probe is offered before any device question, and answering yes removes them
- [ ] "Container" surfaces the microVM/artifact distinction and resolves neither
- [ ] Every elicited fact carries `source: user-stated`; none says `probed` or `derived`
- [ ] A declined question leaves the fact unstated and the target refused naming it
- [ ] Question counts per class measured and published in the report
