# Plan: Join a Target to the Errata Table (D8)

**Source PRD**: `auton-hardware-definition.prd.md` — phase D8
**Depends on**: D1 (landed), H4 (landed), H5 (landed)
**Size**: the smallest remaining phase. Every input exists; nothing joins them.

## Summary

`machine_safety.py` can answer "is this machine safe to run this image on". It takes an
`Identity` — vendor, family, model, stepping — which until D1 nothing in the tree recorded in a
reviewable file. A target definition records exactly that.

So: a defined target's silicon is looked up in the errata table, and applicable errata are
reported **before** the build rather than discovered after.

## Evidence

- `agent/tools/machine_safety.py:106` `assess_machine(identity, image_capabilities, documents)` —
  the whole assessment already exists. It needs an `Identity` and a capability set.
- `agent/tools/errata_table.py:68-76` `Identity` — `vendor: str, family: int, model: int,
  stepping: int, microcode_rev: int | None`. Note the comment on `microcode_rev`: *"None means not
  read — not zero"*. The same distinction this plan must preserve one level up.
- `agent/tools/target_spec.py` `Target.silicon` — a dict of **strings**: `family: "6"`,
  `model: "142"`. `Identity` wants ints. That conversion is where an unstated value becomes a
  confident zero if nobody is careful.
- `agent/kernel_spec/targets/firecracker.md` — `vendor: unknown, family: 0, model: 0, stepping: 0,
  source: assumed`. **This is the case that matters.** Handed to `assess_machine` as-is it
  produces a clean bill of health for silicon nobody has identified.
- `agent/tools/machine_safety.py:58` — *"model {v.model}. This machine has not been examined —
  that is not the same as safe."* The rule is already written down; D8 must not violate it from
  a new direction.
- `agent/tools/package_image.py` `_record_target` (w6/D2, landed) — packaging already validates
  and records a target. The errata report belongs alongside it, in the same package.
- `agent/tools/target_spec.py` `Target.assumed_facts` — already reports which facts rest on an
  assumption. The join reads it rather than re-deriving the question.

## Patterns to Mirror

- **Three-valued verdict**: `errata_table.Verdict` — `APPLIES` / `NOT_APPLICABLE` / `UNKNOWN`.
  `assess_machine` already keeps `report.unknown` separate from `report.not_applicable`.
- **Unknown is never folded into safe**: `machine_safety.py:58`.
- **Report, do not refuse**: most errata are not fatal. `gate_capabilities` refuses because an
  unimplementable capability makes a useless image; an applicable erratum usually does not.

## Tasks

### Task 1: Target silicon to `Identity`
- **Action**: `silicon_identity(target) -> Identity | None`. Returns `None` — not a zeroed
  `Identity` — when the target's silicon cannot support a lookup.
- **Why `None` and not a default**: `Identity(vendor="unknown", family=0, model=0)` is a valid
  object that `assess_machine` will happily answer about, and the answer will be "nothing
  applies". A missing return value cannot be mistaken for an answer; a zeroed one can.
- **Gotcha**: the fields are strings in the target and ints in `Identity`. A non-numeric `family`
  must raise or return `None`, never `int()`-with-a-fallback.
- **Validate**: `qemu-pc.md` yields an `Identity`; `firecracker.md` yields `None`.

### Task 2: Assumed silicon yields UNKNOWN, never a clean bill
- **Action**: Where `target.silicon["source"] == "assumed"`, the join reports UNKNOWN for the
  whole machine and says why, rather than querying the table.
- **Why**: this is `machine_safety.py:58`'s rule applied one level up. A microVM guest inherits
  the host CPU and cannot read it; reporting "no errata apply" there is a confident false
  statement about silicon nobody has looked at.
- **Gotcha**: `Target.assumed_facts` already computes this. Use it — a second copy of the rule
  will drift from the first.
- **Validate**: `firecracker.md` produces an UNKNOWN assessment naming `silicon` as the reason,
  and the word "safe" appears nowhere in it.

