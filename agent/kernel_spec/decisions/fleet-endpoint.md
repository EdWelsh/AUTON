# Decision (open, owner): where a fleet conformance report could go

**Status: open, and nothing is blocked by it.** The report format, the consent flow and the
local aggregator exist (`agent/tools/fleet_report.py`). What does not exist, and will not be
assumed, is somewhere to send a report.

## Why this is a decision and not a task

Mercurial cores appear at roughly one machine in a thousand
(`agent/hardware/CONFORMANCE-HARDWARE.md`), so detecting them needs a fleet, and this project
does not have one. Deployments could supply the scale. But collecting results means **moving
data off a user's machine**, and that is not an engineering default — it is a commitment to:

- **a recipient**: who operates the endpoint, under what terms, and what happens to the data if
  that party stops existing;
- **a retention answer**: how long a report is kept, and whether a user can withdraw one after
  the fact (with an anonymous report, usually they cannot, which is a reason to say so up front);
- **a jurisdiction**: where the data lands;
- **an abuse story**: an endpoint accepting anonymous reports can be filled with fabricated
  divergences, so aggregate claims need a story for that before they are published.

None of those is answerable by looking at the code, which is why the tool has no endpoint and
no network call at all.

## What is already true, and testable

- The report schema is an **allowlist** (`ALLOWED` in `fleet_report.py`). A field nobody
  considered cannot ride along, and names that hint at identity — MAC, hostname, IP, serial,
  UUID, user — are refused with a reason.
- Reports are grouped by `family:model:stepping`. A report that cannot be grouped by part is
  refused rather than sent.
- **Virtualised reports never count toward a flag.** A divergence under a hypervisor is the
  hypervisor's; those reports are counted separately and reported as such.
- `--show` prints exactly what would be sent and sends nothing. The consent prompt defaults to
  **no**, and the user sees the report before answering.

## How this gets answered

The owner decides whether to operate an endpoint and on what terms, and the answer is written
here. Until then AUTON's fleet story is: the results stay on the machine, and the aggregator
runs locally over reports a person collected deliberately.
