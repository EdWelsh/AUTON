# Implementation Report: Device + Errata Table Merge (H13)

**Plan**: `plans/completed/w13-hardware-table-merge.plan.md`

## Summary

The errata verdicts now ship in the image as `assets/errata.bin`, a boot module beside the
model, keyed by silicon identity and binary-searched in place. The device table stays in the
model file where w10 put it.

## Decisions

- **A separate module, not a model-file section** (the PRD's Open Question 3). Errata change on
  a vendor's schedule, and a module is replaced without retraining; `auton_format.VERSION` is
  untouched. Recorded in `slm.md` "Errata Module (REQUIRED)".
- **Verdicts are precomputed, not re-derived.** `errata_table.applies` (processor lines;
  "Plan Fix" is UNKNOWN without microcode) runs on the host for each CPUID signature a document
  covers. A second implementation in C would drift from it.
- **The vendor is part of the key.** Intel's and AMD's family/model spaces overlap; a test pins
  that Intel 25/33 is not AMD 25/33.

## Results

| Check | Result |
|---|---|
| Real module from Intel 682436 | 4 identities × 94 verdicts, 11,465 bytes; 66–68 apply per identity |
| C reader (`run_errata_lookup_test.sh`) | 11/11; **every** truncation of the module refused under ASan |
| Python format tests | 12/12 (round trip, sorting, shared text stored once, truncation, target scoping) |
| Package | `assets/errata.bin` in every targeted package; `qemu-pc`'s silicon is not covered → a valid 57-byte module meaning "not examined" |

## Deviations

- The plan placed the format in `auton_format.py`. It lives in `SLM/tools/errata_format.py`,
  because it is not part of the model file, which is the point of the decision above.
- `package_image.py` ships the module but the kernel-side loader is **specified and host-proved,
  not generated**. It joins the w13+ generation work with the rest of `slm.md`.
