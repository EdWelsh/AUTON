# Report: Intent-Scoped SLM Corpus (intent-D)

**Plan**: `.claude/PRPs/plans/w1-slm-scoped-corpus.plan.md`
**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase D

## The hypothesis, and the answer

The PRD's central claim: *the model is bad because it is general.* Most measured garbage was
cross-intent mis-routing, and intent classes that cannot coexist in an image cannot mis-route
into each other. Scoping the corpus to a capability manifest should therefore drop the garbage
rate **with no modelling change**.

**It does not.** Measured on the in-scope half of the 65-prompt eval, same architecture, same
kernel, same harness, only the corpus differing:

| | in-scope correct-or-honest | in-scope garbage |
|---|---|---|
| Unscoped control | 40/50 (80%) | 10 (20%) |
| Doom-scoped | 39/50 (78%) | 11 (22%) |

A one-prompt difference. The hypothesis is **refuted**: 20-22% is not a generality artefact,
and scoping will not remove it.

Whole-set, scoping is actively worse — 23% garbage against 34% — because the image still gets
asked network questions it can no longer answer (see *The image is not actually scoped*).

## What did work: grounding (Task 1)

The other half of the plan was a truthfulness fix, and it holds.

`UNKNOWN_DEVICES` carried `10ec:8139` and `1022:2000` — a Realtek NIC and an AMD bridge on no
bus AUTON boots — in 14 records each. The model learned a deflection template with a
real-looking id baked in and emitted it for questions naming no device at all. Measured
before: 5 phantom citations per 50 novel turns.

`BUS_DEVICES` is now the single source of truth and `UNKNOWN_DEVICES` derives from it.

| | PCI ids cited across 65 answers | not on the bus |
|---|---|---|
| Unscoped control | 26 | **0** |
| Doom-scoped | 23 | **0** |

`scripts/session.sh` reports `PASS grounding — no answer cited hardware outside the bus`,
which was FAIL before.

The second half of that defect mattered more than the id list. The model reached for the
unknown-device template because **nothing covered a hardware question with no id**. 36 records
now teach the behaviour that belongs there. The three mis-routing cases the PRD names by hand:

| prompt | before | control (grounding fix, unscoped) |
|---|---|---|
| `i need gpu access` | cited a phantom Realtek NIC | asks for a PCI id — **correct** |
| `can i run nginx` | the kubernetes roadmap | asks for a PCI id (still a mis-route, but no false fact) |
| `check everything` | the DHCP lease | declines honestly |

So the defect the hypothesis pointed at is real and is fixed — by grounding, not by scoping.

## What replaced the garbage

The rate is flat but its character changed. The dominant in-scope failure is now
**over-refusal**: the model declines questions it demonstrably can answer — `lsmod`,
`meminfo`, `which roles are available?`, `how long have you been running` — 10 of 11 in-scope
garbage verdicts. `session.sh` puts a number on it: 28 of 40 novel turns declined.

That is a different problem from the one the PRD describes. The 3b failures were confidently
wrong; these are under-confident. Over-refusal is a retrieval/capacity problem, and it points
at the rule engine and the model's size, not at the breadth of the corpus.

One self-inflicted case: the new no-id clarification became its own over-applied template
(`how is networking configured on this box`, `is anything wrong with this machine`). Same
pathology as the phantom-id template it replaced, minus the false fact. Worth watching — it
suggests small models over-apply *whatever* deflection template is nearest, and adding one is
not free.

## The image is not actually scoped

The most consequential finding, and it was not in the plan.

The out-of-scope half collapses from 67% to 27% correct-or-honest under scoping. That is not
a scoped image correctly declining — it is a **general kernel with a narrowed model**. The
kernel is unchanged: `slm.c` tries the model first and falls through to a deterministic rule
engine whose tables are compiled in. A Doom image built this way still answers `what is my ip`
from `answer_ip()`, still lists `8086:100e(e1000)`, still offers `web server` as a role.

Corpus scoping alone therefore cannot produce a minimal image. **The manifest must scope the
kernel's rule tables and role list, not only the corpus** — otherwise `excludes` is enforced
on the training data and ignored by the machine that ships. This belongs in intent-A/B/C
(capability index, service spec) before any further corpus work.

Three truthfulness leaks that only an artifact check would have found, all fixed:

- the refusal advertised "network" on an image with none;
- the devices answer annotated `8086:100e(e1000)` when no net driver ships, claiming a binding
  that does not exist;
- troubleshooting tags read the answer while the question could be NIC-specific.

The refusal, the devices line and the composite status line are now rendered per image. A
Doom image no longer states an IP it never had. Both scoped corpora carry **zero** mentions of
any excluded capability, checked on the built artifact.

