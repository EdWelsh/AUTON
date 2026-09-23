# Plan: Proxmox Access, KVM Boot, and Real KVM OS Profiles (windows-linux 0, B1 confirm, C2)

## Summary
Phase 0 is the PRD's own first step: *"Establish and document Proxmox access … choose the physical
test machine and record firmware mode, NIC PCI id, storage controller, and serial access
method."* Nothing in this repo can do that without the owner: access and hardware are facts only
the owner holds. This plan turns Phase 0 into a checklist that produces machine-readable facts
(a target file from `probe_ingest.py`), then runs B1's confirmation (the same ISO timed on
Proxmox KVM, beside the CI ratio from `w12-portability-linux-bench`), and C2 (boot the three
container OS profiles and correct `profiles.py` to what actually happens).

## User Story
As the owner with a Proxmox host, I want AUTON's hardware claims about my machine and hypervisor
recorded as probed facts, so that B-lane and C-lane work stops being guesswork.

## Problem → Solution
No named machine, no Proxmox path → `agent/kernel_spec/targets/<machine>.md` from a real probe;
`scripts/proxmox.sh` (upload ISO, create VM, boot with serial, collect markers) using a scoped
API token from the environment; the B1 ratio on real KVM; `profiles.py` statuses set from
observed boots.

## Metadata
- **Complexity**: Medium (mostly operational)
- **Source PRD**: `auton-windows-linux.prd.md`
- **PRD Phase**: 0, B1 (confirmation), C2
- **Estimated Files**: 6
- **GATE**: the owner supplies Proxmox reachability and an API token (never committed), and names the physical machine

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/prds/auton-windows-linux.prd.md` | Phase 0, B1, C2 | success signals |
| P0 | `agent/tools/probe_ingest.py` | 1-20, 194-250 | lspci/cpuinfo/dmidecode → a target file with `source: probed` |
| P0 | `agent/kernel_spec/targets/README.md` | all | the target format; every fact carries a source |
| P0 | `controlplane/src/controlplane/` profiles module (`profiles.py`) | all | the three KVM OS profiles to make honest |
| P1 | `docs/HOST-MATRIX.md` | all | rows to add |

## Patterns to Mirror
### SECRETS_FROM_ENV
// SOURCE: agent/orchestrator/cli.py:79-115: keys from env vars or an uncommitted config, a clear error when missing.
### PROBED_FACTS
// SOURCE: agent/tools/probe_ingest.py `to_target`: `source: probed` on every fact.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `docs/PHASE0-CHECKLIST.md` | CREATE | the steps the owner runs: token scope (VM.Allocate, Datastore.AllocateSpace on one storage), the probe commands, serial access options (IPMI SoL / USB-TTL) |
| `agent/kernel_spec/targets/<machine>.md` | CREATE (from a probe) | the named physical machine |
| `scripts/proxmox.sh` | CREATE | `PROXMOX_HOST`, `PROXMOX_TOKEN_ID`, `PROXMOX_TOKEN_SECRET` from the env; upload ISO, create VM (e1000, serial socket), start, read the serial log, stop, destroy |
| `docs/HOST-MATRIX.md` | UPDATE | the Proxmox row; B1 ratio (Proxmox KVM vs Mac TCG vs CI KVM) |
| `controlplane/…/profiles.py` | UPDATE | each profile's status from observed boots: `works`, `boots-no-app`, `blocked: <EULA/arch/…>` |
| `controlplane/tests/test_profiles_truth.py` | CREATE | no profile says `works` without a recorded observation (date + evidence file) |

## NOT Building
- Metal boot (B4/B5, `w16-portability-metal`).
- Storing any credential in the repo.

## Step-by-Step Tasks
### Task 1: Checklist (human), then the probe → target file
### Task 2: `proxmox.sh`, dry-run mode first (prints the API calls)
- **GOTCHA**: API tokens with privilege separation need explicit ACLs. Record the minimal ACL in the checklist.
### Task 3: B1: 12/12 markers + transcript on Proxmox; timings beside CI and the Mac
### Task 4: C2: boot windows-dockur / android (budtmo) / macos-dockur; record truth; correct `profiles.py`
- **GOTCHA**: macOS in a VM has licensing terms that restrict it to Apple hardware. Record that as a status (`blocked: licence on non-Apple hardware`) rather than working around it.

## Validation Commands
```bash
scripts/proxmox.sh --dry-run
scripts/proxmox.sh boot <iso>
cd controlplane && python -m pytest tests/test_profiles_truth.py -q
```

## Acceptance Criteria
- [ ] A named machine with a probed target file
- [ ] A Proxmox command that runs from this Mac
- [ ] B1: 12/12 markers on Proxmox KVM, ratio recorded
- [ ] C2: ≥2 of 3 profiles run an app, or each failure encoded as an honest status

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A credential leaks | L | H | env-only; a pre-commit grep for `PVEAPIToken` |
| Profiles fail for licensing reasons | M | L | an honest status is a success per the PRD |


---

## Closed 2026-09-23

Blocked on the Proxmox host.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
