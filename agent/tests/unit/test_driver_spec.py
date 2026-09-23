"""Driver decision records: how a driver came to exist, and how anyone knows it works.

A target says a device is present. The capability index says whether the tree
can drive it. Neither says where the driver came from or what checking it means,
and a driver that cannot say how its claim was checked is an assertion — the
most expensive kind to be wrong about when it is about hardware.

The bar the format has to clear is the one D1 set: two structurally different
records, the second written without adding a field.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from driver_spec import (  # noqa: E402
    REQUIRED,
    DriverError,
    load,
    validate,
)
from target_spec import Identification, identify  # noqa: E402

DRIVERS = ROOT / "agent" / "kernel_spec" / "drivers"

BASE = {
    "driver": "widget",
    "devices": '["8086:100e"]',
    "provides": "[net]",
    "strategy": "synthesize",
    "specification": '"VIRTIO 1.2 §5.1"',
    "verification": '["marker: [W] up"]',
    "status": "specified",
}


@pytest.fixture
def record(tmp_path):
    def _write(name="widget", drop=(), **overrides):
        fields = dict(BASE, driver=name)
        fields.update(overrides)
        for k in drop:
            fields.pop(k, None)
        lines = ["---"] + [f"{k}: {v}" for k, v in fields.items()] + \
                ["---", "", f"# {name}", ""]
        path = tmp_path / f"{name}.md"
        path.write_text("\n".join(lines))
        return path
    return _write


class TestTheShippedRecords:
    def test_both_validate(self):
        for name in ("virtio-net", "e1000"):
            assert validate(DRIVERS / f"{name}.md").record.driver == name

    def test_they_differ_on_every_axis_the_format_expresses(self):
        """A format proven against one record has not been tested. These two
        differ on strategy, status, id count, transport count, and which of
        `source`/`specification` carries their basis."""
        vn = load(DRIVERS / "virtio-net.md")
        e1 = load(DRIVERS / "e1000.md")

        assert vn.strategy != e1.strategy
        assert vn.status != e1.status
        assert len(vn.devices) != len(e1.devices)
        assert bool(vn.specification) != bool(e1.specification)
        assert bool(vn.source) != bool(e1.source)

    def test_the_second_record_added_no_field(self):
        """D1's bar: `firecracker.md` was written second and needed nothing new.
        If `e1000.md` needs a key `virtio-net.md` does not have beyond its
        strategy's own requirement, the first record taught the wrong shape."""
        import driver_spec

        vn_keys = set(REQUIRED) | {"specification"}
        e1_keys = set(REQUIRED) | {"source"}

        assert vn_keys - {"specification"} == e1_keys - {"source"}
        assert set(driver_spec.STRATEGY_REQUIRES.values()) == {"source", "specification"}

    def test_virtio_net_covers_both_transports(self):
        """One driver, three ways of being found. A format admitting only
        `vvvv:dddd` could not express `virtio-mmio:1` — the transport every
        microVM uses, and the one AUTON most needs."""
        vn = load(DRIVERS / "virtio-net.md")

        assert any(d.startswith("virtio-mmio:") for d in vn.devices)
        assert any(":" in d and not d.startswith("virtio-mmio:") for d in vn.devices)

    def test_virtio_net_is_specified_not_implemented(self):
        """D7 measured why this record exists: `drivers.md` provides exactly one
        network driver, so a Firecracker target cannot be built for at all."""
        assert load(DRIVERS / "virtio-net.md").status == "specified"

    def test_the_unimplemented_record_is_reported_not_refused(self, monkeypatch):
        """A record for a driver that does not exist yet is the point of having
        records. Refusing it would make the format unusable for planning."""
        # Pin identification: .cache/vendor/ is gitignored, so on a fresh clone
        # every device id is UNAVAILABLE and r.ok is False for a reason that has
        # nothing to do with what this test asserts. The subject here is that an
        # unmapped capability is *reported*, not refused.
        import driver_spec

        monkeypatch.setattr(
            driver_spec, "identify",
            lambda _id: (Identification.IDENTIFIED, "pinned for this test"))

        r = driver_spec.validate(DRIVERS / "virtio-net.md")

        assert r.unmapped == ["net"]
        assert r.ok


class TestRefusalsNameTheField:
    @pytest.mark.parametrize("field_name", REQUIRED)
    def test_every_required_field_is_named_when_missing(self, record, field_name):
        with pytest.raises(DriverError, match=field_name):
            load(record(drop=(field_name,)))

    def test_filename_and_driver_must_agree(self, record):
        path = record(name="widget")
        path.write_text(path.read_text().replace("driver: widget", "driver: gadget"))

        with pytest.raises(DriverError, match="they address the same thing"):
            load(path)

    def test_an_unknown_strategy_is_refused(self, record):
        with pytest.raises(DriverError, match="strategy 'vibes'"):
            load(record(strategy="vibes"))

    def test_an_unknown_status_is_refused(self, record):
        with pytest.raises(DriverError, match="status 'nearly'"):
            load(record(status="nearly"))

    def test_a_driver_with_no_device_is_refused(self, record):
        with pytest.raises(DriverError, match="is a library"):
            load(record(devices="[]"))

    def test_a_malformed_device_id_is_refused(self, record):
        with pytest.raises(DriverError, match="none of vvvv:dddd"):
            load(record(devices='["8086-100e"]'))

    @pytest.mark.parametrize("device_id", [
        "8086:100e", "virtio-mmio:1", "platform:i8042"])
    def test_all_three_id_forms_are_admitted(self, record, device_id):
        """The grammar grew twice, each time because a real driver could not be
        written without it: `virtio-mmio:` for a machine with no PCI bus,
        `platform:` for a device on no enumerable bus at all."""
        assert load(record(devices=f'["{device_id}"]')).devices == [device_id]


