"""Manifest-to-source-list resolution.

The property that matters most is the boring one: resolving the *full* manifest
must reproduce what the build already compiles, byte for byte. A refactor that
changes the general image while claiming to add scoping is two changes wearing
one commit, and the second one hides inside the first.

After that, the checks are about not failing quietly — a capability with no
source mapping produces an image missing something the manifest asked for, and
the symptom is a link error in a file nobody was editing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from build_manifest import (  # noqa: E402
    ManifestError,
    SourceMap,
    _match,
    _tree_sources,
    resolve,
)

TREE = ROOT / "kernels" / "x86_64"
pytestmark = pytest.mark.skipif(
    not (TREE / "kernel").is_dir(),
    reason="no kernel tree to resolve against",
)


@pytest.fixture(scope="module")
def source_map():
    return SourceMap.load()


class TestTheSourceMap:
    def test_every_mapped_capability_exists_in_the_index(self, source_map):
        """A mapping for a capability the index does not define is dead data
        that will never be selected."""
        from capability_slice import capability_owner, load_specs

        known = set(capability_owner(load_specs()))
        unknown = [c for c in source_map.capabilities if c not in known]
        assert not unknown, f"mapped but not a capability: {unknown}"

    def test_core_provides_are_real_capabilities(self, source_map):
        from capability_slice import capability_owner, load_specs

        known = set(capability_owner(load_specs()))
        unknown = [c for c in source_map.core_provides if c not in known]
        assert not unknown, f"core claims to provide non-capabilities: {unknown}"

    def test_the_mandatory_core_matches_something(self, source_map):
        matched = [p for p in _tree_sources(TREE)
                   if _match(source_map.mandatory_core, str(p.relative_to(TREE)))]
        assert matched, "the mandatory core matches no source in the tree"


class TestFullResolutionMatchesTheGlob:
    def test_requiring_everything_includes_every_source(self, source_map):
        """The status-quo check. `find kernel -name '*.c'` is what the build
        does today, and the resolver has to agree with it before its scoping
        can be trusted."""
        from capability_slice import capability_owner, load_specs

        every_capability = sorted(capability_owner(load_specs()))
        included, excluded, _ = resolve(every_capability, [], TREE, source_map)

        # A source no capability claims would be silently dropped from every
        # scoped image, and nobody would notice until the link failed.
        unclaimed = sorted(str(p.relative_to(TREE)) for p in excluded)
        assert not unclaimed, f"no capability claims: {unclaimed}"
        assert len(included) == len(_tree_sources(TREE))

    def test_capabilities_this_tree_does_not_implement_are_reported(self, source_map):
        """The seed tree has no ipc, fs or sched. Requiring everything must say
        so rather than quietly producing an image without them — that is the
        difference between "not built here" and "silently missing"."""
        from capability_slice import capability_owner, load_specs

        every_capability = sorted(capability_owner(load_specs()))
        _, _, report = resolve(every_capability, [], TREE, source_map)

        unmapped = set(report["unmapped_capabilities"])
        assert {"channels", "vfs", "preemptive"} <= unmapped, sorted(unmapped)


class TestScoping:
    def test_a_no_network_slice_drops_the_network_sources(self, source_map):
        included, excluded, _ = resolve(
            ["framebuffer", "input", "terminal", "allocator", "pci"], ["net"],
            TREE, source_map)

        names = {str(p.relative_to(TREE)) for p in included}
        assert not [n for n in names if n.startswith("kernel/net/")]
        assert not [n for n in names if n.startswith("kernel/server/")]

    def test_scoping_only_removes(self, source_map):
        from capability_slice import capability_owner, load_specs

        every = sorted(capability_owner(load_specs()))
        full, _, _ = resolve(every, [], TREE, source_map)
        scoped, _, _ = resolve(["terminal", "allocator", "pci"], ["net"], TREE, source_map)

        assert set(scoped) <= set(full), "scoping invented a source"

    def test_the_mandatory_core_survives_every_exclusion(self, source_map):
        """An image with no console cannot report why it failed."""
        included, _, _ = resolve(["allocator"], ["net", "fs"], TREE, source_map)

        names = {str(p.relative_to(TREE)) for p in included}
        assert "kernel/boot/kernel_main.c" in names
        assert "kernel/lib/kprintf.c" in names
        assert "kernel/sys/console.c" in names

    def test_two_services_resolve_to_different_source_sets(self, source_map):
        sys.path.insert(0, str(ROOT / "agent" / "tools"))
        from service_spec import load as load_service

        services = ROOT / "agent" / "kernel_spec" / "services"
        dhcp = load_service(services / "dhcp.md")
        fileserver = load_service(services / "fileserver.md")

        a, _, _ = resolve(list(dhcp.requires), list(dhcp.excludes), TREE, source_map)
        b, _, _ = resolve(list(fileserver.requires), list(fileserver.excludes),
                          TREE, source_map)

        assert set(a) != set(b)


class TestNothingFailsQuietly:
    def test_an_unmapped_capability_is_reported(self, source_map):
        """Not raised — the build may legitimately proceed — but never silent,
        because the symptom otherwise appears as a link error elsewhere."""
        gapped = SourceMap(
            mandatory_core=source_map.mandatory_core,
            core_provides=frozenset(),
            capabilities={},
        )
        _, _, report = resolve(["terminal", "allocator"], [], TREE, gapped)

        assert report["unmapped_capabilities"], "a wholly unmapped slice reported nothing"

    def test_a_contradictory_manifest_is_refused(self, source_map):
        with pytest.raises(ManifestError, match="excluded"):
            resolve(["tcp"], ["mm"], TREE, source_map)

    def test_an_unknown_capability_is_refused(self, source_map):
        with pytest.raises(ManifestError, match="unknown"):
            resolve(["telepathy"], [], TREE, source_map)

    def test_an_empty_tree_is_refused(self, tmp_path, source_map):
        with pytest.raises(ManifestError, match="no .c or .S sources"):
            resolve(["allocator"], [], tmp_path, source_map)
