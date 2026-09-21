# Target Definitions

**This is not a kernel, and it is not a manifest.** A capability manifest says what an image is
*for*. A target definition says what it will *run on*.

Until now the target was implicit: QEMU's idealised PC, hardcoded. `BUS_DEVICES` in
`SLM/tools/build_corpus.py` is a literal — `8086:1237 8086:7000 1234:1111 8086:100e` — and every
corpus answer, rule-engine fact and eval expectation was written against that one machine. That
is tolerable with one target and is the binding constraint at two.

## Shape

```yaml
---
target: firecracker-default
class: microvm               # bare-metal | vm | microvm | k8s-pod | auton-hosted
arch: x86_64
firmware: none               # uefi | bios | device-tree | none
silicon:
  vendor: GenuineIntel
  family: 6
  model: 85
  stepping: 4
  source: derived
devices:
  - id: "1af4:1000"
    role: network
    source: derived
assumptions:
  - "input: assuming serial console; no framebuffer stated"
provenance:
  stated_by: hypervisor-table
  stated_at: 2026-09-16T10:00:00Z
---
```

## Why each field exists

| Field | Why |
|---|---|
| `target` | Its identity; must match the filename, as service specs do |
| `class` | Five classes present different devices and different trust. A bare-metal NIC and a virtio NIC are not the same decision |
| `arch` | Selects the HAL and the build template |
| `firmware` | `uefi`/`bios`/`device-tree`/`none` decides how the machine is discovered at all. A microVM often has none |
| `silicon` | The errata join key from `arch/hal.md` category 8 — family/model/stepping |
| `devices` | What a driver decision is made per. Ids are checked against the ingested `pci.ids` |
| `assumptions` | Defaults that were applied, recorded rather than silent — the discipline `intent_manifest.py` already uses |
| `provenance` | Who said so and when |

## `source` is mandatory, per fact

Every silicon field and every device carries one of:

| `source` | Means |
|---|---|
| `user-stated` | A person said so. Trust it, record it, and let a later probe contradict it |
| `probed` | Read from the running machine |
| `derived` | Computed from something known — a hypervisor table, or a host image's provenance |
| `assumed` | A default was applied. **The weakest, and the one that must be visible** |

This is `ident_source_t` from `arch/hal.md` generalised from one machine to any target. The
reason is the same: a decision made on an assumption must be reversible when the truth arrives,
and that is impossible if the record cannot say which facts were assumed.

## Rules

1. **An underspecified target is refused, never defaulted.** Silently becoming the QEMU PC is how
   every image ends up built for a machine nobody owns.
2. **A device id names its transport.** `vvvv:dddd` is a PCI pair; `virtio-mmio:<type>` is a
   VIRTIO device type number (1 network, 2 block — VIRTIO 1.2 §5). A machine with no PCI bus
   cannot have PCI ids, and a format admitting only one shape does not merely fail to express
   the other: it makes the wrong answer the only writable one. That is how `firecracker.md`
   shipped with `1af4:1000` on a machine its own table says has no PCI bus.
3. **A device id is checked against the registry for its transport, and `source: probed`
   outranks it.**
   `ffff:ffff` claimed by a person is refused by name; QEMU's Bochs VGA at `1234:1111` is
   accepted, because the machine itself reported it and vendor `1234` is an id QEMU invented.
   A device backed by neither the registry nor a probe is backed by nothing — that is the
   phantom-id defect with a driver attached. The registry is evidence, not the arbiter of
   what exists.
4. **A missing registry makes identification *unavailable*, not devices *valid*.** Three states,
   the same distinction `run_leakage_test.sh` draws between "nothing to check" and "clean".
5. **Something must pin the device set — an enumeration, or a platform that fixes one.**
   `bare-metal` and `vm` enumerate: nothing is implied there, so silence means nobody looked.
   `microvm`, `k8s-pod` and `auton-hosted` may leave `devices` empty, but only once the platform
   is named — `platform.hypervisor` + `platform.machine`, `platform.runtime`, or
   `platform.host_image`. Without it an empty list is not implied, it is blank. A definition too
   thin either way is refused with every missing fact named in one run, and with how to supply
   them: probe the machine, state the fact, or derive it — and record which. Whether a platform
   pins anything is itself a fact in [hypervisors.yaml](hypervisors.yaml): QEMU's `microvm`
   declares MMIO slots and says nothing about what occupies them, so naming it is not enough.
6. **Absence is a field, not a remark.** `absent:` holds what the machine does not have. A target
   that can only list what is present cannot say "there is no PCI bus here", which is exactly the
   fact a driver decision turns on — a kernel that enumerates PCI on a Firecracker guest finds
   nothing and concludes the machine has no devices. An absence read off a machine type is as
   derived as a presence, so it does not belong under `assumptions`.
7. **A target is per-image, not global.** There is one capability index and many targets.

## Exit codes

`target_spec.py --validate` has three outcomes, and they are three codes because collapsing any
two loses the distinction the format exists for.

| Code | Outcome | Meaning |
|---|---|---|
| 0 | valid | Checked, and nothing was wrong |
| 1 | refused | A fact is missing, or a device is backed by nothing |
| 3 | unverifiable | The registry was never consulted — this is **not** a pass |

2 is skipped deliberately: `argparse` exits 2 on a usage error, so an unverifiable target sharing
it would be indistinguishable from a mistyped flag in any script that reads `$?`.

