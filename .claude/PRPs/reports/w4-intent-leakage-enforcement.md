# Report: Leakage Enforcement (intent-E)

**Plan**: `.claude/PRPs/plans/w4-intent-leakage-enforcement.plan.md`
**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase E

F5 wired leakage as a gate. This makes it a **measurement**, makes an empty `excludes` a
failure, and — most of the value — pins the detector against a case it is known to catch.

## Leakage is a number now

```json
{ "excludes": ["tcp", "fs"], "image_symbols": 97, "leaked_symbols": 0,
  "absence_stubs": ["tcp_input"], "conclusive": true }
```

The PRD tracks leakage with a target of 0. A pass/fail cannot be tracked, and `--report` writes
the measurement per build into `build-<service>/leakage.json`.

`conclusive` is the field that matters. A run that could not compile a source has not checked
it, and recording that as 0 would put a false zero into a series someone reads as progress.

## An empty `excludes` is a failure

*"`excludes` is mandatory in every manifest — without it 'minimal' is unfalsifiable"* is in the
PRD's constraints table. It is now enforced: a spec with no excludes is refused with that
reason, rather than passing a check that had nothing to verify.

## The regression fixture

The detector reports 0 when it works and 0 when it has stopped working. So the general image —
which leaks the network when `net` is excluded — is a fixture the check must still catch.

It fires: exit 1, 30 leaked symbols, attributed to `kernel/net/`.

**30, not the 68 first measured.** That count included file-local statics, and attribution
deliberately stopped covering them after `seg.0` — a static in `netif.c` — was reported as TCP
leaking into an image that does not contain TCP. 30 globals is the honest number, and the test
records why it changed so the next reader does not treat it as a regression.

## Three defects this work surfaced

All three were found by writing the tests, not by the tests passing.

**A service build permanently poisoned every later general build.** `gen_absent.py` wrote
`absent.c` into `kernel/boot/`, and the Makefile globs `kernel` for sources — so the general
build compiled stubs for `slm_neural_available` alongside the real implementation and died on
`multiple definition`, until someone deleted a file they did not know existed. Generated output
now goes to `build-<service>/generated/`.

**Objects were shared between configurations.** `CFLAGS` is not a prerequisite of any object
rule, so `make` reused `setup.c.o` compiled without `-DNET_STATIC_IP` — linking a service image
whose network path still called `dhcp_run`. This is the same class as the `make iso-neural`
defect already recorded in this repo: the build system cannot express "this object was compiled
with different flags". Each service now builds into its own directory, so no object is ever
shared and both stay incremental.

**Build output was being treated as source.** `_tree_sources` globbed the whole tree, so
`build-dhcp/generated/absent.c` appeared as an unclaimed source — and would eventually have been
compiled back into the next image. Build directories are now excluded.

Verified: general 214,592 bytes, DHCP 53,056 bytes, and a general build after a service build
is byte-identical to one before it.

## Acceptance

- [x] Leakage is reported as a number, not only pass/fail
- [x] A manifest with no excludes is refused, with the PRD's own reason
- [x] The known leak is a regression fixture the detector must still catch
- [~] **Every manifest-built image is gated, not only services** — the service path is gated.
      There is no other manifest-built image path yet: intent-F (packaging) is where a
      non-service image gets built, and it has not been written
- 7 tests

## Follow-on

- The leakage measurement should be collected across builds rather than overwritten per build,
  so the PRD's number has a series behind it.
- `conclusive: false` has never been observed. It should be, deliberately, before it is trusted.
