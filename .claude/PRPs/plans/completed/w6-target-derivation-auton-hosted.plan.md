# Plan: Derive an AUTON-Hosted Target (D2)

**Source PRD**: `auton-hardware-definition.prd.md` — phase D2
**Depends on**: D1, intent-F (packaging, landed)
**Why it matters more than it looks**: if the host presents virtio, the guest needs about four
drivers rather than 21,564

## Summary

The recursive case — *"hosted on its own version of k8s that another kernel team built and
deployed"*. An AUTON-built host is the one target that is **perfectly knowable**, because it was
built from a manifest and its provenance was written down.

This derives a guest's target definition from the host image's `PROVENANCE.json`, with no
elicitation and no probing.

## Evidence

- `agent/tools/package_image.py` writes `PROVENANCE.json` carrying `artifacts`, `spec_sections`
  (each with `included_because`), `leakage`, `assumptions` and hashes — verified on a real
  package in `reports/w4-intent-packaging.md`.
- **The gap this plan must close first**: that record carries the *capability slice* and **not**
  the target's devices or silicon. Packaging never recorded what it built *for*, because until
  D1 there was no format to record it in. So D2 is two steps: teach packaging to write the
  target, then read it back.
- `agent/tools/capability_slice.py` — a host image's `spec_sections` name its subsystems, from
  which what it *presents* to a guest is derivable.
- `SLM/tools/build_corpus.py` `DRIVER_CAPS` — `virtio-net` → `{net}`, `virtio-blk` → `{fs}`.
  A host presenting virtio implies exactly which guest capabilities are reachable.

## Tasks

### Task 1: Packaging records its target
- **Action**: `package_image.py` writes the target definition into `PROVENANCE.json` and into
  `spec/target.md`. Today it records what the image is *for* and not what it runs *on*.
- **Why here**: D2 cannot derive from a record that was never written. This is the smaller half
  and it must land first.
- **Validate**: a packaged image carries a valid target under D1; an image built without one
  says so rather than omitting the field.

### Task 2: Host image to guest target
- **Action**: `target_spec.py --derive-hosted <host-package-dir>` reads the host's provenance and
  emits a guest target: `class: auton-hosted`, devices from what the host presents,
  `source: derived`, and the host's image hash as provenance.
- **Critical**: the guest target must record **which host image** it was derived from, by hash.
  A host rebuilt with different capabilities presents a different machine, and a guest built
  against the old one is building for hardware that no longer exists.
- **Validate**: deriving from the DHCP package produces a target naming the host image's hash;
  changing the host image changes the derived target.

### Task 3: The honest limit
- **Action**: A host that presents no virtio — because its manifest excluded `net` or `fs` —
  yields a guest target with correspondingly nothing. Report that plainly rather than emitting a
  default device set.
- **Why**: a Doom-shaped host has no network. A guest derived from it cannot have one either,
  and inventing one would produce an image that cannot boot on the only host it was built for.
- **Validate**: deriving from a no-network host yields a target with no network device and an
  explicit statement of why.

### Task 4: Errata inheritance, asked not answered
- **Action**: Record the open question in the target: a guest on defective silicon is affected by
  defects the host does not mitigate. H8 answers per-machine; this is per-stack.
- **Why recorded rather than solved**: the PRD lists it as open question 4, and guessing an
  answer here would put a confident wrong claim into a safety report.
- **Validate**: a derived target carries the host's silicon identity where the host recorded one,
  marked `source: derived`, and `UNKNOWN` where it did not — never absent.

## Validation

```bash
python agent/tools/package_image.py "hand out addresses" --output /tmp/host --service dhcp
python agent/tools/target_spec.py --derive-hosted /tmp/host > /tmp/guest.md
python agent/tools/target_spec.py --validate /tmp/guest.md
grep -q "$(sha256 of host image)" /tmp/guest.md      # provenance by hash
cd agent && python -m pytest tests/unit/test_target_derivation.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Derived guest drifts from a rebuilt host | **H** | Task 2 records the host image hash; a mismatch is detectable and must be |
| The recursion is treated as a novelty | **M** | It is the strategically correct default: a virtio-only guest needs four drivers, not 21,564. Worth stating in the report |
| Packaging grows a field nobody reads | **L** | D7 and the driver PRD both consume it; if neither did, the field should not exist |
| Errata inheritance quietly assumed safe | **M** | Task 4 records UNKNOWN rather than absent, per H8's rule that unknown is never folded into safe |

## Acceptance
- [ ] Packaging records the target it built for; an image without one says so
- [ ] A guest target derives from a host package with no questions asked
- [ ] The derived target names the host image by hash, and a rebuilt host is detectable
- [ ] A host presenting nothing yields a guest with nothing, stated plainly
- [ ] Host silicon is carried as `derived`, or `UNKNOWN` — never absent