## The harness was miscounting, and the old baseline is suspect

The first scoped run scored 42% garbage. Eleven consecutive prompts had empty answers, and
`auto_grade` scored an empty answer as GARBAGE — rubric rule 1, correct for a model that says
nothing, wrong when the prompt was never delivered.

`eval.sh` sent every prompt on a fixed 0.7s cadence, waited `DRAIN_SECS=4`, then killed QEMU.
That works only while answers are faster than the cadence. Scalar fp32 inference under
emulation is not: the machine fell behind and was killed mid-queue. **A slower model looked
like a worse one.**

Fixed three ways, in increasing order of durability:

1. `NOT_ASKED` — a prompt whose echo never appears was never delivered. It leaves the
   denominator, the run is flagged TRUNCATED, and the PASS/FAIL bar is not applied. A score
   over a truncated run is worse than no score, because it looks like one.
2. The watchdog scales with prompt count and model type instead of a fixed 300s.
3. `eval.sh` is now **closed-loop**: it waits for the machine to return to an idle prompt
   before sending the next, with a per-prompt timeout. This removes the guess entirely.

Consequence worth stating: **the recorded 22% rung-3b baseline was measured with the
open-loop harness** and may contain truncation counted as garbage. The control in this report
was re-measured with the fixed harness for exactly that reason — comparing against the
recorded number would have compared two different instruments.

## Attempts, including the failures

| # | What | Outcome |
|---|---|---|
| 1 | Scoped corpus, 300s watchdog | 42% garbage — 11 prompts never sent, scored as garbage. Invalid |
| 2 | Watchdog scaled to 8s/prompt | 4 prompts still unsent. TRUNCATED correctly reported; bar withheld |
| 3 | Watchdog at 14s/prompt | Identical 4 unsent — proved it was not the watchdog |
| 4 | Isolated `i need gpu access` ×1 | Answers fine. Not an input-specific hang |
| 5 | Last 20 prompts only | Same 4 unsent — not positional either |
| 6 | 30× `uptime` | All 30 fine (rule-engine path, fast) |
| 7 | 20× `i need gpu access` | Dies after ~13 — reproducible, and neural-path specific |
| 8 | Same, `DRAIN_SECS=180` | **All 21 complete.** No kernel hang; the harness was killing a busy machine |
| 9 | Closed-loop harness, scoped | 65/65 delivered, 0 truncated |
| 10 | Closed-loop harness, control | 65/65 delivered, 0 truncated |

A further regression, found by re-running the rule-engine lane afterwards: the closed-loop
wait deadlocked on `install a web server`, which parks the kernel on "press any key to stop"
rather than a prompt. It cannot reach a prompt until it receives the key, and the loop was
waiting for one before sending it. `wait_for_idle` now treats waiting-for-keypress as settled
and has a stability valve for states it does not recognise. A first attempt at the fix also
died with SIGPIPE: `tail | grep -q` under `pipefail` reports 141 when grep exits early, so
every match read as a miss.

**The result does not depend on the harness version.** Re-running the scoped model on the
final harness gives 62 of 65 answers byte-identical; the three that differ are uptime
readings, which change with wall-clock. The run is also 2.5x faster (1:58 against 4:59), the
two 90s keypress stalls having been removed.

(A related wart, not fixed: the verdict cache keys on the answer hash, so the three
uptime-bearing prompts can never cache and are re-queued on every run.)

Steps 4-8 were spent chasing a kernel bug that did not exist. `reset_cache()`, the KV bounds,
`out_ids[40]` against a 40-token cap and the detokenizer bound were all read and are all
correct. The defect was in the measuring instrument.

## Acceptance

- [x] No corpus response teaches a PCI id absent from the bus; session `grounding` PASSES
- [x] A question with no device id is taught to get a clarification
- [x] `--manifest` produces measurably different corpora (187 / 443 / 561), `excludes` honoured
      with zero leaks on the artifact
- [x] In-scope and out-of-scope reported separately, against a control re-measured on the
      same harness
- [x] Hypothesis refuted in writing, every attempt recorded

## What this redirects

1. **Scoping is not a quality lever.** Keep `--manifest` — it is needed for image size and for
   not shipping false capability claims — but stop expecting a garbage-rate win from it.
2. **The 20% floor is the real target**, and it is over-refusal, not mis-routing. That is a
   retrieval problem: the rule engine should answer more, and the model should defer to it
   rather than decline.
3. **`excludes` must reach the kernel.** Until the manifest scopes the rule tables and role
   list, a "scoped image" is a general OS with a smaller model, and the out-of-scope collapse
   from 67% to 27% is the cost of that mismatch.
