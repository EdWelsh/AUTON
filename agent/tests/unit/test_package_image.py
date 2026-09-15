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
