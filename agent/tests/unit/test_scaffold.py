"""Scaffolding a buildable tree.

AUTON contains no kernel — `kernels/` was deleted because the agents write it.
But a tree still needs a Makefile, a linker script and a toolchain fragment
before anything compiles, and those are identical for every image.

The distinction this holds: the factory *emits* build scaffolding, and an agent
*authors* kernel source. A tree with scaffolding and no source is refused with
that explanation, rather than failing at a link error.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from build_service import TEMPLATES, GateFailure, build, scaffold  # noqa: E402


class TestTheTemplate:
    def test_it_contains_no_kernel_source(self):
        """If C source appeared here it would be a kernel in the repo, which is
        the thing that was deleted."""
        sources = [p for p in TEMPLATES.rglob("*") if p.suffix in (".c", ".h", ".S")]

        assert not sources, [str(p) for p in sources]

    def test_it_has_what_a_build_needs(self):
        names = {p.name for p in TEMPLATES.rglob("*") if p.is_file()}

        assert "Makefile" in names
        assert "linker.ld" in names
        assert "toolchain.mk" in names

    def test_the_makefile_does_not_glob_for_sources(self):
        """A generated tree's source list comes from build_manifest.py. A
        Makefile that globs would compile whatever an agent left lying around,
        including files the manifest excludes."""
        text = (TEMPLATES / "x86_64" / "Makefile").read_text()

        assert "CSRC" in text


class TestScaffolding:
    def test_it_lays_the_build_files(self, tmp_path):
        placed = scaffold(tmp_path)

        assert (tmp_path / "Makefile").exists()
        assert (tmp_path / "kernel" / "arch" / "x86_64" / "linker.ld").exists()
        assert (tmp_path / "grub" / "grub.cfg").exists()
        assert len(placed) == 5

    def test_arch_files_land_under_the_kernel_arch_directory(self, tmp_path):
        """toolchain.mk and linker.ld are included by paths the Makefile
        expects; putting them at the root would build nothing."""
        scaffold(tmp_path)

        assert (tmp_path / "kernel" / "arch" / "x86_64" / "toolchain.mk").exists()

    def test_it_does_not_overwrite_existing_files(self, tmp_path):
        """Safe to run over a tree an agent has already written into."""
        scaffold(tmp_path)
        (tmp_path / "Makefile").write_text("# edited by an agent\n")

        placed = scaffold(tmp_path)

        assert placed == []
        assert "edited by an agent" in (tmp_path / "Makefile").read_text()

    def test_an_unknown_arch_is_refused(self, tmp_path):
        with pytest.raises(GateFailure, match="no template for arch"):
            scaffold(tmp_path, arch="vax")


class TestATreeWithoutSource:
    def test_building_is_refused_with_the_reason(self, tmp_path):
        """Not a link error. The tree is fine; it simply has no kernel in it,
        and that is the project's whole premise."""
        scaffold(tmp_path)

        with pytest.raises(GateFailure, match="no kernel source"):
            build("dhcp", tmp_path)

    def test_the_refusal_says_where_a_kernel_comes_from(self, tmp_path):
        scaffold(tmp_path)

        with pytest.raises(GateFailure) as exc:
            build("dhcp", tmp_path)

        assert "agents write it" in str(exc.value)
        assert "kernel_spec/subsystems" in str(exc.value)

    def test_a_refused_build_leaves_the_tree_as_it_found_it(self, tmp_path):
        """Scaffolding used to be laid before the sources gate, so every refusal
        left a Makefile behind. Pointed at the default `kernels/x86_64`, that
        half-tree made every tree-dependent test in the suite stop skipping."""
        tree = tmp_path / "kernels" / "x86_64"

        with pytest.raises(GateFailure):
            build("dhcp", tree)

        assert not tree.exists()


class TestTheRepoContainsNoKernel:
    def test_no_kernel_tree_is_tracked(self):
        import subprocess

        out = subprocess.run(["git", "ls-files", "kernels/"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
        # Deleted from the index; anything still listed is staged for deletion.
        staged = subprocess.run(["git", "diff", "--cached", "--name-only",
                                 "--diff-filter=D", "kernels/"],
                                cwd=ROOT, capture_output=True, text=True).stdout
        assert not out or all(line in staged for line in out.splitlines())

    def test_the_structural_reference_survives(self):
        """Deleting the tree keeps its structure, per kernel_spec/reference/."""
        import json

        graph = json.loads(
            (ROOT / "agent" / "kernel_spec" / "reference" / "x86_64" /
             "graph.json").read_text())

        assert len(graph["files"]) > 40
        assert graph["symbols"]
        assert graph["source_commit"]
