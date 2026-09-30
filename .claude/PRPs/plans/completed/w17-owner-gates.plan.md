# Plan: Owner Gates — every decision written as a question, every acquisition as one command

## Summary
Eight rows across the two open PRDs can only be closed by the owner: D1 (Doom licence), D2
(fleet endpoint), D-A1 (first substrate), D-A2 (syscall scope), D-A3 (subject trust), and the
acquisitions X1–X4. Two decision files exist (`doom-engine-licence.md`, `fleet-endpoint.md`);
three are marked "to be written" in `docs/OPEN-WORK.md`. This plan writes the missing three in
the house format (options, what each turns on, what is already true, a recommended default
**labelled as a recommendation**), and turns X1–X4 into an acquisition checklist where each
item is one ingest command. The agent writes the question; it does not take the decision.

## User Story
As the owner, I want every decision I owe to be a single short document with the options and
their consequences, and every acquisition to be "get this file, run this command", so that
unblocking the project costs me minutes of reading, not a re-derivation.

## Problem → Solution
Three decisions "to be written", X phases described in prose across two docs →
`agent/kernel_spec/decisions/{first-substrate,syscall-scope,subject-trust}.md` in the format of
`fleet-endpoint.md`, and `docs/ACQUIRE.md` with one row per X item: what, where to get it by
hand, the exact ingest command, and the gate that proves it landed.

## Metadata
- **Complexity**: Small
- **Source PRD**: both open PRDs
- **PRD Phase**: D1, D2, X1–X4 (`auton-completion`); D-A1, D-A2, D-A3 (`auton-application-to-environment`)
- **Estimated Files**: 5
- **Timing**: D-A3 and D-A1 **must** be decided before `w19-app-observe` starts; D-A1 before `w20-app-packager`

---

## Mandatory Reading

| Priority | File | Why |
|---|---|---|
| P0 | `agent/kernel_spec/decisions/fleet-endpoint.md` | the format: status line, why it is a decision, what is already true, options |
| P0 | `agent/kernel_spec/decisions/doom-engine-licence.md` | same, with a licence question |
| P0 | `prds/auton-application-to-environment.prd.md` §"D-A3 deserves reading", §"On D-A2" | the substance of the new decisions |
| P1 | `docs/OPEN-WORK.md` §decide, §hardware | where each is referenced; links must resolve |
| P1 | `agent/tools/vendor_fetch.py` (`--from-file`) | the X1/X2 ingest path |
| P1 | `docs/HOST-MATRIX.md`, `agent/hardware/CONFORMANCE-HARDWARE.md` | X3/X4 "what a host would newly prove" |

## Files to Change

| File | Action | Content |
|---|---|---|
| `agent/kernel_spec/decisions/first-substrate.md` | CREATE | D-A1. Options: **container** (the control plane's `docker` backend exists, fast to probe, shares the host kernel so syscall/driver claims are untestable) vs **microVM** (Firecracker/QEMU `microvm`, `hypervisors.yaml` already derives targets with 0 questions, slower, isolates A5's observation). Turns on: A5's sandbox, A8's output format, A9's cost per ablation step. Recommended default: container for A8/A9 throughput, microVM for A5 observation — labelled a recommendation |
| `agent/kernel_spec/decisions/syscall-scope.md` | CREATE | D-A2. Options: none in v1 / report-only (observed syscall set, with coverage, never enforced) / opt-in seccomp with coverage stated. States the PRD's warning: an almost-right profile is an outage. Turns on: whether `observe.py` records syscalls at all |
| `agent/kernel_spec/decisions/subject-trust.md` | CREATE | D-A3. The injection vector (a README instructing the Analyst), the blast radius the closed vocabulary already limits, and the options for A5: no-network disposable sandbox, no credentials, subject content quoted as data in prompts; or subject must be owner-authored. Turns on: A3's prompt framing, A5's sandbox, whether A7 may act on an unreviewed artifact |
| `docs/ACQUIRE.md` | CREATE | X1–X4 rows: X1 one Intel 82574 spec update → `vendor_fetch.py --from-file <pdf>` → `errata_join.py` finds an `e1000e` pair; X2 six Intel spec updates, one per generation → `retrodict.py` scores a cutoff; X3 an x86 machine → `run_conformance.sh` does not SKIP; X4 Proxmox token (env only) / Windows 11 / bare metal with serial → the host's `HOST-MATRIX.md` row |
| `docs/OPEN-WORK.md` | UPDATE | "to be written" → links; hardware table links `ACQUIRE.md` |

## NOT Building
- Verdicts. Each decision file ends `**Status: open**` with a blank verdict section. The recommendation is written as a recommendation.
- Any network fetch of Intel documents (the CDN refuses scripted downloads; a person downloads them).

---

## Step-by-Step Tasks

### Task 1: Three decision documents
- **ACTION**: write each in `fleet-endpoint.md`'s structure: status, why it is a decision, what is already true and testable (with file refs), options with consequences, which plans wait on it, an empty `## Verdict` section.
- **VALIDATE**: `pytest agent/tests/unit/test_doc_links.py`.

### Task 2: `docs/ACQUIRE.md`
- **ACTION**: one table; each row: item, where a human gets it, exact command, gate proving it landed, PRD phase it closes.
- **VALIDATE**: each command's `--help` runs; links resolve.

### Task 3: Point the open-work doc at them
- **ACTION**: replace "(to be written)" with links; add a line in the application PRD's phase table pointing D-A1..3 at the files.

## Acceptance Criteria
- [ ] Every D row in both PRDs links to a decision file that exists and has an empty verdict.
- [ ] Every X row links to an `ACQUIRE.md` entry with one command and one gate.
- [ ] `test_doc_links.py` passes.

## Risks
| Risk | Mitigation |
|---|---|
| A recommendation is read as a decision | wording: "Recommended default (not a decision)", and the verdict section stays empty |
| D-A3 written too permissively | it lists what the closed vocabulary does *not* limit — A5 executes the subject — so the risk is stated, not minimised |
