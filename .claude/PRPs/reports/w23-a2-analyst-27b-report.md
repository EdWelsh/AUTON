# w23 A2: the fixture Analyst on `qwen3.5:27b-coding-mxfp8`. Result: passed

**Pre-registration:** [w23-a2-analyst-27b-preregistration.md](w23-a2-analyst-27b-preregistration.md).
**Run:** `.artifacts/w23-a2/`, one iteration, about 5 minutes of work (analyst 22:26–22:30, reviewer to 22:35).

## Verdict

A record merged: `analysis/flask-hello.artifact.yaml`, 5 facts, **valid with every quote verified
against the subject** (`artifact_spec.py --validate --subject`). The reviewer model read it and
approved. The model was refused twice by its own `check_record` and corrected itself; no phantom
capability reached the reviewer.

| Fact | Source | Right? |
|---|---|---|
| `runtime:python-3.12` | declared, `Dockerfile:1` | yes |
| `pypi:flask` | declared, `requirements.txt:1` | yes, and it used the C1 kind that run 4 on the 9b could not |
| `listen:tcp/8000` | declared, `Dockerfile:6` | yes (recorded as an assumption, never observed) |
| `env:GREETING` | inferred, `app.py:5` | yes |
| `lib:libssl.so.3`, `lib:libcrypto.so.3` | inferred, `app.py:2` | yes: `import ssl`. The 9b missed this |

## Against the predictions

- Right on runtime and port, refused at most twice: **held** (twice).
- At least one over-claim a reviewer should catch: **did not hold.** None. The "needed because the
  base has it" pattern of 9b run 4 did not appear.

## Consequence

**C2 (an Analyst prompt change) is not justified by this record** and is not made. The 9b's
failures were a capability gap, not a prompt defect. One fixture is one data point; A3 (the three
real subjects) is what decides whether the model can analyse.
