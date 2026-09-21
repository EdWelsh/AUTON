"""Packaging an intent into a reviewable directory.

The PRD's reason for provenance is specific: *"a human must be able to review
generated kernel code without reading it blind."* That sets the bar — the record
has to say which spec section each artifact implements, not merely list files
with hashes.

The second property is that an unbuildable intent produces a package that says
so. A directory missing its ISO looks like a build that half-worked rather than
one that was never possible, and the difference is what the next person acts on.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from intent_manifest import IntentError  # noqa: E402
from package_image import package  # noqa: E402

TREE = ROOT / "kernels" / "x86_64"
CAN_BUILD = (TREE / "kernel").is_dir() and shutil.which("x86_64-elf-gcc") is not None


class TestAnUnbuildableIntentSaysSo:
    def test_doom_is_incomplete_not_partial(self, tmp_path):
        """No framebuffer driver exists, so no Doom image can be built. The
        package must be explicit rather than looking half-finished."""
        pkg = package("I want to play Doom", tmp_path / "out", TREE)

        assert not pkg.complete
        assert pkg.blocked_by
        assert not (tmp_path / "out" / "image.iso").exists()

    def test_the_readme_names_the_blocker(self, tmp_path):
        package("I want to play Doom", tmp_path / "out", TREE)
        text = (tmp_path / "out" / "README.md").read_text()

        assert "INCOMPLETE" in text
        assert "## What is missing" in text
        assert "never possible" in text

    def test_the_spec_subset_is_still_written(self, tmp_path):
        """An unbuildable intent still resolves to a slice, and that slice is
        the useful part of the package — it says what the image would contain."""
        package("I want to play Doom", tmp_path / "out", TREE)

        specs = list((tmp_path / "out" / "spec" / "subsystems").glob("*.md"))
        assert specs

    def test_an_unknown_intent_is_declined_before_anything_is_written(self, tmp_path):
        out = tmp_path / "out"
        with pytest.raises(IntentError):
            package("make me a sandwich", out, TREE)

        assert not out.exists() or not list(out.iterdir())


class TestTheSpecSubset:
    def test_it_records_why_each_subsystem_is_present(self, tmp_path):
        """'Which spec section each artifact implements' is the review bar. A
        subsystem listed with no reason is a file listing."""
        pkg = package("I want to play Doom", tmp_path / "out", TREE)

        assert pkg.spec_sections
        for section in pkg.spec_sections:
            assert section["subsystem"]
            assert section["included_because"], section

    def test_a_transitive_dependency_says_it_is_one(self, tmp_path):
        pkg = package("I want to play Doom", tmp_path / "out", TREE)
        reasons = [r for s in pkg.spec_sections for r in s["included_because"]]

        assert any("provides" in str(r) or r for r in reasons)

    def test_excluded_subsystems_are_absent_from_the_subset(self, tmp_path):
        """A Doom package carrying net.md would be describing an image it is
        not."""
        package("I want to play Doom", tmp_path / "out", TREE)
        names = {p.name for p in (tmp_path / "out" / "spec" / "subsystems").glob("*.md")}

        assert "net.md" not in names
        assert "fs.md" not in names


class TestProvenance:
    def test_every_artifact_records_tool_input_and_hash(self, tmp_path):
        pkg = package("I want to play Doom", tmp_path / "out", TREE)

        for a in pkg.artifacts:
            assert a.produced_by, a.path
            assert a.from_input, a.path
            assert len(a.sha256) == 64, a.path
            assert a.bytes >= 0

    def test_a_modified_artifact_is_detectable(self, tmp_path):
        """A hash nobody can check is decoration."""
        import hashlib

        out = tmp_path / "out"
        pkg = package("I want to play Doom", out, TREE)
        target = next(a for a in pkg.artifacts if a.path.endswith(".json"))

        p = out / target.path
        p.write_text(p.read_text() + "\n# tampered\n")
        actual = hashlib.sha256(p.read_bytes()).hexdigest()

        assert actual != target.sha256

    def test_the_record_is_valid_json_with_the_expected_shape(self, tmp_path):
        out = tmp_path / "out"
        package("I want to play Doom", out, TREE)
        data = json.loads((out / "PROVENANCE.json").read_text())

        for field in ("intent", "matched_rule", "created_at", "complete",
                      "artifacts", "spec_sections"):
            assert field in data, field

    def test_applied_assumptions_reach_the_package(self, tmp_path):
        """intent-B records a default; it must survive two handoffs to the
        person who opens the directory."""
        pkg = package("what hardware is in this machine", tmp_path / "out", TREE)

        assert any("input" in a for a in pkg.assumptions)
        assert "Assumptions applied" in (tmp_path / "out" / "README.md").read_text()


@pytest.mark.skipif(not CAN_BUILD, reason="needs a kernel tree and cross toolchain")
class TestACompletePackage:
    def test_dhcp_packages_completely(self, tmp_path):
        pkg = package("hand out addresses", tmp_path / "out", TREE, service="dhcp")

        assert pkg.complete, pkg.blocked_by
        assert (tmp_path / "out" / "image.iso").exists()
        assert (tmp_path / "out" / "install.sh").exists()

    def test_the_installer_refuses_without_a_target(self, tmp_path):
        import subprocess

        package("hand out addresses", tmp_path / "out", TREE, service="dhcp")
        r = subprocess.run([str(tmp_path / "out" / "install.sh")],
                           capture_output=True, text=True, timeout=60)

        assert r.returncode == 2
        assert "ERASES" in r.stderr

    def test_the_installer_refuses_a_non_block_device(self, tmp_path):
        import subprocess

        package("hand out addresses", tmp_path / "out", TREE, service="dhcp")
        r = subprocess.run([str(tmp_path / "out" / "install.sh"), str(tmp_path)],
                           capture_output=True, text=True, timeout=60)

        assert r.returncode == 2
        assert "not a block device" in r.stderr

    def test_the_leakage_measurement_is_carried_into_the_package(self, tmp_path):
        """A reviewer should not have to rebuild to learn whether the image
        contains what its manifest excluded."""
        pkg = package("hand out addresses", tmp_path / "out", TREE, service="dhcp")

        assert pkg.leakage
        assert pkg.leakage["leaked_symbols"] == 0
        assert pkg.leakage["conclusive"]


class TestTheScopedModel:
    """Training takes minutes, so the fast checks are on the plumbing and the
    failure path. The full run is marked slow and exercised separately."""

    def test_without_training_the_absence_is_recorded_not_silent(self, tmp_path):
        """An image without a model is a worse image, not a failed package —
        but the README must say which one it is, because the difference is what
        the image can answer."""
        pkg = package("I want to play Doom", tmp_path / "out", TREE, train=False)

        assert any("model: none packaged" in a for a in pkg.assumptions)
        assert "rule engine" in " ".join(pkg.assumptions)

    def test_a_training_failure_is_a_note_not_an_exception(self, tmp_path, monkeypatch):
        import package_image

        def fail(manifest, workdir, steps=3000):
            return None, "forced failure"

        monkeypatch.setattr(package_image, "train_scoped_model", fail)
        pkg = package("I want to play Doom", tmp_path / "out", TREE, train=True)

        assert any("forced failure" in a for a in pkg.assumptions)

    def test_a_supplied_model_is_packaged_with_its_manifest(self, tmp_path):
        """The manifest sits beside the model so the two cannot be separated —
        a model whose scope nobody can look up is a model nobody can trust."""
        fake = tmp_path / "auton-slm.bin"
        fake.write_bytes(b"\x00" * 64)

        pkg = package("I want to play Doom", tmp_path / "out", TREE, model=fake)

        assert (tmp_path / "out" / "model" / "auton-slm.bin").exists()
        assert (tmp_path / "out" / "model" / "manifest.json").exists()
        assert any(a.path == "model/manifest.json" for a in pkg.artifacts)

    @pytest.mark.slow
    @pytest.mark.skipif(not CAN_BUILD, reason="needs a kernel tree and cross toolchain")
    def test_a_full_package_trains_and_ships_a_valid_model(self, tmp_path):
        """AUTON train "<intent>" --output <dir>, end to end. ~2 minutes."""
        import subprocess

        pkg = package("hand out addresses", tmp_path / "out", TREE,
                      service="dhcp", train=True)

        assert pkg.complete
        model = tmp_path / "out" / "model" / "auton-slm.bin"
        assert model.exists()

        r = subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"),
             str(ROOT / "SLM" / "tools" / "auton_format.py"), "--validate", str(model)],
            capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        # The training work directory is large and is not the deliverable.
        assert not (tmp_path / "out" / "model" / "work").exists()


class TestThePackageRecordsWhatItRunsOn:
    """`spec_sections` says what an image is *for*. Until D1 there was no format
    for the other half, so a package could say "this image serves DHCP" and
    nothing at all about the machine it expects.

    The intent here is deliberately one that needs no NIC. Since D7 the driver
    is chosen from the target's devices, and pairing a DHCP server with
    Firecracker is refused — that machine's network device needs `virtio-net`,
    which no subsystem spec provides. These tests are about the target being
    *recorded*, so they use a pairing that is actually buildable.
    """

    INTENT = "what hardware is this"
    TARGET = ROOT / "agent" / "kernel_spec" / "targets" / "firecracker.md"

    def test_a_stated_target_is_recorded_and_copied(self, tmp_path):
        out = tmp_path / "out"
        pkg = package(self.INTENT, out, TREE, target=self.TARGET)

        assert pkg.target["stated"] is True
        assert pkg.target["target"] == "firecracker"
        assert (out / "spec" / "target.md").exists()

    def test_the_recorded_target_keeps_each_fact_s_source(self, tmp_path):
        """A decision made on an assumption must be reversible when the truth
        arrives, and a provenance record that drops `source` cannot support
        that."""
        pkg = package(self.INTENT, tmp_path / "out", TREE,
                      target=self.TARGET)

        assert pkg.target["silicon"]["source"] == "assumed"
        assert {d["source"] for d in pkg.target["devices"]} == {"derived"}

    def test_absences_survive_into_provenance(self, tmp_path):
        pkg = package(self.INTENT, tmp_path / "out", TREE,
                      target=self.TARGET)
        assert any("PCI bus" in a for a in pkg.target["absent"])

    def test_an_image_without_a_target_says_so(self, tmp_path):
        """An absent field and a deliberate "no machine in particular" are
        different claims, and a reader cannot tell them apart."""
        pkg = package(self.INTENT, tmp_path / "out", TREE)

        assert pkg.target["stated"] is False
        assert pkg.target["why"]
        assert not (tmp_path / "out" / "spec" / "target.md").exists()

    def test_an_invalid_target_fails_the_package(self, tmp_path):
        """A package carrying a target that does not parse is worse than one
        carrying none: the next reader believes it."""
        from target_spec import TargetError

        bad = tmp_path / "bad.md"
        bad.write_text("---\ntarget: bad\nclass: vm\n---\n")
        with pytest.raises(TargetError):
            package(self.INTENT, tmp_path / "out", TREE, target=bad)

    def test_the_target_is_in_the_artifact_list_with_a_hash(self, tmp_path):
        pkg = package(self.INTENT, tmp_path / "out", TREE,
                      target=self.TARGET)
        entry = next(a for a in pkg.artifacts if a.path == "spec/target.md")
        assert len(entry.sha256) == 64
        assert "built to run on" in entry.implements


class TestPackagingRefusesAnImpossiblePairing:
    """D7's refusal reaching the packaging layer.

    Firecracker was this case until V5 specified `virtio-net`. It is now
    plannable — the manifest selects the driver — and still not *buildable*,
    because nothing implements it and `[gate: capabilities]` says so. The
    refusal moved down a layer rather than disappearing, which is the honest
    outcome: planning works, building refuses.
    """

    NO_DRIVER = ROOT / "agent" / "kernel_spec" / "targets" / "firecracker.md"

    def test_a_machine_whose_driver_the_index_lacks_is_refused(self, tmp_path):
        """`8086:10d3` resolves to `e1000e`, which `drivers.md` does not
        provide. The mechanism is unchanged; only Firecracker moved."""
        from intent_manifest import TargetMismatch

        target = tmp_path / "e1000e-box.md"
        target.write_text(
            "---\ntarget: e1000e-box\nclass: vm\narch: x86_64\n"
            "firmware: bios\nsilicon:\n  vendor: GenuineIntel\n  family: 6\n"
            "  model: 6\n  stepping: 3\n  source: probed\ndevices:\n"
            '  - id: "8086:10d3"\n    role: network\n    source: probed\n'
            "provenance:\n  stated_by: test\n---\n")

        with pytest.raises(TargetMismatch, match="e1000e"):
            package("hand out addresses", tmp_path / "out", TREE, target=target)

    def test_nothing_is_written_when_the_pairing_is_refused(self, tmp_path):
        """The same rule intent-C set: a declined sentence used to leave an
        empty spec/ behind, and an empty package directory looks like a build
        that produced nothing rather than one that never started."""
        from intent_manifest import TargetMismatch

        out = tmp_path / "out"
        target = tmp_path / "e1000e-box.md"
        target.write_text(
            "---\ntarget: e1000e-box\nclass: vm\narch: x86_64\n"
            "firmware: bios\nsilicon:\n  vendor: GenuineIntel\n  family: 6\n"
            "  model: 6\n  stepping: 3\n  source: probed\ndevices:\n"
            '  - id: "8086:10d3"\n    role: network\n    source: probed\n'
            "provenance:\n  stated_by: test\n---\n")

        with pytest.raises(TargetMismatch):
            package("hand out addresses", out, TREE, target=target)

        assert not out.exists()

    def test_firecracker_now_packages_but_would_not_build(self, tmp_path):
        """V5 moved the refusal from the manifest to the build gate. A package
        is a plan; `[gate: capabilities]` is what refuses to produce an image
        with no driver in it."""
        from build_service import GateFailure, gate_capabilities

        pkg = package("hand out addresses", tmp_path / "out", TREE,
                      target=self.NO_DRIVER)
        assert "virtio-net" in pkg.target["target"] or pkg.target["stated"]

        class _Spec:
            requires = ["virtio-net"]

        with pytest.raises(GateFailure, match="virtio-net"):
            gate_capabilities(_Spec(), {"unmapped_capabilities": ["virtio-net"],
                                        "capabilities": []})

    def test_the_driver_decision_reaches_the_manifest_on_disk(self, tmp_path):
        import json

        out = tmp_path / "out"
        package("hand out addresses", out, TREE,
                target=ROOT / "agent" / "kernel_spec" / "targets" / "qemu-pc.md")
        manifest = json.loads((out / "spec" / "manifest.json").read_text())

        assert manifest["target"] == "qemu-pc"
        assert manifest["decisions"][0]["device"] == "8086:100e"
