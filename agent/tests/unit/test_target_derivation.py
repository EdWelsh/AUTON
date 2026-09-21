"""Deriving a microVM target from the hypervisor table.

The PRD's hypothesis is that elicitation is a fallback rather than the main
road. A microVM is where that claim is strongest: its device set is not
discovered, it is *decided* by the hypervisor and machine type before anything
boots. So these tests are largely about proving the derivation asks nothing and
still produces something D6 accepts — and about the one entry where naming the
platform is not enough.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from target_spec import (  # noqa: E402
    HYPERVISORS,
    Identification,
    TargetError,
    derive_microvm,
    hypervisor_table,
    identify,
    load,
    validate,
)

TARGETS = ROOT / "agent" / "kernel_spec" / "targets"


@pytest.fixture
def derived(tmp_path):
    """Emit a derived target to a file named so `target` matches — the format
    requires the two to agree, and the derivation names itself."""
    def _derive(hypervisor, machine="default"):
        text = derive_microvm(hypervisor, machine)
        name = next(l.split(":", 1)[1].strip()
                    for l in text.splitlines() if l.startswith("target:"))
        path = tmp_path / f"{name}.md"
        path.write_text(text)
        return path
    return _derive


# --- the table --------------------------------------------------------------- #

def test_every_entry_records_the_version_it_describes():
    """A hypervisor's device set changes between releases. An entry that does
    not say which release it describes cannot be found stale."""
    table = hypervisor_table()
    for name, entry in table["hypervisors"].items():
        assert entry.get("describes_version"), f"{name} describes no version"
        assert entry.get("reference"), f"{name} cites no source"


def test_every_machine_states_what_is_absent():
    """Absence is the fact a driver decision turns on: a kernel that enumerates
    PCI on a Firecracker guest finds nothing and concludes, wrongly, that the
    machine has no devices."""
    for name, entry in hypervisor_table()["hypervisors"].items():
        for m, conf in entry["machines"].items():
            assert conf.get("absent"), f"{name}/{m} lists no absences"


def test_the_table_is_not_shaped_around_one_hypervisor():
    """Cloud Hypervisor is a microVM *with* a PCI bus. If absence were a
    property of the class rather than of the entry, its row could not exist."""
    transports = {
        conf["transport"]
        for e in hypervisor_table()["hypervisors"].values()
        for conf in e["machines"].values()
    }
    assert transports == {"virtio-mmio", "virtio-pci"}


# --- derivation asks nothing ------------------------------------------------- #

def test_firecracker_derives_a_valid_target(derived):
    """The measurement behind the PRD's hypothesis: zero questions, and the
    result passes D6."""
    report = validate(derived("firecracker"))
    assert report.target.klass == "microvm"
    assert len(report.target.devices) == 2


def test_every_derived_fact_says_it_was_derived(derived):
    t = load(derived("firecracker"))
    assert {d.source for d in t.devices} == {"derived"}
    assert t.platform["source"] == "derived"


def test_nothing_derived_claims_to_have_been_probed(derived):
    """`probed` is the one source a derivation must never write. It is what
    lets D4 later contradict this file without the contradiction being a
    disagreement between two observations."""
    for hv in ("firecracker", "cloud-hypervisor"):
        text = derive_microvm(hv)
        assert "source: probed" not in text


def test_assumptions_hold_only_the_fact_derivation_cannot_supply(derived):
    """Task 3's bar: empty, or every entry justified. Exactly one survives —
    a guest does not choose its CPU, and the hypervisor config does not state
    it."""
    t = load(derived("firecracker"))
    assert len(t.assumptions) == 1
    assert t.assumptions[0].startswith("silicon:")
    assert t.silicon["source"] == "assumed"


def test_absences_are_not_filed_as_assumptions(derived):
    """An absence read off the machine type is as derived as a presence.
    Filing it under `assumptions` would mark a known fact as a guess."""
    t = load(derived("firecracker"))
    assert any("PCI bus" in a for a in t.absent)
    assert not any("PCI bus" in a for a in t.assumptions)


def test_provenance_cites_the_table_entry_and_its_version(derived):
    t = load(derived("firecracker"))
    assert t.provenance["stated_by"] == "hypervisors.yaml:firecracker/default"
    assert t.provenance["describes_version"]


def test_derivation_is_deterministic():
    """No timestamp, no ordering wobble. A round-trip against the hand-written
    control is only meaningful if re-running changes nothing."""
    assert derive_microvm("firecracker") == derive_microvm("firecracker")


# --- ids follow the transport ------------------------------------------------ #

def test_mmio_devices_do_not_carry_pci_ids(derived):
    """Firecracker has no PCI bus. `1af4:1000` is virtio's PCI pair, and writing
    it here names a bus the machine does not have — the defect this phase found
    in the hand-written control."""
    t = load(derived("firecracker"))
    for d in t.devices:
        assert d.id.startswith("virtio-mmio:")


def test_pci_transport_derives_pci_ids(derived):
    t = load(derived("cloud-hypervisor"))
    for d in t.devices:
        assert ":" in d.id and not d.id.startswith("virtio-mmio:")


def test_mmio_ids_resolve_against_the_virtio_type_table():
    """There is no pci.ids entry to find, and that is not a failure to
    identify — it is a different registry."""
    state, detail = identify("virtio-mmio:1")
    assert state is Identification.IDENTIFIED
    assert "network" in detail


def test_an_undefined_virtio_type_is_unknown_not_identified():
    state, _ = identify("virtio-mmio:99")
    assert state is Identification.UNKNOWN


# --- naming a platform is not always enough ---------------------------------- #

def test_a_machine_that_pins_no_devices_refuses_to_derive():
    """QEMU's `microvm` declares MMIO slots and says nothing about what occupies
    them. D6's rule assumed every platform implies its devices; this is the
    entry that showed the assumption was wrong."""
    with pytest.raises(TargetError, match="slots, not occupants"):
        derive_microvm("qemu-microvm")


def test_a_hand_written_target_gets_the_same_answer(tmp_path):
    """One source of truth. A hand-written target naming the same machine must
    be refused for the same reason a derived one would be."""
    path = tmp_path / "qm.md"
    path.write_text("""---