### Task 3: Report before the build
- **Action**: The errata report is produced when a target is packaged, written into the package
  next to `PROVENANCE.json`, and summarised on stdout.
- **Why not a gate**: refusing a build because a 20-year-old erratum applies to the CPU would
  make the tool unusable on real hardware. The PRD asks for it *reported* before the build, and
  the useful failure is the narrower one in Task 4.
- **Gotcha**: `assess_machine` takes `image_capabilities`. Those come from the manifest, not the
  target — the join is target × manifest, and passing the wrong set silently changes which errata
  are judged relevant.
- **Validate**: packaging with `--target qemu-pc.md` writes an errata report; the report names the
  document and revision each verdict came from.

### Task 4: Refuse only the narrow case
- **Action**: Refuse when an erratum **applies**, the image **uses the affected capability**, and
  **no mitigation exists** in `kernel_spec/mitigations/`.
- **Why this is the right line**: all three conditions are already computable —
  `assess_machine` intersects applicable errata with image capabilities, and
  `mitigations/README.md` defines the registry with `addresses:` keyed as H4 keys errata. An
  image that will demonstrably compute wrong answers, with nothing available to do about it, is
  worth stopping.
- **Gotcha**: an erratum with verdict UNKNOWN must not trigger this refusal *or* be counted as
  clear. It is reported as unknown and the build proceeds with it named — the same three-way
  split `assess_machine` already keeps.
- **Validate**: a synthetic target matching a known un-mitigated erratum, with an image using the
  affected capability, is refused; the same target with the mitigation present is not; the same
  target with an image excluding the capability is not.

### Task 5: Answer open question 4 or record it unanswered
- **Action**: D2 records the question — *does an AUTON-hosted guest inherit the host's errata?* —
  in every derived guest target. D8 either answers it or leaves it recorded.
- **Why it belongs here**: this is the phase that knows what an erratum applying to a machine
  means. If the answer is still open after building the join, say so in the report rather than
  letting a silent absence read as "no".
- **Validate**: a guest target derived from a host with identified silicon produces an assessment
  that explicitly addresses inheritance, even if the answer is UNKNOWN.

## Validation

```bash
python agent/tools/machine_safety.py --target agent/kernel_spec/targets/qemu-pc.md \
    --intent "hand out addresses"
python agent/tools/machine_safety.py --target agent/kernel_spec/targets/firecracker.md \
    --intent "hand out addresses"       # UNKNOWN, names assumed silicon, never "safe"
python agent/tools/package_image.py "hand out addresses" --output /tmp/pkg \
    --target agent/kernel_spec/targets/qemu-pc.md    # writes the errata report
cd agent && python -m pytest tests/unit/test_machine_safety.py tests/unit/test_errata_join.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Assumed silicon produces a clean bill of health | **H** | Task 2 is the phase's central test; `Target.assumed_facts` already computes the input |
| A zeroed `Identity` is queried and answered confidently | **H** | Task 1 returns `None`, which cannot be mistaken for an answer |
| The refusal is too broad and blocks real hardware | **M** | Task 4's three conditions; an erratum alone never refuses |
| UNKNOWN quietly counted as clear | **H** | `assess_machine` already separates `unknown` from `not_applicable`; the join must not merge them when summarising |
| The errata documents are stale and the report reads as current | **M** | `assess_machine` already records `signatures` and document names per report; surface the revision in the summary |

## Acceptance
- [ ] A target's silicon produces an `Identity`, or `None` — never a zeroed one
- [ ] Assumed silicon yields UNKNOWN naming the reason, and never the word "safe"
- [ ] The report is produced at package time and names the document and revision behind each verdict
- [ ] A build is refused only when an erratum applies, the image uses the capability, and no mitigation exists
- [ ] UNKNOWN errata neither refuse the build nor count as clear
- [ ] Errata inheritance for hosted guests is answered, or recorded as unanswered
