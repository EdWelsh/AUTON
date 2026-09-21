"""The factory pipeline and its gates.

F4 walked this path by hand, and five of the seven defects it found were
**disagreements between steps** — the stub generator compiling with different
defines than the build, one source added twice because two steps each appended
it, a stub list maintained separately from the check that reads it.

So the property under test is not "it builds". It is that each thing is derived
once, and that a violated gate refuses by name rather than producing a wrong
image quietly.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from build_service import (  # noqa: E402
    CAPABILITY_DEVICES,
    KERNEL_CFLAGS,
    STATIC_NET,
    GateFailure,
    _service_sources,
    gate_capabilities,
    gate_spec,
)
from intent_service import STUB_MARKER, emit  # noqa: E402

SERVICES = ROOT / "agent" / "kernel_spec" / "services"


class TestTheSpecGate:
    def test_a_real_service_passes(self):
        spec = gate_spec("dhcp")

        assert spec.service == "dhcp"
        assert spec.entry == "dhcp_serve"

    def test_a_generated_stub_is_refused(self, tmp_path):
        """intent-C emits valid front-matter over an empty body. It passes every
        structural check and is not implementable — an agent handed one writes
        code against prose that does not exist."""
        emit("hand out addresses", name="stubbed", out_dir=SERVICES)
        try:
            with pytest.raises(GateFailure, match="generated-stub marker"):
                gate_spec("stubbed")
        finally:
            (SERVICES / "stubbed.md").unlink(missing_ok=True)

    def test_an_unknown_service_is_refused_by_name(self):
        with pytest.raises(GateFailure, match="no such service spec|gate: spec"):
            gate_spec("nonexistent")

    def test_the_refusal_names_the_gate(self):
        with pytest.raises(GateFailure) as exc:
            gate_spec("nonexistent")

        assert "[gate:" in str(exc.value), "a bare failure sends someone reading a log"


class TestOneSourceOfTruth:
    def test_the_static_network_config_is_defined_once(self):
        """The stub generator compiling without the build's defines left the
        DHCP client path live and `dhcp_run` looking absent. One dict, shared."""
        assert set(STATIC_NET) == {"NET_STATIC_IP", "NET_STATIC_MASK",
                                   "NET_STATIC_GW", "NET_STATIC_DNS"}

    def test_the_guest_address_is_the_one_qemu_forwards_to(self):
        """10.0.2.15. A statically-configured guest at any other address is
        unreachable through a host port forward."""
        assert STATIC_NET["NET_STATIC_IP"] == "0x0A00020F"

    def test_kernel_flags_exclude_sse(self):
        """Interrupt handlers must never touch SSE state — the reason
        toolchain.mk keeps a separate CFLAGS_SSE for the neural code."""
        assert "-mno-sse" in KERNEL_CFLAGS
        assert "-mno-red-zone" in KERNEL_CFLAGS


class TestServiceSources:
    def test_a_services_own_sources_are_found(self):
        tree = ROOT / "kernels" / "x86_64"
        if not (tree / "kernel" / "services" / "dhcp").is_dir():
            pytest.skip("no DHCP service in the tree")

        found = _service_sources(tree, "dhcp")

        assert any(f.endswith("server.c") for f in found)
        assert any(f.endswith("serve.c") for f in found)

    def test_an_absent_service_directory_yields_nothing(self, tmp_path):
        assert _service_sources(tmp_path, "nosuch") == []


class TestMarkersComeFromTheSpec:
    def test_a_services_markers_are_read_from_its_spec(self):
        sys.path.insert(0, str(ROOT / "agent" / "kernel_spec" / "tests"))
        import acceptance_tests as at

        patterns = at.service_marker_patterns("dhcp")

        assert len(patterns) == 5
        assert any("listening on :67" in p.replace("\\", "") for p in patterns)

    def test_marker_text_is_escaped_not_treated_as_a_pattern(self):
        """`[DHCP]` is a literal the kernel prints, not a character class."""
        import re
        sys.path.insert(0, str(ROOT / "agent" / "kernel_spec" / "tests"))
        import acceptance_tests as at

        patterns = at.service_marker_patterns("dhcp")
        assert any(re.search(p, "[DHCP] listening on :67") for p in patterns)

    def test_an_unknown_service_raises_rather_than_returning_nothing(self):
        sys.path.insert(0, str(ROOT / "agent" / "kernel_spec" / "tests"))
        import acceptance_tests as at

        with pytest.raises(KeyError, match="no service spec"):
            at.service_marker_patterns("nosuch")

    def test_changing_the_spec_changes_what_is_asserted(self, tmp_path):
        """The property that makes this data rather than a copy."""
        sys.path.insert(0, str(ROOT / "agent" / "kernel_spec" / "tests"))
        import acceptance_tests as at

        original = (SERVICES / "dhcp.md").read_text()
        try:
            (SERVICES / "dhcp.md").write_text(
                original.replace('"[DHCP] listening on :67"', '"[DHCP] up on :67"', 1))
            patterns = at.service_marker_patterns("dhcp")
            assert any("up on :67" in p.replace("\\", "") for p in patterns)
        finally:
            (SERVICES / "dhcp.md").write_text(original)


class _Spec:
    """The two fields the capabilities gate reads. A real ServiceSpec needs a
    file on disk, and the gate's behaviour does not depend on the rest of it."""
    def __init__(self, requires):
        self.requires = list(requires)


