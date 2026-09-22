"""Closed-slice computation over the spec capability index.

The property that matters is not that a slice is produced — it is that an
impossible one is *refused*. A manifest whose requires transitively pull in
something its excludes forbid is self-contradictory, and an OS builder that
notices only after generating a kernel has noticed too late.

The second property is that nothing fails quietly. An unknown capability
yielding an empty slice would look exactly like a correctly minimal image.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from capability_slice import (  # noqa: E402
    Spec,
    build_owner_index,
    SliceError,
    capability_slice,
    load_specs,
)


def _spec(name, provides, depends_on=(), optional=()):
    return Spec(name=name, provides=tuple(provides), depends_on=tuple(depends_on),
                optional=tuple(optional), path=Path(f"/synthetic/{name}.md"))


@pytest.fixture
def toy() -> dict[str, Spec]:
    """A small graph with the shapes that matter: a chain, a shared leaf, an
    optional capability, and a subsystem nothing depends on."""
    return {
        "hal": _spec("hal", ["arch"]),
        "mm": _spec("mm", ["allocator", "pool"], ["hal"], optional=["pool"]),
        "dev": _spec("dev", ["pci"], ["mm"]),
        "net": _spec("net", ["ipv4", "tcp"], ["mm", "dev"], optional=["tcp"]),
        "video": _spec("video", ["framebuffer"], ["mm", "dev"]),
    }


class TestClosure:
    def test_a_slice_contains_every_transitive_dependency(self, toy):
        s = capability_slice(["framebuffer"], specs=toy)

        assert set(s.subsystems) == {"video", "dev", "mm", "hal"}

    def test_a_slice_omits_what_nothing_requires(self, toy):
        s = capability_slice(["framebuffer"], specs=toy)

        assert "net" not in s.subsystems

    def test_requiring_a_subsystem_by_name_works_like_a_capability(self, toy):
        by_cap = capability_slice(["ipv4"], specs=toy)
        by_name = capability_slice(["net"], specs=toy)

        assert by_cap.subsystems == by_name.subsystems

    def test_optional_capabilities_ship_only_when_asked_for(self, toy):
        without = capability_slice(["ipv4"], specs=toy)
        with_tcp = capability_slice(["ipv4", "tcp"], specs=toy)

        assert "tcp" not in without.capabilities
        assert "tcp" in with_tcp.capabilities

    def test_a_shared_dependency_appears_once(self, toy):
        s = capability_slice(["framebuffer", "ipv4"], specs=toy)

        assert len(s.subsystems) == len(set(s.subsystems))
        assert set(s.subsystems) == {"video", "net", "dev", "mm", "hal"}


class TestRefusal:
    def test_a_required_capability_that_needs_an_excluded_one_is_refused(self, toy):
        with pytest.raises(SliceError) as exc:
            capability_slice(["ipv4"], ["mm"], specs=toy)

        assert "excluded" in str(exc.value)

    def test_the_refusal_names_the_path_that_caused_it(self, toy):
        """Without the path an operator knows only that it failed, not which
        requirement to drop."""
        with pytest.raises(SliceError) as exc:
            capability_slice(["framebuffer"], ["hal"], specs=toy)

        message = str(exc.value)
        assert "video" in message and "mm" in message and "hal" in message

    def test_requiring_and_excluding_the_same_thing_is_refused(self, toy):
        with pytest.raises(SliceError, match="both required and excluded"):
            capability_slice(["ipv4"], ["ipv4"], specs=toy)

    def test_an_excluded_subsystem_nothing_reaches_is_not_an_error(self, toy):
        """Excluding what you were never going to include is redundant, not
        contradictory."""
        s = capability_slice(["framebuffer"], ["net"], specs=toy)

        assert "net" not in s.subsystems


class TestNothingFailsQuietly:
    def test_an_unknown_required_capability_raises(self, toy):
        with pytest.raises(SliceError, match="unknown capability"):
            capability_slice(["bluetooth"], specs=toy)

    def test_an_unknown_capability_never_yields_an_empty_slice(self, toy):
        """The failure this guards: a typo'd manifest producing {} and looking
        like a correctly minimal image."""
        with pytest.raises(SliceError):
            capability_slice(["framebufer"], specs=toy)  # typo, deliberate

    def test_an_unknown_exclude_raises_rather_than_excluding_nothing(self, toy):
        with pytest.raises(SliceError, match="unknown excluded"):
            capability_slice(["framebuffer"], ["bluetoth"], specs=toy)

    def test_a_dependency_cycle_raises_rather_than_looping(self):
        cyclic = {
            "a": _spec("a", ["ca"], ["b"]),
            "b": _spec("b", ["cb"], ["a"]),
        }
        with pytest.raises(SliceError, match="cycle"):
            capability_slice(["ca"], specs=cyclic)

    def test_a_capability_owned_by_two_subsystems_raises(self):
        """Two owners makes `pci` ambiguous — the slice would depend on which
        spec was read second."""
        clash = {
            "x": _spec("x", ["shared"]),
            "y": _spec("y", ["shared"]),
        }
        with pytest.raises(SliceError, match="one owner"):
            build_owner_index(clash)


class TestAgainstTheRealSpecs:
    """The toy graph proves the algorithm; these prove the specs on disk are
    usable by it."""

    def test_every_spec_parses_and_declares_capabilities(self):
        specs = load_specs()

        assert len(specs) == 15, sorted(specs)
        assert all(s.provides for s in specs.values())

    def test_no_capability_has_two_owners(self):
        load_specs()  # raises if one does

    def test_a_doom_shaped_slice_excludes_the_network(self):
        s = capability_slice(
            ["boot", "allocator", "pci", "framebuffer", "input", "terminal",
             "scoped", "module-asset"],
            ["net", "ipc", "writable", "preemptive"],
        )

        assert "net" not in s.subsystems
        assert "sched" not in s.subsystems
        assert "fs" not in s.subsystems
        assert "framebuffer" in s.capabilities
        assert "terminal" in s.capabilities

    def test_a_webserver_shaped_slice_includes_the_network(self):
        s = capability_slice(
            ["boot", "allocator", "pci", "e1000", "terminal", "scoped", "ipv4"],
            ["ipc", "writable", "preemptive"],
        )

        assert "net" in s.subsystems
        assert "ipv4" in s.capabilities

    def test_the_two_manifests_slice_differently(self):
        doom = capability_slice(["framebuffer", "input", "terminal"], ["net"])
        web = capability_slice(["e1000", "ipv4", "terminal"], [])

        assert set(doom.subsystems) != set(web.subsystems)

    def test_optional_network_capabilities_do_not_ship_unasked(self):
        """An image that needs IPv4 should not carry a DHCP client and a DNS
        resolver it never asked for."""
        s = capability_slice(["ipv4", "terminal"], [])

        assert "ipv4" in s.capabilities
        assert "dhcp-client" not in s.capabilities
        assert "http-server" not in s.capabilities


class TestFat32IsSplitFromItsWritePath:
    """w12 F7: a read-only image must be able to require fat32 and exclude
    writable, or "read-only file server" is unfalsifiable."""

    def test_fat32_resolves_to_the_fs_subsystem(self):
        from capability_slice import capability_slice

        sl = capability_slice(["fat32"])
        assert "fs" in sl.subsystems

    def test_fat32_with_writable_excluded_is_admissible(self):
        from capability_slice import capability_slice

        sl = capability_slice(["fat32"], excludes=["writable"])
        assert "fs" in sl.subsystems
