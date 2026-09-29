# Decision (open, owner): how far to go on syscalls and seccomp

**Status: open.** Nothing is blocked by it: until it is answered, `observe.py` does **not**
record the `syscalls:` capability kind, and no seccomp profile is produced. Plan:
[`w19-app-observe`](../../../.claude/PRPs/plans/w19-app-observe.plan.md).

## Why this is a decision and not a task

A syscall allowlist is the most attractive part of "derive the minimum environment" and the
least tractable:

- **Static extraction is defeated** by indirect calls and by any interpreter. For a Python or
  Node application, reading the source says almost nothing about the syscalls the runtime makes.
- **Dynamic extraction is only as complete as the paths exercised.** A profile derived from one
  run kills the process on the first branch that run did not take.
- **An almost-right profile is an outage with a confusing error message.** `EPERM` from a
  `statx` on the error path of a rarely used feature does not name the profile as its cause.

That is a reliability and security trade-off with real users on the far side of it, which makes
it the owner's call rather than a default an agent picks.

## What is already true

- `observe.py` (A5) runs the subject under `strace`; recording syscall numbers costs nothing
  extra in collection. The decision is about what is *done* with them.
- Every observation states its exercise script and exit, so coverage is always reportable.
- Ablation (A9) can only test what the probe exercises, the same limit a profile would have.

## Options

| Option | Effect |
|---|---|
| **(a) None in v1** | The `syscalls:` kind stays out of the index. No profile, no claim |
| **(b) Report only** | `observe.py` records the observed syscall set with its coverage statement; the Packager never enforces it. Useful as evidence, harmless as output |
| **(c) Opt-in enforcement** | as (b), plus a seccomp profile the operator may enable per application, shipped with its coverage stated and **never** the default |
| **(d) Default enforcement** | not recommended; listed so its rejection is on record |

**Recommended default (not a decision):** (b) now, (c) once A9's ablation has been run on three
applications and its false-"not needed" rate is known. The PRD's own words: opt-in, reported
with its coverage, never the default.

## Verdict

*(empty — the owner writes the decision and its reasoning here)*
