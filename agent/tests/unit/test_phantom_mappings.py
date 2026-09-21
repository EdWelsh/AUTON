"""A source mapping that points at a directory which has never existed.

V1 made an *absent* mapping a build failure. This is the state V1's own report
recorded as open and more dangerous: a mapping that resolves, matches nothing,
and passes every gate.

Measured before the fix, on a tree with no `kernel/drivers/blk/`:

    virtio-blk reported unmapped?  False
    files behind kernel/drivers/fb/**:  0
    => the gate passes and the image would contain no block driver
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from build_manifest import SourceMap, resolve  # noqa: E402
from build_service import GateFailure, gate_capabilities  # noqa: E402


class _Spec:
    def __init__(self, requires):
        self.requires = list(requires)


@pytest.fixture
def tree(tmp_path):
    """A tree realising only the patterns named, so the rest are phantom."""
    def _make(*capabilities, core=True):
        sm = SourceMap.load()
        pats = list(sm.mandatory_core) if core else []
        for cap in capabilities:
            pats += list(sm.capabilities.get(cap, ()))
        for pat in pats:
            p = tmp_path / pat.replace("/**", "/impl.c")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("/* stand-in */\n")
        return tmp_path
    return _make


class TestTheThirdState:
    def test_a_mapping_matching_nothing_is_reported(self, tree):
        """Any mapped capability whose sources are absent from the tree.

        This test named `virtio-blk`, then `framebuffer`, and broke both times
        when the phase that fixed the real defect removed the mapping. Pinning a
        test to a live defect means it fails on success. It now picks whatever
        mapped capability the tree lacks, which is the property being tested."""
        t = tree("udp", "ipv4")
        sm = SourceMap.load()
        absent = next(c for c in sm.capabilities
                      if c not in sm.core_provides and c not in ("udp", "ipv4"))

        _, _, report = resolve(["boot", "allocator", "pci", "terminal",
                                "scoped", absent], [], t)

        assert absent in report["phantom_capabilities"]

    def test_it_is_not_reported_as_unmapped(self):
        """The two states have different fixes — one needs a mapping added, the
        other has one that lies — so merging them loses what to do next."""
        sm = SourceMap.load()

        assert sm.capabilities, "the map has no capabilities at all"

    @pytest.mark.parametrize("capability", ["virtio-blk", "framebuffer"])
    def test_removed_phantom_mappings_are_honestly_unmapped(self, capability):
        """Both mapped to directories that have never existed. V6 and V7 removed
        them: the capabilities are still specified and still unimplemented, and
        they now say so in the way that tells the reader what to do.

        `input` is deliberately not here — it maps to kernel/drivers/arch/**,
        which is also in mandatory_core and matches real sources. A mapping that
        points at something is not the defect."""
        sm = SourceMap.load()

        assert capability not in sm.capabilities

    def test_a_mapping_that_matches_is_not_phantom(self, tree):
        t = tree("udp", "ipv4", "input")

        _, _, report = resolve(["boot", "allocator", "pci", "terminal",
                                "scoped", "input"], [], t)

        assert "input" not in report["phantom_capabilities"]

    def test_phantom_only_when_every_pattern_matches_nothing(self, tmp_path):
        """A capability with two patterns, one of which matched, is satisfied.
        Reporting it would fire on every partial map and teach the reader to
        ignore the warning.

        The capability must be one `resolve()` actually considers: anything in
        `core_provides` is skipped before the check, so picking `serial` here
        makes the test pass without exercising anything.
        """
        sm = SourceMap.load()
        multi = [c for c, pats in sm.capabilities.items()
                 if len(pats) > 1 and c not in sm.core_provides]
        assert multi, "the map has no multi-pattern, non-core capability"

        cap = multi[0]
        for pat in list(sm.mandatory_core) + [sm.capabilities[cap][0]]:
            f = tmp_path / pat.replace("/**", "/impl.c")
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("/* x */\n")

        _, _, report = resolve(["boot", cap], [], tmp_path)

        assert cap in report["capabilities"], f"{cap} not in the slice"
        assert cap not in report["phantom_capabilities"]

    def test_a_capability_with_no_pattern_matching_is_phantom(self, tmp_path):
        """The other side of the same rule, so the pair pins the boundary."""
        sm = SourceMap.load()
        multi = [c for c, pats in sm.capabilities.items()
                 if len(pats) > 1 and c not in sm.core_provides]
        cap = multi[0]
        for pat in sm.mandatory_core:
            f = tmp_path / pat.replace("/**", "/impl.c")
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("/* x */\n")

        _, _, report = resolve(["boot", cap], [], tmp_path)

        assert cap in report["phantom_capabilities"]

    def test_both_states_are_in_the_report(self, tree):
        t = tree("udp")
        _, _, report = resolve(["boot", "allocator", "pci", "terminal",
                                "scoped"], [], t)

        assert "unmapped_capabilities" in report
        assert "phantom_capabilities" in report


