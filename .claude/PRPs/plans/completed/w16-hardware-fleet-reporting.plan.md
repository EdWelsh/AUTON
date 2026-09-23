# Plan: Fleet Reporting of Conformance Divergences, with Consent (H10e)

## Summary
Mercurial cores were found at fleet scale, around one per thousand machines, and
`CONFORMANCE-HARDWARE.md` states AUTON cannot reach that scale in-house. H10e is how scale could
come from deployments instead: images that opted in contribute conformance results, and
divergences aggregate by silicon identity. Because this ships data *off* a user's machine, the
plan is consent-first and privacy-minimal. It builds the **report format, the consent flow, and
a local aggregator**. A hosted collection endpoint is a separate deployment decision, recorded
and not assumed.

## User Story
As an AUTON user, I want to choose whether my machine's conformance results help find defective
silicon, and to see exactly what would be sent, so that fleet detection never costs me privacy
I did not agree to give.

## Problem → Solution
First-boot results stay on the machine (H10d) → an opt-in `[CONF] share?` prompt, a signed-free,
identifier-free report (silicon identity + clause verdicts only), a `fleet_aggregate.py` that
merges reports and flags a divergence seen on ≥2 independent reports of the same stepping, and
the flagged cases routed to `disclosure.record`.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-hardware-truth.prd.md`
- **PRD Phase**: H10e
- **Estimated Files**: 6
- **Depends on**: `w15-hardware-conformance-every-image` (H10d), H11 (landed)

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/hardware/CONFORMANCE-HARDWARE.md` | "Stated limits" | the claim this must not overstate |
| P0 | `agent/tools/disclosure.py` | 41-185 | private findings, embargo clock: the sink |
| P0 | `agent/tools/errata_table.py` | 70-80 | `Identity`: the only machine fields a report may carry |
| P1 | `w15-hardware-conformance-every-image.plan.md` | markers | the input |

## Patterns to Mirror
### PRIVATE_BY_DEFAULT
// SOURCE: agent/tools/disclosure.py: findings stored privately under `agent/hardware/disclosure/`, never published before the embargo.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/conformance/report.md` | CREATE | the report schema: `vendor, family, model, stepping, microcode, hypervisor bit`, clause verdicts, image hash. **No** serials, MACs, IPs or timestamps finer than a day. Refuses any other field |
| `agent/kernel_spec/subsystems/slm.md` | UPDATE | the consent dialogue: default **no**; shows the exact report before asking; the answer persists on disk if storage exists, and is re-asked every boot otherwise |
| `agent/tools/fleet_aggregate.py` | CREATE | ingest report files → per `(identity, clause)` counts → a divergence is flagged when ≥2 reports from distinct images agree and the oracle disagrees |
| `agent/tests/unit/test_fleet_aggregate.py` | CREATE | single-report divergence not flagged; two agreeing flagged; a report with a forbidden field rejected; QEMU (hypervisor bit) reports never counted as silicon evidence |
| `agent/kernel_spec/decisions/fleet-endpoint.md` | CREATE | the open decision: where reports go (none, a Git-based drop, a hosted service), the data-protection obligations of each. The owner decides |

## NOT Building
- A hosted endpoint or any network upload code before that decision is recorded.
- Telemetry of anything other than conformance verdicts.

## Step-by-Step Tasks
### Task 1: Schema with a denylist-by-construction
- **IMPLEMENT**: an allowlist of fields; the serialiser refuses others; a test feeds a report with a MAC address and expects refusal.
### Task 2: The aggregator
- **GOTCHA**: Virtualised reports (the H5 hypervisor bit) prove nothing about silicon. Count them separately and never toward a flag.
### Task 3: The consent dialogue spec
- **VALIDATE**: acceptance markers: `[CONF] share? (shows report) → default no`.
### Task 4: The endpoint decision record (owner)

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/test_fleet_aggregate.py -q
.venv/bin/python agent/tools/fleet_aggregate.py --reports <dir>
```

## Acceptance Criteria
- [ ] Opt-in, default no, with the report shown before consent
- [ ] Reports carry the allowlisted fields only
- [ ] Two-agreeing-reports rule; virtualised reports excluded
- [ ] Endpoint decision recorded by the owner before any upload code

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The fleet never reaches meaningful size | H | — | stated in `CONFORMANCE-HARDWARE.md`; the machinery is still correct at N=2 |
| Privacy regression via a later field addition | M | H | the allowlist test fails on any new field |


---

## Progress: Tasks 1-2 (2026-09-22)

Allowlist schema with per-field refusals, local aggregator that never counts virtualised reports, 18 tests including one that greps the module for network clients. **Remaining**: Task 3 (the consent dialogue's spec and markers) and Task 4 (the endpoint decision, owner).


---

## Closed 2026-09-23

The allowlist schema, the local aggregator (19 tests) and the consent dialogue's spec are done. The endpoint is an owner decision, written up rather than assumed.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
