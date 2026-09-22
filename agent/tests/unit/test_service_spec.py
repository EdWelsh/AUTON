"""Service spec format: validation and resolution.

A service spec is the factory's input. The failure that costs most is a spec
that validates but means something other than what it says, because it is
discovered after a kernel has been generated from it. So every check here is
about failing loudly and naming the field.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from service_spec import (  # noqa: E402
    ServiceSpecError,
    load,
    load_all,
)

SERVICES = ROOT / "agent" / "kernel_spec" / "services"


@pytest.fixture
def spec_file(tmp_path):
    """Write a service spec with fields overridden, named so `service` matches."""
    def _write(name="widget", **overrides):
        fields = {
            "service": name,
            "requires": "[udp, allocator]",
            "excludes": "[tcp]",
            "entry": "widget_serve",
            "markers": '["[WIDGET] up"]',
            "assets": "[]",
        }
        fields.update(overrides)
        lines = ["---"]
        for k, v in fields.items():
            if v is not None:
                lines.append(f"{k}: {v}")
        lines += ["---", "", "# Widget", "", "Prose."]
        p = tmp_path / f"{name}.md"
        p.write_text("\n".join(lines))
        return p
    return _write


class TestTheShippedSpecs:
    def test_every_service_spec_validates_and_resolves(self):
        specs = load_all()

        assert set(specs) == {"dhcp", "fileserver", "play-doom", "ssh", "tftp"}
        for spec in specs.values():
            spec.resolve()

    def test_dhcp_resolves_without_tcp_or_a_filesystem(self):
        sl = load(SERVICES / "dhcp.md").resolve()

        assert "fs" not in sl.subsystems
        assert "tcp" not in sl.capabilities
        assert "udp" in sl.capabilities

    def test_a_service_can_exclude_one_capability_of_a_subsystem_it_needs(self):
        """The reason the index is per-capability. The file server needs `fs`
        for `vfs` and `initramfs` while excluding `writable` and `ext2` from
        the same spec — a per-subsystem index could not express that."""
        sl = load(SERVICES / "fileserver.md").resolve()

        assert "fs" in sl.subsystems
        assert "vfs" in sl.capabilities
        assert "initramfs" in sl.capabilities
        assert "writable" not in sl.capabilities
        assert "ext2" not in sl.capabilities

    def test_the_two_services_are_structurally_different(self):
        """A format that expresses only the service it was written alongside
        has not been tested."""
        dhcp = load(SERVICES / "dhcp.md")
        fs = load(SERVICES / "fileserver.md")

        assert "tcp" in fs.requires and "tcp" in dhcp.excludes
        assert fs.assets and not dhcp.assets
        assert set(dhcp.resolve().subsystems) != set(fs.resolve().subsystems)

    def test_neither_service_needed_a_field_the_other_lacks(self):
        """Task 1's actual bar: two shapes, no new fields."""
        dhcp = load(SERVICES / "dhcp.md")
        fs = load(SERVICES / "fileserver.md")

        assert set(vars(dhcp)) == set(vars(fs))


class TestMalformedSpecsAreRejected:
    @pytest.mark.parametrize("field", ["service", "requires", "entry", "markers", "assets"])
    def test_a_missing_field_is_named(self, spec_file, field):
        with pytest.raises(ServiceSpecError, match=field):
            load(spec_file(**{field: None}))

    def test_no_front_matter_is_rejected(self, tmp_path):
        p = tmp_path / "bare.md"
        p.write_text("# Just prose\n")
        with pytest.raises(ServiceSpecError, match="no front-matter"):
            load(p)

    def test_an_unterminated_block_is_rejected(self, tmp_path):
        p = tmp_path / "open.md"
        p.write_text("---\nservice: open\nrequires: [udp]\n")
        with pytest.raises(ServiceSpecError, match="unterminated"):
            load(p)

    def test_a_filename_mismatch_is_rejected(self, spec_file):
        """The filename is how the factory addresses a service. A mismatch means
        a build would act on the wrong one."""
        p = spec_file(name="widget", service="gadget")
        with pytest.raises(ServiceSpecError, match="must agree|address the same"):
            load(p)

    def test_empty_requires_is_rejected(self, spec_file):
        with pytest.raises(ServiceSpecError, match="requires"):
            load(spec_file(requires="[]"))

    def test_empty_markers_are_rejected(self, spec_file):
        """Without markers the spine has nothing to assert, so the image cannot
        be verified — a spec that ships none is not finished."""
        with pytest.raises(ServiceSpecError, match="markers"):
            load(spec_file(markers="[]"))

    def test_a_scalar_where_a_list_belongs_is_rejected(self, spec_file):
        with pytest.raises(ServiceSpecError, match="must be a list"):
            load(spec_file(requires="udp"))

    def test_a_missing_file_is_reported(self, tmp_path):
        with pytest.raises(ServiceSpecError, match="no such service spec"):
            load(tmp_path / "absent.md")


class TestCapabilitiesAreCheckedAgainstTheIndex:
    def test_an_unknown_required_capability_is_rejected(self, spec_file):
        """Otherwise `requires` is decoration — it would name something no
        subsystem provides and still validate."""
        with pytest.raises(ServiceSpecError, match="unknown capabilities"):
            load(spec_file(requires="[udp, telepathy]"))

    def test_an_unknown_excluded_capability_is_rejected(self, spec_file):
        with pytest.raises(ServiceSpecError, match="unknown capabilities"):
            load(spec_file(excludes="[teleportation]"))

    def test_the_offending_field_is_named(self, spec_file):
        with pytest.raises(ServiceSpecError) as exc:
            load(spec_file(excludes="[teleportation]"))

        assert "'excludes'" in str(exc.value)
        assert "teleportation" in str(exc.value)

    def test_the_same_capability_required_and_excluded_is_rejected(self, spec_file):
        with pytest.raises(ServiceSpecError, match="both 'requires' and 'excludes'"):
            load(spec_file(requires="[udp, tcp]", excludes="[tcp]"))


class TestResolutionRefusals:
    def test_a_conflicting_spec_is_refused_with_the_path(self, spec_file):
        """`tcp` needs `mm`; excluding `mm` makes the spec impossible, and the
        path is what tells an author which line to change."""
        spec = load(spec_file(requires="[tcp]", excludes="[mm]"))

        with pytest.raises(ServiceSpecError) as exc:
            spec.resolve()

        message = str(exc.value)
        assert "excluded" in message
        assert "net" in message and "mm" in message

    def test_a_refusal_names_the_spec_file(self, spec_file):
        spec = load(spec_file(requires="[tcp]", excludes="[mm]"))

        with pytest.raises(ServiceSpecError, match="widget.md"):
            spec.resolve()

    def test_list_form_markers_parse(self, tmp_path):
        """Both `markers: [a, b]` and the block form must work — dhcp.md uses
        the block form and the round trip is what the spine depends on."""
        p = tmp_path / "blocky.md"
        p.write_text(
            "---\nservice: blocky\nrequires: [udp]\nexcludes: []\n"
            "entry: blocky_serve\nmarkers:\n  - \"[A] one\"\n  - \"[B] two\"\n"
            "assets: []\n---\n\n# Blocky\n"
        )
        spec = load(p)

        assert spec.markers == ("[A] one", "[B] two")