target: qm
class: microvm
arch: x86_64
firmware: none
silicon:
  vendor: unknown
  family: 0
  model: 0
  stepping: 0
  source: assumed
platform:
  hypervisor: qemu-microvm
  machine: default
  source: user-stated
devices:
provenance:
  stated_by: test
---
""")
    with pytest.raises(TargetError, match="slots, not occupants"):
        validate(path)


def test_an_unknown_hypervisor_is_refused_by_name():
    with pytest.raises(TargetError, match="known: cloud-hypervisor"):
        derive_microvm("xen")


def test_an_unknown_machine_type_is_refused_by_name():
    with pytest.raises(TargetError, match="no machine type"):
        derive_microvm("firecracker", "jailer")


# --- round-trip against the hand-written control ----------------------------- #

def test_derived_and_hand_written_agree_on_every_fact_about_the_machine():
    """`firecracker.md` was written by hand before the derivation existed and is
    kept as the control. The two may differ on provenance — who says so and how
    they know — but a disagreement about the hardware means one of them is
    wrong.
    """
    control = load(TARGETS / "firecracker.md")
    text = derive_microvm("firecracker")
    emitted = yaml.safe_load(text.split("---")[1])

    assert control.klass == emitted["class"]
    assert control.firmware == emitted["firmware"]
    assert control.platform["hypervisor"] == emitted["platform"]["hypervisor"]
    assert control.platform["machine"] == emitted["platform"]["machine"]
    assert control.platform["transport"] == emitted["platform"]["transport"]
    assert control.platform["console"] == emitted["platform"]["console"]
    assert ([(d.id, d.role) for d in control.devices]
            == [(d["id"], d["role"]) for d in emitted["devices"]])
    assert control.absent == emitted["absent"]


def test_the_control_and_the_derivation_differ_only_on_provenance():
    """The differences that remain are the point of `source`: the same value,
    two ways of knowing it."""
    control = load(TARGETS / "firecracker.md")
    assert control.platform["source"] == "user-stated"
    assert yaml.safe_load(
        derive_microvm("firecracker").split("---")[1]
    )["platform"]["source"] == "derived"


# --- the recursive case: a guest on an AUTON host ---------------------------- #

import hashlib  # noqa: E402
import json  # noqa: E402

from target_spec import derive_hosted  # noqa: E402


@pytest.fixture
def host_package(tmp_path):
    """An AUTON host package as `package_image.py` writes one.

    Constructed rather than built: no host ISO can be produced in this tree
    (`kernels/` was removed, and `serve-dhcp` has no service spec, so a real
    DHCP package is INCOMPLETE and carries no image.iso). The shape matches what
    packaging writes — `PROVENANCE.json` with an `image.iso` artifact and its
    sha256, plus `spec/manifest.json`.
    """
    def _make(intent, target=None, body=b"stand-in ISO", name="host"):
        sys.path.insert(0, str(ROOT / "agent" / "tools"))
        from intent_manifest import build

        d = tmp_path / name
        (d / "spec").mkdir(parents=True, exist_ok=True)
        m = build(intent)
        (d / "spec" / "manifest.json").write_text(m.to_json() + "\n")
        iso = d / "image.iso"
        iso.write_bytes(body)
        prov = {
            "intent": intent, "matched_rule": m.matched, "complete": True,
            "blocked_by": "",
            "target": target or {"stated": False, "why": "no target was stated"},
            "artifacts": [{
                "path": "image.iso", "produced_by": "build_service.py",
                "from_input": intent,
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body), "implements": "the bootable image"}],
        }
        (d / "PROVENANCE.json").write_text(json.dumps(prov, indent=2))
        return d
    return _make


@pytest.fixture
def hosted(tmp_path):
    def _derive(package_dir):
        text = derive_hosted(package_dir)
        name = next(l.split(":", 1)[1].strip()
                    for l in text.splitlines() if l.startswith("target:"))
        path = tmp_path / f"{name}.md"
        path.write_text(text)
        return path
    return _derive


STATED_TARGET = {
    "stated": True, "target": "firecracker", "class": "microvm",
    "arch": "x86_64", "firmware": "none",
    "silicon": {"vendor": "GenuineIntel", "family": "6", "model": "142",
                "stepping": "10", "source": "probed"},
}


def test_a_guest_derives_from_a_host_with_no_questions(host_package, hosted):
    """The one target that is perfectly knowable: the host was built from a
    manifest and wrote down what it is."""
    report = validate(hosted(host_package("hand out addresses")))
    assert report.target.klass == "auton-hosted"


def test_the_guest_names_the_host_image_by_hash(host_package, hosted):
    d = host_package("hand out addresses", body=b"iso-a")
    t = load(hosted(d))
    assert t.platform["host_image"] == hashlib.sha256(b"iso-a").hexdigest()


def test_a_rebuilt_host_produces_a_different_guest_target(host_package):
    """A host rebuilt with different capabilities presents a different machine.
    A guest built against the old one is building for hardware that no longer
    exists, and without the hash nothing would notice."""
    a = derive_hosted(host_package("hand out addresses", body=b"iso-a", name="a"))
    b = derive_hosted(host_package("hand out addresses", body=b"iso-b", name="b"))
    assert a != b


def test_a_network_host_presents_a_network_device(host_package, hosted):
    t = load(hosted(host_package("hand out addresses")))
    assert [(d.id, d.role) for d in t.devices] == [("virtio-mmio:1", "network")]


def test_a_host_presenting_nothing_yields_a_guest_with_nothing(host_package, hosted):
    """Task 3's honest limit. A Doom host excludes `net` and `fs`, so a guest on
    it has neither — and inventing one would produce an image that cannot boot
    on the only host it was built for."""
    t = load(hosted(host_package("I want to play Doom")))
    assert t.devices == []
    assert any("network" in a for a in t.absent)
    assert any("storage" in a for a in t.absent)


def test_the_absence_says_which_capability_was_excluded(host_package, hosted):
    t = load(hosted(host_package("I want to play Doom")))
    assert any("'net'" in a for a in t.absent)


def test_a_package_with_no_image_cannot_host_anything(host_package):
    """An INCOMPLETE package produced no image. A guest target derived from it
    would name a host that does not exist."""
    d = host_package("hand out addresses")
    prov = json.loads((d / "PROVENANCE.json").read_text())
    prov["artifacts"] = []
    prov["blocked_by"] = "no service spec for 'serve-dhcp'"
    (d / "PROVENANCE.json").write_text(json.dumps(prov))
    with pytest.raises(TargetError, match="no image.iso"):
        derive_hosted(d)


def test_a_directory_that_is_not_a_package_is_refused(tmp_path):
    with pytest.raises(TargetError, match="not an AUTON package"):
        derive_hosted(tmp_path)


# --- Task 4: errata inheritance, asked not answered -------------------------- #

def test_host_silicon_is_carried_down(host_package, hosted):
    t = load(hosted(host_package("hand out addresses", target=STATED_TARGET)))
    assert t.silicon["vendor"] == "GenuineIntel"
    assert t.silicon["model"] == "142"


def test_a_probed_host_fact_becomes_derived_in_the_guest(host_package, hosted):
    t = load(hosted(host_package("hand out addresses", target=STATED_TARGET)))
    assert t.silicon["source"] == "derived"


def test_an_assumed_host_fact_stays_assumed_in_the_guest(host_package, hosted):
    """Deriving from an assumption yields an assumption. Relabelling it
    `derived` because this file read it is how a guess becomes a fact by being
    copied — exactly what `source` exists to prevent."""
    weak = dict(STATED_TARGET,
                silicon=dict(STATED_TARGET["silicon"], source="assumed"))
    t = load(hosted(host_package("hand out addresses", target=weak)))
    assert t.silicon["source"] == "assumed"


def test_silicon_is_unknown_never_absent_when_the_host_stated_none(host_package, hosted):
    """H8's rule: unknown is not folded into safe, and an absent field cannot be
    told apart from one nobody looked at."""
    t = load(hosted(host_package("hand out addresses")))
    assert t.silicon["source"] == "assumed"
    assert t.silicon["vendor"] == "unknown"
    assert any("UNKNOWN" in a for a in t.assumptions)


def test_errata_inheritance_is_recorded_as_open(host_package, hosted):
    """Recorded rather than solved. The PRD lists it as open question 4, and
    guessing an answer would put a confident wrong claim into a safety report."""
    t = load(hosted(host_package("hand out addresses", target=STATED_TARGET)))
    errata = [a for a in t.assumptions if a.startswith("errata:")]
    assert len(errata) == 1
    assert "open" in errata[0]


def test_the_guest_says_no_device_model_exists_yet(host_package, hosted):
    """AUTON implements no hypervisor today. A target claiming a running host
    offers these devices would be stating something untrue."""
    t = load(hosted(host_package("hand out addresses")))
    assert any("no device model" in a for a in t.assumptions)
