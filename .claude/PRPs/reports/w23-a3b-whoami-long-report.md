# Report: w23 A3b, whoami with a 4 h analyst budget

**Run 2026-10-08**, as [pre-registered](w23-a3b-whoami-long-preregistration.md). A different
experiment from A3 (budget doubled to 4 h), same model, subject, probe and exercise.

**Question:** was whoami's A3 failure budget or capability?
**Answer: budget.** Every stage passed with no human input.

| stage | result | time |
|---|---|---|
| analyst | merged `subject.artifact.yaml` | 42 min |
| manifest | 3 requirements, 1 assumption | 0 s |
| packager | image built, 0 extras (agent-authored) | 28 min |
| observe | 3 observed, 2 unindexed; exercise exit 0 | 21 s |
| regate | 5 requirements, 0 missing | 5 s |
| probe | WORKED, 2 checks passed from outside the application | 2 s |
| ablate | 0 of 1 load-bearing; over-claimed `path:/etc/localtime` | |

**Prediction vs result.** Predicted: analyst merges in 2–4 h, packager then likely fails on
Go multi-stage into scratch. Actual: the analyst took 42 min (well inside the 2 h A3 budget's
neighbourhood, so the A3 timeout was not simply "too short" for a clean run; the A3 attempt
was likely a slow or unlucky pass) and the packager succeeded. Both halves of the prediction were wrong.

**Caveats.** One run. The A3 timeout at 2 h and this 42 min success are both single samples,
so variance between runs is as likely as budget as the cause. Ablate found nothing
load-bearing and flagged `path:/etc/localtime` as over-claimed, the same over-claim pattern as the
node subject.

**Effect on A3.** With this run whoami counts as fully agent-driven under the longer budget:
2 of 3 (node-js-getting-started, whoami), js-example still stopped at the packager.
The label stands: 2 of 3 is under a changed budget, not the pre-registered one.