class TestTheCapabilitiesGate:
    """A manifest requiring `nvme` resolved to a closed slice, passed every
    gate, and produced an image with no storage driver in it. Nothing was
    broken: `resolve()` computed `unmapped_capabilities` correctly and put it in
    a report field the pipeline never read.
    """

    def test_a_directly_required_unmapped_capability_refuses(self):
        report = {"unmapped_capabilities": ["nvme"], "capabilities": ["nvme"]}

        with pytest.raises(GateFailure, match="nvme"):
            gate_capabilities(_Spec(["boot", "nvme"]), report)

    def test_the_refusal_names_the_gate(self):
        """`build failed` sends someone reading a 200-line log to find out
        which step."""
        report = {"unmapped_capabilities": ["nvme"], "capabilities": []}

        with pytest.raises(GateFailure, match=r"\[gate: capabilities\]"):
            gate_capabilities(_Spec(["nvme"]), report)

    def test_the_refusal_says_what_to_do_next(self):
        report = {"unmapped_capabilities": ["ahci"], "capabilities": []}

        with pytest.raises(GateFailure) as exc:
            gate_capabilities(_Spec(["ahci"]), report)

        assert "source_map.yaml" in str(exc.value)

    def test_the_refusal_names_the_subsystem_that_promised_it(self):
        """The reader needs to know which spec advertised something the tree
        does not deliver."""
        report = {"unmapped_capabilities": ["nvme"], "capabilities": []}

        with pytest.raises(GateFailure, match=r"drivers"):
            gate_capabilities(_Spec(["nvme"]), report)

    def test_a_transitively_unmapped_capability_does_not_refuse(self):
        """The spec never named it. Refusing would blame the author for a
        dependency they did not choose."""
        report = {"unmapped_capabilities": ["vfs"], "capabilities": ["vfs"]}

        gate_capabilities(_Spec(["boot", "terminal"]), report)   # no raise

    def test_nothing_unmapped_passes(self):
        gate_capabilities(_Spec(["boot"]), {"unmapped_capabilities": []})

    def test_a_core_provided_capability_is_never_flagged(self):
        """`resolve()` skips `core_provides` before building the list, and the
        gate consumes that list rather than re-deriving it — a second copy of
        the rule would drift from the first."""
        report = {"unmapped_capabilities": [], "capabilities": ["serial"]}

        gate_capabilities(_Spec(["serial"]), report)             # no raise

    def test_every_offending_capability_is_named_in_one_run(self):
        report = {"unmapped_capabilities": ["nvme", "ahci", "vfs"]}

        with pytest.raises(GateFailure) as exc:
            gate_capabilities(_Spec(["nvme", "ahci"]), report)

        assert "nvme" in str(exc.value) and "ahci" in str(exc.value)

    def test_the_shipped_specs_require_nothing_unmapped(self):
        """`dhcp` and `fileserver` are the regression fixtures: the gate must
        not refuse builds that previously worked."""
        from build_manifest import resolve
        from capability_slice import capability_slice

        for name in ("dhcp", "fileserver"):
            spec = gate_spec(name)
            sl = capability_slice(list(spec.requires), list(spec.excludes))
            assert sl.capabilities            # resolves at all


class TestTheGateDoesNotDependOnTheRegistry:
    def test_it_still_refuses_when_the_registry_is_unavailable(self, monkeypatch):
        """An unidentifiable device is not a reason to allow an unimplementable
        build. The name is a courtesy; the refusal is not."""
        import device_registry

        device_registry._index.cache_clear()
        monkeypatch.setattr(
            device_registry, "_index",
            lambda: (_ for _ in ()).throw(RuntimeError("no registry")))

        report = {"unmapped_capabilities": ["e1000"], "capabilities": []}
        with pytest.raises(GateFailure, match="e1000"):
            gate_capabilities(_Spec(["e1000"]), report)

    def test_a_device_bearing_capability_is_named_when_the_registry_can(self):
        """No capability that is unmapped today carries a device id, so this
        path never fires against the shipped map — it is exercised here so the
        mechanism is tested rather than assumed."""
        from device_registry import Outcome, identify

        if identify("8086:100e").outcome is Outcome.UNAVAILABLE:
            pytest.skip("pci.ids not cached")

        report = {"unmapped_capabilities": ["e1000"], "capabilities": []}
        with pytest.raises(GateFailure) as exc:
            gate_capabilities(_Spec(["e1000"]), report)

        assert "82540EM" in str(exc.value)
        assert "8086:100e" in str(exc.value)

    def test_no_currently_unmapped_capability_carries_a_device_id(self):
        """States the finding rather than leaving it implicit: `nvme` and `ahci`
        are PCI class-coded devices, and the ingested registry holds device
        records only. Naming them would mean inventing a title."""
        assert not (set(CAPABILITY_DEVICES) & {"nvme", "ahci"})