## Deriving instead of asking

A microVM's device set is not discovered, it is *decided* — Firecracker with a given machine type
has exactly the devices that machine type declares, before anything boots. So it is derived from
[hypervisors.yaml](hypervisors.yaml) and asks nothing:

```bash
python agent/tools/target_spec.py --derive-microvm firecracker > targets/firecracker.md
```

Every emitted fact carries `source: derived` — never `probed`, because nothing was probed. That
distinction is what lets a later probe contradict the file without the contradiction being a
disagreement between two observations. A probe that disagrees with a derived target is a finding
about the table.

The table is transcribed from hypervisor documentation, not ingested from a vendor document under
`.cache/`. That makes it weaker evidence than a `pci.ids` lookup, and it says so in its own
header.

## Probing a machine you have

Bare metal is the class where nothing is decided and nothing can be derived, so the only honest
source is the machine itself:

```bash
lspci -nn | python agent/tools/probe_ingest.py --lspci - --name my-laptop
python agent/tools/probe_ingest.py --lspci lspci.txt --cpuinfo cpuinfo.txt \
    --dmidecode dmi.txt --name my-laptop > targets/my-laptop.md
```

**This is the only tool that may write `source: probed`.** A derivation is forbidden from it by
test, and that guarantee is worthless from the other direction if the probe stamps `probed` on
anything it inferred.

Three things it deliberately will not do:

- **It does not keep the names `lspci` prints.** Those come from the *host's* `pci.ids`, which may
  be a different revision from the ingested one; capturing them would put an unattributed second
  source of truth into the record. Ids and class codes only, names looked up here.
- **It does not keep serial numbers, UUIDs or asset tags.** `dmidecode` reports all three, none is
  needed to build an image, and a target definition is a file that gets committed. They are
  stripped at parse time and the omission is recorded, so it reads as deliberate.
- **It does not guess the machine class.** A manufacturer it does not recognise is not evidence of
  bare metal — it may be a hypervisor the table has not seen. `class` is left unset and the
  definition is refused naming it.

Partial input yields a partial target. `lspci` alone gives real devices and no firmware, which is
a better record than a guessed firmware, and it is refused naming `class`, `firmware` and
`silicon`.

## The recursive case

A guest hosted on an AUTON image is the one target that is **perfectly knowable**: the host was
built from a manifest and its provenance was written down, so nothing has to be probed or asked.

```bash
python agent/tools/package_image.py "hand out addresses" --output host \
    --target agent/kernel_spec/targets/firecracker.md
python agent/tools/target_spec.py --derive-hosted host > guest.md
```

The guest names its host **by hash**. A host rebuilt with different capabilities presents a
different machine, and a guest built against the old one is building for hardware that no longer
exists — without the hash nothing would notice.

A host presents only what it has. A Doom host excludes `net` and `fs`, so a guest on it gets
neither, stated in `absent:` with the capability named. Inventing a device there would produce an
image that cannot boot on the only host it was built for.

**Deriving from an assumption yields an assumption.** Host silicon is carried down without being
strengthened: a fact the host recorded as `assumed` stays `assumed` in the guest. Relabelling it
`derived` because the derivation read it is how a guess becomes a fact by being copied. Where the
host stated no target at all, silicon is UNKNOWN — recorded, never absent.

If the host presents virtio, a guest needs about four drivers rather than the 21,564 devices in
`pci.ids`. That makes this the strategically correct default, not a novelty.

## Asking, when nothing else answers

The last resort, and the measurement of whether the rest worked:

```bash
python agent/tools/elicit.py --name my-box          # one question at a time
python agent/tools/elicit.py --measure              # the hypothesis, as a table
```

| Path | Questions |
|---|---|
| microVM, derived from `hypervisors.yaml` | **0** |
| AUTON-hosted, derived from `PROVENANCE.json` | **0** |
| VM, probed with `lspci`/`cpuinfo`/`dmidecode` | **0** |
| microVM, elicited | 5 |
| VM or bare metal, elicited with a probe | 4 |
| bare metal, elicited, probe refused | 5 |

Questions come from `target_spec.missing_facts` — the same list the validator refuses on, so the
two cannot drift. The cheaper path is offered before any device question: a tool that asks twelve
device questions when one `lspci -nn` paste would do has made the form the product.

**A kernel cannot run inside a container.** A container shares the host's kernel — that is what a
container is. Saying "docker", "k8s" or "pod" produces a question, never a guess: a microVM the
runtime schedules, or an OCI image shipping the ISO as an artifact. One reading yields an
unbootable image and the other a useless one, and nobody can tell which they got until it fails.

**"I don't know" is an answer.** A declined question leaves the fact unstated and the target
refused naming it, rather than filled with a plausible default. Declining the *class* ends the
conversation, because every remaining question is per-class. `unknown` for silicon is different —
that is a statement, the same one D3 makes for a microVM guest, and it is recorded as
`source: assumed`.

## Targets

| Target | Class | Exercises |
|---|---|---|
| [qemu-pc.md](qemu-pc.md) | `vm` | Emulated legacy PC: PCI bus, many devices, real ids |
| [firecracker.md](firecracker.md) | `microvm` | virtio-over-MMIO, **no PCI bus at all**, minimal set |

The two are deliberately far apart. A format proven against one class has not been tested, and
the microVM example was written second without adding a field.
