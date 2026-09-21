"""Parse and validate a target definition — what an image will run on.

A capability manifest says what an image is *for*. This says what it runs *on*,
and until it existed the answer was a hardcoded literal: `BUS_DEVICES` in
`SLM/tools/build_corpus.py` is QEMU's default PC, and every corpus answer and
eval expectation was written against that one machine.

Two rules carry the weight.

**Every fact carries a `source`** — user-stated, probed, derived or assumed. A
decision made on an assumption must be reversible when the truth arrives, and
that is impossible if the record cannot say which facts were assumed. This is
`ident_source_t` from arch/hal.md, generalised from one machine to any target.

**An underspecified target is refused, never defaulted.** Silently becoming the
QEMU PC is how every image ends up built for a machine nobody owns.

    python agent/tools/target_spec.py --validate agent/kernel_spec/targets/firecracker.md
    python agent/tools/target_spec.py --identify 8086:100e
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ROOT / "agent" / "kernel_spec" / "targets"
sys.path.insert(0, str(Path(__file__).resolve().parent))

CLASSES = ("bare-metal", "vm", "microvm", "k8s-pod", "auton-hosted")
SOURCES = ("user-stated", "probed", "derived", "assumed")
FIRMWARE = ("uefi", "bios", "device-tree", "none")
# Two id forms, because a machine with no PCI bus cannot have PCI ids. Over
# virtio-MMIO the guest reads a device *type number* out of a register — there
# is no vendor:device pair anywhere in the transport. Writing `1af4:1000` for a
# Firecracker device names a bus that machine does not have.
PCI_ID = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{4}$")
MMIO_ID = re.compile(r"^virtio-mmio:([0-9]{1,3})$")
# A third form, for devices on no enumerable bus: a framebuffer handed over by
# the boot protocol, an i8042 at fixed ISA ports. Neither is enumerated and
# neither is in any registry, so a driver record naming one had no writable id
# at all — the same gap `virtio-mmio:` closed for microVMs.
PLATFORM_ID = re.compile(r"^platform:([a-z0-9][a-z0-9-]{0,63})$")

REQUIRED = ("target", "class", "arch", "firmware", "silicon", "devices", "provenance")

# Something must pin the device set, or a driver decision has nothing to decide
# from. There are exactly two ways to pin it: enumerate the devices, or name a
# platform that fixes them. Each class uses one or the other, never neither.
#
# A Firecracker guest gets virtio-mmio and nothing else whatever anyone writes
# down — but only once the hypervisor and machine type are on record. Without
# them, an empty `devices` list is not "implied", it is blank.
PLATFORM_IMPLIES_DEVICES = {
    "microvm": ("hypervisor", "machine"),
    "k8s-pod": ("runtime",),
    "auton-hosted": ("host_image",),
}

# How to supply a fact that is missing. A refusal that does not say this leaves
# the reader to guess which of the four sources is even available to them.
HOW_TO_SUPPLY = "probe the machine, state the fact, or derive it — and record which"
SILICON_FIELDS = ("vendor", "family", "model", "stepping", "source")


# Three states need three codes, and 2 is already spoken for: argparse exits 2
# on a usage error, so an unverifiable target sharing it would be
# indistinguishable from a mistyped flag in any script that checks $?.
EXIT_REFUSED = 1
EXIT_UNVERIFIABLE = 3


class TargetError(Exception):
    """Names the field. A target definition is the input to every driver
    decision, so a vague error here costs more than most."""


class Identification(str, Enum):
    """Three states, because two would lie.

    UNKNOWN means the registry was consulted and does not list the device —
    QEMU's Bochs VGA at 1234:1111 is genuinely present and genuinely absent from
    pci.ids. UNAVAILABLE means no registry was consulted at all. Collapsing them
    would report every device as unidentifiable on a fresh checkout.
    """
    IDENTIFIED = "identified"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Device:
    id: str
    role: str
    source: str


@dataclass
class Target:
    target: str
    klass: str
    arch: str
    firmware: str
    silicon: dict
    platform: dict = field(default_factory=dict)
    devices: list[Device] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    absent: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    path: Path | None = None

    @property
    def assumed_facts(self) -> list[str]:
        """Everything resting on a default. A caller that ignores this is
        making driver decisions on guesses without knowing it."""
        out = []
        if self.silicon.get("source") == "assumed":
            out.append("silicon")
        out += [f"device {d.id}" for d in self.devices if d.source == "assumed"]
        return out


def _front_matter(text: str, path: Path) -> dict:
    """The same hand-rolled subset used by service specs: `key: value`,
    `key: [a, b]`, `key:` followed by indented items. Not a YAML dependency,
    because agents read these files as plain text."""
    if not text.startswith("---\n"):
        raise TargetError(f"{path.name}: no front-matter block")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise TargetError(f"{path.name}: unterminated front-matter block")

    root: dict = {}
    stack: list[tuple[int, object]] = [(-1, root)]
    for raw in text[4:end].splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]
        body = raw.strip()

        if body.startswith("- "):
            item = body[2:].strip()
            if not isinstance(container, list):
                raise TargetError(f"{path.name}: list item {item!r} belongs to no field")
            if ":" in item and not item.startswith('"'):
                d: dict = {}
                k, _, v = item.partition(":")
                d[k.strip()] = v.strip().strip('"')
                container.append(d)
                stack.append((indent, d))
            else:
                container.append(item.strip('"'))
            continue

        key, sep, value = body.partition(":")
        if not sep:
            raise TargetError(f"{path.name}: cannot parse {raw!r}")
        key, value = key.strip(), value.strip().strip('"')
        if isinstance(container, dict):
            if value == "":
                child: object = [] if _expects_list(key) else {}
                container[key] = child
                stack.append((indent, child))
            else:
                container[key] = value
    return root


def _expects_list(key: str) -> bool:
    return key in ("devices", "assumptions", "absent")


def load(path: str | Path) -> Target:
    path = Path(path)
    if not path.exists():
        raise TargetError(f"{path}: no such target definition")
    data = _front_matter(path.read_text(encoding="utf-8"), path)

    missing = [f for f in REQUIRED if f not in data]
    if missing:
        raise TargetError(f"{path.name}: missing field(s): {', '.join(missing)}")
    if data["target"] != path.stem:
        raise TargetError(
            f"{path.name}: 'target' is {data['target']!r} but the file is "
            f"{path.stem!r}; they address the same thing")
    if data["class"] not in CLASSES:
        raise TargetError(
            f"{path.name}: class {data['class']!r} not one of {', '.join(CLASSES)}")
    if data["firmware"] not in FIRMWARE:
        raise TargetError(
            f"{path.name}: firmware {data['firmware']!r} not one of "
            f"{', '.join(FIRMWARE)}. A microVM with no firmware says 'none'")

    silicon = data["silicon"]
    if not isinstance(silicon, dict):
        raise TargetError(f"{path.name}: 'silicon' must be a mapping")
    sil_missing = [f for f in SILICON_FIELDS if f not in silicon]
    if sil_missing:
        raise TargetError(
            f"{path.name}: silicon is missing {', '.join(sil_missing)}. "
            f"'source' is required even when the value is unknown — an absent "
            f"source cannot be told apart from a confident one")
    if silicon["source"] not in SOURCES:
        raise TargetError(
            f"{path.name}: silicon source {silicon['source']!r} not one of "
            f"{', '.join(SOURCES)}")

    devices: list[Device] = []
    for entry in data.get("devices") or []:
        if not isinstance(entry, dict):
            raise TargetError(f"{path.name}: a device must be a mapping, got {entry!r}")
        for f in ("id", "role", "source"):
            if f not in entry:
                raise TargetError(
                    f"{path.name}: device {entry.get('id', '<no id>')!r} "
                    f"is missing {f!r}")
        did = entry["id"].lower()
        if not (PCI_ID.match(did) or MMIO_ID.match(did)
                or PLATFORM_ID.match(did)):
            raise TargetError(
                f"{path.name}: device id {entry['id']!r} is none of vvvv:dddd "
                f"(PCI), virtio-mmio:<type> (MMIO) or platform:<name> "
                f"(no enumerable bus)")
        if entry["source"] not in SOURCES:
            raise TargetError(
                f"{path.name}: device {entry['id']} source {entry['source']!r} "
                f"not one of {', '.join(SOURCES)}")
        devices.append(Device(entry["id"].lower(), entry["role"], entry["source"]))

    return Target(
        target=data["target"], klass=data["class"], arch=data["arch"],
        firmware=data["firmware"], silicon=silicon, devices=devices,
        platform=data.get("platform") or {},
        assumptions=list(data.get("assumptions") or []),
        absent=list(data.get("absent") or []),
        provenance=data.get("provenance") or {}, path=path,
    )


def _virtio_types() -> dict[int, str]:
    """The VIRTIO 1.2 device type numbers, from hypervisors.yaml.

    Checked in rather than ingested because no vendor document under .cache/
    covers it — the numbers are in the specification text itself. Weaker
    evidence than pci.ids, and the table says so in its header.
    """
    import yaml
    data = yaml.safe_load((TARGETS / "hypervisors.yaml").read_text())
    return {int(k): v for k, v in (data.get("virtio_device_types") or {}).items()}


def identify(device_id: str) -> tuple[Identification, str]:
    """Look a device up in the registry appropriate to its transport.

    Deterministic: a table lookup with provenance, never an inference. A model
    asked to name a device produces a plausible one, which is the phantom-id
    defect with a driver attached.
    """
    platform = PLATFORM_ID.match(device_id.lower())
    if platform:
        # Resolved against the platform table rather than a device registry:
        # these devices are in no registry by definition. An entry with no
        # `specified_by` is genuinely unidentifiable, which is a real answer and
        # not a lookup failure.
        import yaml
        table = yaml.safe_load(
            (TARGETS.parent / "drivers" / "platform-devices.yaml").read_text()
        ).get("devices") or {}
        entry = table.get(platform.group(1))
        if entry is None:
            return Identification.UNKNOWN, (
                f"no platform device {platform.group(1)!r} in "
                f"drivers/platform-devices.yaml")
        if not entry.get("specified_by"):
            return Identification.UNKNOWN, (
                f"{entry['title']} — no inventoried specification")
        return Identification.IDENTIFIED, (
            f"{entry['title']} [{entry['specified_by']}]")

    mmio = MMIO_ID.match(device_id.lower())
    if mmio:
        types = _virtio_types()
        n = int(mmio.group(1))
        if n in types:
            return Identification.IDENTIFIED, f"virtio {types[n]} [VIRTIO 1.2 §5]"
        return Identification.UNKNOWN, f"no VIRTIO 1.2 device type {n}"

    # Delegated rather than duplicated: device_registry.py owns the PCI lookup
    # and its provenance, and a second copy of that logic would drift from it.
    from device_registry import Outcome, identify as registry_identify

    ident = registry_identify(device_id)
    if ident.outcome is Outcome.IDENTIFIED:
        return Identification.IDENTIFIED, ident.describe()
    if ident.outcome is Outcome.UNAVAILABLE:
        return Identification.UNAVAILABLE, ident.reason
    return Identification.UNKNOWN, ident.reason


@dataclass
class Report:
    """What validation could and could not establish. `unverifiable` is not a
    softer kind of pass — the CLI exits non-zero on it, because a target whose
    devices were never checked against anything must not read as checked."""
    target: Target
    unlisted: list[str] = field(default_factory=list)
    unverifiable: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unverifiable


def _platform_pins_devices(platform: dict) -> str | None:
    """Return a reason string when the named platform does *not* fix a device
    set, or None when it does. Consulting the table keeps one source of truth:
    a hand-written target gets the same answer as a derived one."""
    try:
        table = hypervisor_table()
    except Exception:
        return None                       # no table: D6 cannot say, so it does not
    hv = (table.get("hypervisors") or {}).get(platform.get("hypervisor"))
    if hv is None:
        return (f"devices (no entry for hypervisor "
                f"{platform.get('hypervisor')!r} in hypervisors.yaml, so nothing "
                f"records which devices it implies)")
    conf = (hv.get("machines") or {}).get(platform.get("machine"))
    if conf is None:
        return (f"devices (no machine type {platform.get('machine')!r} for "
                f"{platform.get('hypervisor')!r} in hypervisors.yaml)")
    if conf.get("pins_devices", True):
        return None
    return (f"devices ({platform.get('hypervisor')}/{platform.get('machine')} "
            f"{conf.get('note', 'does not pin a device set')}; naming it does "
            f"not say what is attached)")


def missing_facts(t: Target) -> list[tuple[str, str]]:
    """What this definition still needs, as (field, reason) pairs.

    Split out of `check_completeness` so elicitation can ask about the same
    gaps this refuses on. A second list of questions would drift from this one,
    and the drift shows up as either asking for something the format does not
    need or failing to ask for something it does.
    """
    facts: list[tuple[str, str]] = []
    missing: list[str] = []
    pins = PLATFORM_IMPLIES_DEVICES.get(t.klass)

    if pins:
        # The platform is what makes an empty device list a fact instead of a
        # blank. Absent it, nothing has said which devices are implied.
        absent = [f for f in pins if not t.platform.get(f)]
        if not absent and not t.devices and t.klass == "microvm":
            # Naming a platform is not automatically enough. QEMU's `microvm`
            # machine type declares MMIO slots and says nothing about what
            # occupies them, so a target naming it and listing nothing is still
            # blank. The table is what knows the difference.
            why = _platform_pins_devices(t.platform)
            if why:
                missing.append(why)
        if absent:
            named = (f"platform.{absent[0]}" if len(absent) == 1
                     else "platform." + "{" + ",".join(absent) + "}")
            missing.append(
                f"{named} (class {t.klass!r} takes its device set from the "
                f"platform, so the platform must be named)")
    elif not t.devices:
        missing.append(
            f"devices (class {t.klass!r} implies none; every device must be listed)")

    if t.klass == "bare-metal":
        # Errata applicability is keyed on family/model/stepping (see
        # agent/tools/errata_table.py). On real silicon those are readable via
        # CPUID, so an assumption here is a guess nobody had to make.
        if t.silicon.get("source") == "assumed":
            missing.append("silicon (assumed on bare metal, where CPUID can be read)")
        if t.firmware == "none":
            missing.append("firmware (something must bring real hardware up)")

    for entry in missing:
        field_name, _, reason = entry.partition(" (")
        facts.append((field_name.strip(), reason.rstrip(")")))
    return facts


def check_completeness(t: Target) -> None:
    """Refuse a definition too thin to build against, naming what is missing.

    The alternative — quietly filling the gaps from the QEMU PC — is how an
    image ends up built for a machine nobody owns, and it leaves no trace that
    would let anyone notice.
    """
    facts = missing_facts(t)
    missing = [f"{f} ({why})" for f, why in facts]

    if missing:
        name = t.path.name if t.path else t.target
        raise TargetError(
            f"{name}: underspecified, missing: {'; '.join(missing)}. "
            f"To supply these, {HOW_TO_SUPPLY}. "
            f"Not defaulted — a target nobody stated is not the QEMU PC")


def check_devices(t: Target) -> Report:
    """Resolve every device against the registry.

    Absence from pci.ids refuses a device that only a person or an inference
    claims, and passes one the machine itself reported. `source: probed` is
    independent evidence — QEMU's Bochs VGA at 1234:1111 is genuinely present
    and genuinely absent from the registry. A device that is in neither the
    registry nor a probe is backed by nothing at all, which is the phantom-id
    defect with a driver attached.
    """
    report = Report(target=t)
    phantom: list[str] = []
    for d in t.devices:
        state, detail = identify(d.id)
        if state is Identification.IDENTIFIED:
            continue
        if state is Identification.UNAVAILABLE:
            report.unverifiable.append(d.id)
        elif d.source == "probed":
            report.unlisted.append(d.id)
        else:
            phantom.append(f"{d.id} ({d.role}, source {d.source}) — {detail}")

    if phantom:
        name = t.path.name if t.path else t.target
        raise TargetError(
            f"{name}: device(s) in no registry and never probed: "
            f"{'; '.join(phantom)}. Name a real device, or probe the machine "
            f"and record source: probed")
    return report


def validate(path: str | Path) -> Report:
    t = load(path)
    check_completeness(t)
    return check_devices(t)


# --- derivation ------------------------------------------------------------- #

HYPERVISORS = TARGETS / "hypervisors.yaml"


def hypervisor_table() -> dict:
    import yaml
    return yaml.safe_load(HYPERVISORS.read_text())


def derive_microvm(hypervisor: str, machine: str = "default") -> str:
    """Emit a complete target definition for a microVM, asking nothing.

    A microVM's device set is decided by the hypervisor and machine type before
    anything boots, so the two facts an operator already knows are enough. This
    is the PRD's hypothesis at its strongest: elicitation is the fallback, not
    the main road.

    Every emitted fact carries `source: derived`. Not `probed` — nothing was
    probed — and the distinction is what lets D4 later contradict this file.
    """
    table = hypervisor_table()
    entry = (table.get("hypervisors") or {}).get(hypervisor)
    if entry is None:
        known = ", ".join(sorted(table.get("hypervisors") or {}))
        raise TargetError(
            f"no hypervisor {hypervisor!r} in {HYPERVISORS.name}; known: {known}. "
            f"Add an entry with the version it describes — a derivation from a "
            f"hypervisor nobody wrote down would be a guess with a source field "
            f"claiming otherwise")
    conf = (entry.get("machines") or {}).get(machine)
    if conf is None:
        known = ", ".join(sorted(entry.get("machines") or {}))
        raise TargetError(
            f"no machine type {machine!r} for {hypervisor!r}; known: {known}")

    devices = conf.get("devices") or []
    if not devices and not conf.get("pins_devices", True):
        raise TargetError(
            f"{hypervisor}/{machine} {conf.get('note', 'pins no device set')}: "
            f"deriving would emit a target with no devices and no platform that "
            f"implies any. State what is attached, or probe a running instance")

    name = f"{hypervisor}-{machine}" if machine != "default" else hypervisor
    absent = conf.get("absent") or []

    lines = [
        "---",
        f"target: {name}",
        "class: microvm",
        "arch: x86_64",
        f"firmware: {conf['firmware']}",
        "silicon:",
        "  vendor: unknown",
        "  family: 0",
        "  model: 0",
        "  stepping: 0",
        "  source: assumed",
        "platform:",
        f"  hypervisor: {hypervisor}",
        f"  machine: {machine}",
        f"  transport: {conf['transport']}",
        f"  console: {conf['console']}",
        "  source: derived",
        "devices:",
    ]
    for d in devices:
        lines += [f'  - id: "{d["id"]}"', f'    role: {d["role"]}',
                  "    source: derived"]
    lines.append("assumptions:")
    # The one fact derivation genuinely cannot supply. A guest does not choose
    # its CPU and cannot read a truthful one out of the hypervisor's config, so
    # this stays assumed until D4 probes a running instance.
    lines.append('  - "silicon: a guest inherits the host CPU; the hypervisor '
                 'config does not state it"')
    if absent:
        # Not assumptions: an absence read off the machine type is as derived as
        # a presence, and it is the fact a driver decision turns on. A kernel
        # that enumerates PCI here finds nothing and concludes the machine has
        # no devices at all.
        lines.append("absent:")
        lines += [f'  - "{a}"' for a in absent]
    lines += [
        "provenance:",
        f"  stated_by: hypervisors.yaml:{hypervisor}/{machine}",
        f"  describes_version: \"{entry['describes_version']}\"",
        "---",
        "",
        f"# {name}",
        "",
        f"Derived from `hypervisors.yaml`, entry `{hypervisor}/{machine}` "
        f"(describes {entry['describes_version']}). No questions were asked: a "
        f"microVM's device set is decided by the hypervisor and machine type, "
        f"not discovered.",
        "",
        "Every fact here is `source: derived`. Nothing was probed, and a probe "
        "that contradicts this file is a finding about the table, not the "
        "machine — see `agent/kernel_spec/targets/hypervisors.yaml`.",
        "",
    ]
    if absent:
        lines += ["## What this machine does not have", ""]
        lines += [f"- {a}" for a in absent]
        lines.append("")
    for v in conf.get("vestigial") or []:
        lines += [f"Vestigial: {v}", ""]
    return "\n".join(lines)


# --- the recursive case ----------------------------------------------------- #

# What a host image can present to a guest, given a capability it holds. An
# AUTON host that has no network cannot offer a guest one, and inventing a
# device here would produce a guest image that cannot boot on the only host it
# was built for.
#
# Keyed on capability rather than on driver: `e1000` and `virtio-net` both
# provide `net`, and what the host presents downward is a virtio device either
# way — the guest never sees the host's own NIC.
HOST_PRESENTS = {
    "net":  ("virtio-mmio:1", "network"),
    "ipv4": ("virtio-mmio:1", "network"),
    "udp":  ("virtio-mmio:1", "network"),
    "tcp":  ("virtio-mmio:1", "network"),
    "fs":   ("virtio-mmio:2", "storage"),
}

# Recorded, not answered. The PRD lists it as open question 4: H8 decides errata
# applicability per machine, and a guest is a second machine on the same
# silicon. Guessing here would put a confident wrong claim into a safety report.
ERRATA_QUESTION = (
    "errata: a guest runs on the host's silicon, so it is affected by defects "
    "the host does not mitigate. Applicability is decided per machine (H8) and "
    "this is per stack — open, and not answered by this derivation"
)


def _host_image_hash(prov: dict) -> str | None:
    for a in prov.get("artifacts") or []:
        if a.get("path") == "image.iso":
            return a.get("sha256")
    return None


def derive_hosted(package_dir: str | Path) -> str:
    """Derive a guest target from an AUTON host image's provenance.

    The one target that is perfectly knowable: the host was built from a
    manifest and its provenance was written down, so nothing has to be probed
    or asked. If the host presents virtio, the guest needs about four drivers
    rather than the 21,564 devices in pci.ids — which makes this the
    strategically correct default, not a novelty.
    """
    import json

    package_dir = Path(package_dir)
    prov_path = package_dir / "PROVENANCE.json"
    if not prov_path.exists():
        raise TargetError(
            f"{package_dir}: no PROVENANCE.json — not an AUTON package. A guest "
            f"target is derived from what the host recorded about itself")
    prov = json.loads(prov_path.read_text())

    image_hash = _host_image_hash(prov)
    if image_hash is None:
        raise TargetError(
            f"{package_dir}: the host package has no image.iso"
            + (f" ({prov['blocked_by']})" if prov.get("blocked_by") else "")
            + ". A package that produced no image cannot host anything, and a "
              "guest target derived from it would name a host that does not exist")

    manifest_path = package_dir / "spec" / "manifest.json"
    if not manifest_path.exists():
        raise TargetError(f"{package_dir}: no spec/manifest.json to read the "
                          f"host's capabilities from")
    manifest = json.loads(manifest_path.read_text())
    requires = set(manifest.get("requires") or [])
    excludes = set(manifest.get("excludes") or [])

    devices: list[tuple[str, str]] = []
    for cap, (dev_id, role) in HOST_PRESENTS.items():
        if cap in requires and (dev_id, role) not in devices:
            devices.append((dev_id, role))

    # Task 3's honest limit, stated rather than defaulted.
    withheld = []
    for cap, (_, role) in HOST_PRESENTS.items():
        if cap in excludes and not any(r == role for _, r in devices):
            withheld.append(f"{role} — the host manifest excludes {cap!r}")

    host_target = prov.get("target") or {}
    if host_target.get("stated"):
        silicon = dict(host_target.get("silicon") or {})
        # Carried down one level, and never strengthened on the way. A fact the
        # host only assumed is still an assumption in the guest: relabelling it
        # `derived` because this file read it is how an assumption becomes a
        # fact by being copied, which is the defect the `source` field exists to
        # prevent. Deriving from an assumption yields an assumption.
        host_source = (host_target.get("silicon") or {}).get("source", "assumed")
        silicon["source"] = "assumed" if host_source == "assumed" else "derived"
        silicon_note = (f"silicon: inherited from host target "
                        f"{host_target.get('target')!r}, which recorded it as "
                        f"{host_source}; carried down without strengthening")
    else:
        # UNKNOWN, never absent. H8's rule: unknown is not folded into safe, and
        # an absent field cannot be told apart from one nobody looked at.
        silicon = {"vendor": "unknown", "family": "0", "model": "0",
                   "stepping": "0", "source": "assumed"}
        silicon_note = ("silicon: the host package states no target, so the "
                        "silicon under this guest is UNKNOWN — not assumed safe, "
                        "and not absent from this record")

    name = f"hosted-on-{image_hash[:12]}"
    lines = [
        "---",
        f"target: {name}",
        "class: auton-hosted",
        f"arch: {host_target.get('arch', 'x86_64')}",
        "firmware: none",
        "silicon:",
    ]
    lines += [f"  {k}: {v}" for k, v in silicon.items()]
    lines += [
        "platform:",
        f"  host_image: {image_hash}",
        f"  host_intent: {json.dumps(prov.get('intent', ''))}",
        f"  host_rule: {prov.get('matched_rule', '')}",
        "  source: derived",
        "devices:",
    ]
    for dev_id, role in devices:
        lines += [f'  - id: "{dev_id}"', f"    role: {role}", "    source: derived"]
    lines += ["assumptions:",
              f'  - "{silicon_note}"',
              f'  - "{ERRATA_QUESTION}"',
              '  - "presentation: AUTON implements no device model today, so this '
              'states what the host manifest permits, not what a running host offers"']
    if withheld:
        lines.append("absent:")
        lines += [f'  - "{w}"' for w in withheld]
    lines += [
        "provenance:",
        f"  stated_by: PROVENANCE.json:{image_hash[:12]}",
        f"  host_package: {package_dir.name}",
        "---",
        "",
        f"# Guest on AUTON image `{image_hash[:12]}`",
        "",
        f"Derived from a host package built for {prov.get('intent', '')!r} "
        f"(rule `{prov.get('matched_rule', '')}`). Nothing was probed and nothing "
        f"was asked: the host was built from a manifest and wrote down what it "
        f"is, which makes it the one target that is perfectly knowable.",
        "",
        "## Why the hash is in the platform block",
        "",
        "A host rebuilt with different capabilities presents a different machine. "
        "A guest built against the old one is building for hardware that no "
        "longer exists, and without the hash nothing would notice. "
        f"`{image_hash}`",
        "",
    ]
    if withheld:
        lines += ["## What this host cannot offer", ""]
        lines += [f"- {w}" for w in withheld]
        lines += ["",
                  "Stated rather than defaulted. A guest with an invented network "
                  "device would be an image that cannot boot on the only host it "
                  "was built for.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--validate", metavar="FILE")
    ap.add_argument("--identify", metavar="VVVV:DDDD")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--derive-microvm", nargs="+", metavar=("HYPERVISOR", "MACHINE"),
                    help="emit a target derived from hypervisors.yaml")
    ap.add_argument("--derive-hosted", metavar="PACKAGE_DIR",
                    help="emit a guest target derived from an AUTON host package")
    args = ap.parse_args(argv)

    if args.derive_microvm:
        hv, machine = (args.derive_microvm + ["default"])[:2]
        try:
            print(derive_microvm(hv, machine), end="")
        except TargetError as exc:
            print(f"INVALID: {exc}", file=sys.stderr)
            return EXIT_REFUSED
        return 0

    if args.derive_hosted:
        try:
            print(derive_hosted(args.derive_hosted), end="")
        except TargetError as exc:
            print(f"INVALID: {exc}", file=sys.stderr)
            return EXIT_REFUSED
        return 0

    if args.identify:
        state, detail = identify(args.identify)
        print(f"{args.identify}: {state.value} — {detail}")
        return 0 if state is Identification.IDENTIFIED else 1

    paths = (sorted(p for p in TARGETS.glob("*.md") if p.name != "README.md")
             if args.all else [Path(args.validate)] if args.validate else [])
    if not paths:
        ap.error("give --validate FILE, --identify ID, or --all")

    rc = 0
    for p in paths:
        try:
            r = validate(p)
        except TargetError as exc:
            print(f"INVALID: {exc}", file=sys.stderr)
            rc = max(rc, EXIT_REFUSED)
            continue

        t = r.target
        status = "OK" if r.ok else "UNVERIFIED"
        print(f"{status} {p.name}: {t.klass}/{t.arch}, {len(t.devices)} device(s), "
              f"firmware {t.firmware}")
        if t.assumed_facts:
            print(f"   assumed: {', '.join(t.assumed_facts)}")
        if r.unlisted:
            print(f"   probed but not in pci.ids: {', '.join(r.unlisted)} "
                  f"(present on the machine, absent from the registry)")
        if r.unverifiable:
            print(f"   unverifiable: {', '.join(r.unverifiable)} — no registry "
                  f"cached, so nothing confirms or denies these ids",
                  file=sys.stderr)
            rc = max(rc, EXIT_UNVERIFIABLE)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
