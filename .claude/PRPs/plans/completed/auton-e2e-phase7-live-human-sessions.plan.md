# Plan: Live Human Sessions — Phase 7

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 7 — Live human sessions
**Complexity**: Small (process, not code) — but it is the only bar that catches what the rubric can't

## Summary

One unscripted 20-minute session per training rung, with findings written down and fed back
as new eval prompts or defects. This is the phase that stops the Phase 6 score from becoming
a target that gets gamed.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Report structure | `.claude/PRPs/reports/scratch-os-ondevice-chat-slm-report.md:1-20` | Summary, then "Assessment vs Reality" comparing predicted to actual |
| Honest deviation logging | same report | Deviations recorded explicitly (fp32 not int8, and why) rather than quietly dropped |
| Interactive boot | `kernels/x86_64/Makefile:69-71` | `make run-neural` with `-serial stdio` gives the interactive prompt |
| Eval feedback loop | Phase 6 `tests/eval/prompts.jsonl` | Where findings land as new prompts |

## Files to Change

| File | Action | Why |
|---|---|---|
| `.claude/PRPs/reports/e2e-human-session-<rung>-<date>.md` | CREATE (per session) | The findings record |
| `tests/eval/prompts.jsonl` | UPDATE | Findings promoted into the eval set |

## Tasks

### Task 1: Session protocol
- **Action**: Write the (short) protocol: boot via `make run-neural`, 20 minutes, unscripted,
  transcript captured, no fixing anything mid-session — observations only. Note which rung
  and which model manifest.
- **Validate**: protocol fits on one page and is repeatable by the same person weeks later.

### Task 2: Run one session per rung
- **Action**: After 3a, after 3b, after 3c. Capture the full serial transcript alongside the
  notes.
- **Validate**: transcript plus notes committed per session.

### Task 3: Convert findings
- **Action**: Every finding becomes exactly one of: a new eval prompt, a filed defect, or an
  explicit "no action, here's why". Nothing is left as an unclassified observation.
- **Mirror**: the report convention of recording deviations rather than dropping them.
- **Validate**: each session's report ends with a classified findings table.

### Task 4: Close the loop
- **Action**: New prompts land in `tests/eval/prompts.jsonl` and are scored in the next eval
  run, so the eval set grows with what humans actually asked.
- **Constraint**: prompts added after rung 3b's corpus is frozen must be checked for
  contamination before use as a training signal.
- **Validate**: the eval set grows measurably between rungs.

## Validation

```bash
make -C kernels/x86_64 iso-neural MODEL=$PWD/SLM/work/auton-slm.bin run-neural | tee \
  .artifacts/human-session-$(date +%F).log
ls .claude/PRPs/reports/e2e-human-session-*      # one per rung
wc -l tests/eval/prompts.jsonl                   # grows between rungs
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Sessions get skipped under delivery pressure | **H** | Phase 7 is an acceptance gate on each rung, not an optional extra |
| Findings stay as prose and never become tests | **H** | Task 3's forced classification — every finding gets exactly one disposition |
| Single-operator bias: the developer asks only what they know works | **M** | Note it honestly; consider a second person for one session. Out-of-domain prompts partially compensate |
| Session transcripts leak host details into the repo | **L** | Local LAN IPs only; review before committing |

## Acceptance
- [ ] One-page protocol written
- [ ] One session per completed rung, transcript + notes committed
- [ ] Every finding classified: eval prompt, defect, or reasoned no-action
- [ ] Eval set demonstrably grows from real human usage