class TestTheBasisIsMandatoryForItsStrategy:
    def test_synthesize_without_a_citation_is_refused(self, record):
        """"Synthesized" without a citation means "written from memory", which
        is the phantom-device defect with a register map attached."""
        with pytest.raises(DriverError, match="written from memory"):
            load(record(drop=("specification",)))

    @pytest.mark.parametrize("strategy", ["port", "reuse"])
    def test_a_ported_driver_without_a_source_is_refused(self, record, strategy):
        """A ported driver with an unrecorded licence is a legal defect that
        surfaces at distribution, long after anyone can answer it cheaply."""
        with pytest.raises(DriverError, match="licence"):
            load(record(strategy=strategy, drop=("specification",)))

    def test_the_shipped_port_record_names_its_licence_position(self):
        e1 = load(DRIVERS / "e1000.md")
        assert "no code was copied" in e1.source


class TestVerificationIsMechanical:
    def test_prose_is_refused(self, record):
        """An image that claims a driver works is making the claim a user acts
        on. A description of how one might check is not a check."""
        with pytest.raises(DriverError, match="is prose"):
            load(record(verification='["check that it works"]'))

    def test_an_empty_verification_is_refused(self, record):
        with pytest.raises(DriverError, match="verification"):
            load(record(verification="[]"))

    def test_a_command_is_accepted(self, record):
        assert load(record(verification='["cmd: scripts/x.sh"]')).verification

    def test_it_is_required_even_when_only_specified(self, record):
        """A field allowed to be empty until implementation stays empty
        afterwards — the mitigations registry already refuses that trade."""
        with pytest.raises(DriverError):
            load(record(status="specified", verification="[]"))


class TestDeviceIdsMustResolve:
    def test_a_device_in_no_registry_is_refused(self, record):
        """Unlike a target, a record cannot appeal to `source: probed` — there
        is no machine here to have observed anything."""
        if identify("8086:100e")[0] is Identification.UNAVAILABLE:
            pytest.skip("pci.ids not cached")

        with pytest.raises(DriverError, match="ffff:ffff"):
            validate(record(devices='["ffff:ffff"]'))

    def test_the_refusal_says_why_probed_is_not_available(self, record):
        if identify("8086:100e")[0] is Identification.UNAVAILABLE:
            pytest.skip("pci.ids not cached")

        with pytest.raises(DriverError, match="no machine here"):
            validate(record(devices='["ffff:ffff"]'))

    def test_an_mmio_id_resolves_against_the_virtio_table(self, record):
        assert validate(record(devices='["virtio-mmio:1"]')).ok

    def test_a_missing_registry_is_unverifiable_not_valid(self, record, monkeypatch):
        import driver_spec

        monkeypatch.setattr(
            driver_spec, "identify",
            lambda _id: (Identification.UNAVAILABLE, "no registry"))

        r = driver_spec.check_devices(load(record()))

        assert r.unverifiable == ["8086:100e"]
        assert not r.ok


class TestStatusIsAClaimAboutThisTree:
    def test_implemented_without_a_source_mapping_is_refused(self, record):
        """That combination says the driver is in an image that does not contain
        it — the same false claim `[gate: capabilities]` refuses one level down."""
        with pytest.raises(DriverError, match="does not contain it"):
            validate(record(status="implemented", provides="[vfs]"))

    def test_specified_without_a_source_mapping_is_reported(self, record, monkeypatch):
        # Pin identification: .cache/vendor/ is gitignored, so on a fresh clone
        # every device id is UNAVAILABLE and r.ok is False for a reason that has
        # nothing to do with what this test asserts. The subject here is that an
        # unmapped capability is *reported*, not refused.
        import driver_spec

        monkeypatch.setattr(
            driver_spec, "identify",
            lambda _id: (Identification.IDENTIFIED, "pinned for this test"))

        r = driver_spec.validate(record(status="specified", provides="[vfs]"))

        assert r.unmapped == ["vfs"]
        assert r.ok

    def test_the_shipped_implemented_record_has_its_mapping(self):
        assert validate(DRIVERS / "e1000.md").unmapped == []


class TestTheFormatDoesNotCarryWhatGitOwns:
    @pytest.mark.parametrize("field_name", ["author", "date", "version", "updated"])
    def test_no_shipped_record_carries_a_field_git_already_owns(self, field_name):
        """A field git already owns goes stale in the file while staying correct
        in the history."""
        for p in DRIVERS.glob("*.md"):
            if p.name == "README.md":
                continue
            front = p.read_text().split("\n---\n")[0]
            assert f"{field_name}:" not in front, p.name
