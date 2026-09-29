# Plan: Application to Environment, end to end — three applications, three runtimes

## Summary
The PRD's headline metric is "applications compilable to a running minimal environment: ≥3, in
different runtimes". Each of A1–A10 is proved on fixtures. This phase is the validation run
across all of them. Three real, small, external applications, one per runtime, each driven
through stage → Analyst → observe → manifest → (handoff) → Packager → probe → ablation, with
every PRD success metric read off the results rather than asserted. It plays the same part for
this PRD that the C1–C3 scenarios play for the completion PRD: the exam, not the backlog.

## User Story
As the owner, I want to hand AUTON three repositories I did not prepare for it and get, for
each, a working environment, the manifest that produced it, and a score saying how much of it
was necessary.

## Metadata
- **Complexity**: Large (operator time), Small (code)
- **Source PRD**: `prds/auton-application-to-environment.prd.md`
- **PRD Phase**: validation of A1–A10; closes the Success Metrics table
- **Depends on**: every `w17-app-*` … `w21-app-*` plan; D-A1, D-A2, D-A3 verdicts

---

## The three subjects (chosen before any run, recorded in the pre-registration)
| Runtime | Criteria | Why it is in the set |
|---|---|---|
| Python (WSGI/ASGI) | public repo, < 5k lines, one C-extension dependency, a health endpoint | the `dlopen`/C-extension case A5 exists for |
| Node | public repo, < 5k lines, native module optional | a second interpreter, different loader |
| Static binary (Go or C) | public repo, one listening port | the case where the minimal answer is nearly empty; over-claim is most visible here |

Each subject is pinned by commit. `probe.yaml` for each is written by the operator **before**
the Analyst runs.

## Protocol
The completion PRD's Generation Experiment Protocol, unchanged: pre-register (model, subjects,
commits, probes, predictions) → run once → archive transcripts → tools decide → report either
way.

## Success Metrics, read off the results
| PRD metric | Read from |
|---|---|
| Applications compilable to a running minimal environment | `run-intent-probe.sh app` = `WORKED`, count |
| Facts with no provenance | `artifact_spec --validate` refusals across all Analyst records (must be refused, so the count *reaching* A6 is 0) |
| Agent-asserted capability names absent from the index | A4 gate refusals, reported as a number (refused, not zero) |
| `observed` written by anything but `observe.py` | `test_observed_monopoly.py` passes; plus a grep of the three records |
| Required capabilities proved load-bearing | `ABLATION.json` `N of N` per app |
| Over-claims caught | `ABLATION.json` over-claimed count per app — **reported, not zero** |
| Downstream files changed | `git diff --stat` on A6's consumer list |

## Files to Change
| File | Action |
|---|---|
| `.claude/PRPs/reports/w22-app-three-runtimes-preregistration.md` | CREATE |
| `.claude/PRPs/reports/w22-app-three-runtimes-report.md` | CREATE |
| `prds/auton-application-to-environment.prd.md` | UPDATE — "Today" column of Success Metrics becomes measured |
| `docs/OPEN-WORK.md` | UPDATE |

## NOT Building
Anything. A defect found here is a new plan against the phase that owns it, and this run is
repeated as a new, labelled experiment.

## Step-by-Step Tasks
1. Choose and pin the three subjects; write their `probe.yaml`; pre-register.
2. For each: stage (A2) → Analyst run (A3/A4) → `observe.py` (A5) → `build_from_artifact` (A6) → `manifest_goal` (A7, no-op on container substrates) → Packager (A8) → `run-intent-probe.sh app` (A10) → `ablate.py` (A9).
3. Fill the metrics table; write the report; update the PRD.

## Acceptance Criteria
- [ ] Three pre-registered subjects, each with a recorded verdict at every stage.
- [ ] The PRD's Success Metrics table carries measured values, including over-claims found.
- [ ] Any subject that does not reach `WORKED` has its stopping stage and reason in the report.