class TestTheGateRefusesIt:
    def test_a_directly_required_phantom_capability_refuses(self):
        report = {"unmapped_capabilities": [],
                  "phantom_capabilities": ["input"], "capabilities": []}

        with pytest.raises(GateFailure, match="points at nothing"):
            gate_capabilities(_Spec(["boot", "input"]), report)

    def test_the_refusal_names_the_pattern_that_matched_nothing(self):
        sm = SourceMap.load()
        cap = next(iter(sm.capabilities))
        report = {"unmapped_capabilities": [],
                  "phantom_capabilities": [cap], "capabilities": []}

        with pytest.raises(GateFailure) as exc:
            gate_capabilities(_Spec([cap]), report)

        assert sm.capabilities[cap][0] in str(exc.value)

    def test_the_refusal_says_to_remove_the_mapping(self):
        """The fix is the opposite of the unmapped case: one needs a mapping
        added, this one needs a lie taken away."""
        report = {"unmapped_capabilities": [],
                  "phantom_capabilities": ["input"], "capabilities": []}

        with pytest.raises(GateFailure) as exc:
            gate_capabilities(_Spec(["input"]), report)

        assert "Remove the mapping" in str(exc.value)
        assert "an absent mapping refuses honestly" in str(exc.value)

    def test_a_transitive_phantom_capability_does_not_refuse(self):
        """The rule V1 established, for the same reason: the spec never named
        it, so refusing blames the author for a dependency they did not
        choose."""
        report = {"unmapped_capabilities": [],
                  "phantom_capabilities": ["vfs"], "capabilities": ["vfs"]}

        gate_capabilities(_Spec(["boot", "terminal"]), report)   # no raise

    def test_the_two_messages_are_different(self):
        """A reader who cannot tell the two apart cannot act on either."""
        unmapped = {"unmapped_capabilities": ["nvme"],
                    "phantom_capabilities": [], "capabilities": []}
        phantom = {"unmapped_capabilities": [],
                   "phantom_capabilities": ["input"], "capabilities": []}

        with pytest.raises(GateFailure) as a:
            gate_capabilities(_Spec(["nvme"]), unmapped)
        with pytest.raises(GateFailure) as b:
            gate_capabilities(_Spec(["input"]), phantom)

        assert str(a.value) != str(b.value)
        assert "no source mapping" in str(a.value)
        assert "points at nothing" in str(b.value)

    def test_an_unmapped_capability_is_not_reported_twice(self):
        """A capability can be both, and saying so twice is noise."""
        report = {"unmapped_capabilities": ["nvme"],
                  "phantom_capabilities": ["nvme"], "capabilities": []}

        with pytest.raises(GateFailure) as exc:
            gate_capabilities(_Spec(["nvme"]), report)

        assert "points at nothing" not in str(exc.value)


class TestARecordCannotClaimImplementedOverAPhantom:
    def test_implemented_is_refused_when_the_tree_lacks_the_source(self, tree):
        from driver_spec import DriverError, validate

        t = tree("udp")     # no e1000 source

        with pytest.raises(DriverError, match="does not contain it"):
            validate(ROOT / "agent" / "kernel_spec" / "drivers" / "e1000.md", t)

    def test_a_record_still_validates_standalone(self):
        """`driver_spec` has no tree. The stricter check runs where one is
        known; without one a record must still be checkable."""
        from driver_spec import validate

        r = validate(ROOT / "agent" / "kernel_spec" / "drivers" / "e1000.md")
        assert r.unmapped == []

    def test_a_tree_that_has_the_source_passes(self, tree):
        from driver_spec import validate

        t = tree("e1000")
        r = validate(ROOT / "agent" / "kernel_spec" / "drivers" / "e1000.md", t)

        assert r.unmapped == []


class TestTheFileThatCausedItSaysSo:
    def test_the_header_no_longer_calls_the_state_undetected(self):
        """Leaving a comment saying this is out of scope, after fixing it, is
        how a comment becomes a lie."""
        text = (ROOT / "agent" / "kernel_spec" / "source_map.yaml").read_text()
        header = text.split("version: 1")[0]

        assert "now DETECTED" in header
        assert "recorded as open" not in header

    def test_the_header_states_the_rule_that_follows(self):
        """Comment prose is line-wrapped, so the assertion normalises rather
        than depending on where the wrap happens to fall."""
        text = (ROOT / "agent" / "kernel_spec" / "source_map.yaml").read_text()
        flat = " ".join(text.replace("#", " ").split())

        assert "An absent mapping refuses honestly; one that lies does not" in flat
        assert "NO entry here" in flat
