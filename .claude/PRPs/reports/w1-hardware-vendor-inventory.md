# Report: Vendor Inventory (H1)

**Plan**: `.claude/PRPs/plans/w1-hardware-vendor-inventory.plan.md`
**Source PRD**: `auton-hardware-truth.prd.md` — phase H1

## What exists now

`agent/hardware/vendors.yaml` — **28 vendors, 43 documents**, machine-readable. The PRD's
landscape was prose and unqueryable; it is now data with a validator, a coverage report, and a
fetch planner that refuses to break the licence.

No network activity. H0 gates fetching, and pointing agents at externally fetched documents
while they hold a shell is the combination that turns a vendor PDF into code execution.

## The schema survived four shapes

Designed against **Intel** first, deliberately: four document kinds on four cadences in three
forms. A schema built around RISC-V's single open spec would have broken immediately.

| Shape | Why it stresses the schema |
|---|---|
| Intel | SDM, per-family Specification Updates, security advisories, microcode revision guidance — four kinds, four cadences |
| Arm | Keyed per *core revision* (`implementer/part_num/variant/revision`), not per family, because the same core ships in many vendors' SoCs |
| RISC-V | Open ISA (CC-BY, source form), and **no central errata document at all** — defects belong to implementations |
| PCI-SIG | Base spec membership-gated while the `pci.ids` registry is public — one vendor, two access levels |

No field was added for any of them. A test asserts the four carry identical field sets.

`identity_keys` is required on every vendor, and the reason is load-bearing: without it an
erratum matches a *vendor*, not a *running machine*. For x86 that key is CPUID leaf 1's
family/model/stepping, already documented at `arch/x86_64.md:1624` — the join column exists,
which is what makes conformance checking tractable at all.

## Gaps are records, not omissions

The validator rejects a vendor with neither documents nor stated gaps. Silence reads as
coverage, and a report that quietly omitted Apple would say AUTON covers the field.

- **Apple** — no public silicon specs of any kind; Asahi Linux's reverse-engineering notes are
  the de-facto reference, recorded as third-party provenance, which can never carry a vendor
  document's confidence.
- **Qualcomm** — largely closed, partner NDA only.
- **MIPI** — membership for everything, which matters for display and camera on every ARM SoC.
- Six more publish documents but no errata: IBM/OpenPOWER, Loongson, NVIDIA, Broadcom/RPi,
  Rockchip, Allwinner.

7 of 28 vendors publish errata documents. That number is the real ceiling on hardware-truth
coverage, and it is now visible rather than implied.

## The licensing rule is enforced, not advised

Most silicon specs are freely downloadable and not freely redistributable. Only 8 of 43
documents here may be republished.

```
$ vendor_inventory.py --fetch-plan intel --into agent/hardware/docs
INVALID: refusing to plan a fetch into 'agent/hardware/docs': it is tracked, and
4 of intel's documents are not redistributable (intel-sdm, intel-spec-update,
intel-sa). Ingest and derive; never vendor the source.
```

The check is on the destination rather than on intent — a repo full of vendor PDFs is a
licensing problem whoever added them meant well — and it resolves the path rather than matching
a prefix, so `.cache/vendor/../../agent/hardware` is caught too. RISC-V's CC-BY specs may
target a tracked path, because the rule is about the licence, not caution in general.

Two schema rules exist purely to stop an accident: `redistributable` must be an explicit
boolean (`"probably"` is how a violation gets committed), and setting it true requires naming
the licence.

`.cache/` is now gitignored, and a test asserts against `git ls-files` that no PDF is tracked.

## A bug the tests found

`is_tracked_path` resolved relative destinations against the **current working directory**, so
`.cache/vendor` became `agent/.cache/vendor` when run from `agent/` — flagged as tracked, and
just as capable of mis-classifying the other way. It now resolves against the repo root, so a
destination means the same place wherever the tool is run from. Verified from both directories.

That is exactly the class of error this plan's refusal is meant to prevent, found in the
refusal itself.

## Acceptance

- [x] Every vendor from the PRD landscape inventoried, negatives included
- [x] The schema expresses Intel, Arm, RISC-V and a standards body without new fields
- [x] `redistributable: false` documents cannot be targeted at a tracked path
- [x] Coverage report separates inventoried from ingested — 28 and **0**
- [x] No vendor document committed (asserted against `git ls-files`)
- 39 tests

## Follow-on

- H2 (Intel + AMD) and H3 (Arm + RISC-V) do the ingestion. Both are gated on H0, which has now
  landed — `w0-agent-shell-hardening` closed the injection and confined the shell tool.
- Cheapest first targets, in order: `arm-sysreg-xml` (the only vendor-published machine-readable
  register description here — no PDF parsing at all), RISC-V's source-form specs, and the
  `pci.ids`/`usb.ids` registries. Intel's Specification Updates are the hardest and the most
  valuable, which is why the PRD scoped H2 to them.
- Intel's errata are monthly. A list six months stale is worse than none, because it reads as
  current.
