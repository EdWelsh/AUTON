"""A header that includes another subsystem's header passes the syntax gate when the run seeded
that subsystem's reference (w18 R1 attempt 2: `boot.h: No such file`)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from orchestrator.core import syntax_gate

pytestmark = pytest.mark.skipif(syntax_gate.compiler() is None, reason="no C compiler")


def _tree(tmp_path: Path, seed: bool) -> Path:
    (tmp_path / "kernel/include").mkdir(parents=True)
    (tmp_path / "kernel/include/mm.h").write_text(
        '#pragma once\n#include "boot.h"\nvoid mm_init(const boot_mmap_t *m);\n')
    if seed:
        ref = tmp_path / "tests/kernel/mm_reference/include"
        ref.mkdir(parents=True)
        (ref / "boot.h").write_text("#pragma once\ntypedef struct { int n; } boot_mmap_t;\n")
    return tmp_path


def test_a_foreign_header_is_found_in_the_seeded_reference(tmp_path):
    tree = _tree(tmp_path, seed=True)
    assert syntax_gate.check(tree, ["kernel/include/mm.h"]) is None


def test_without_the_seed_the_missing_header_still_fails(tmp_path):
    tree = _tree(tmp_path, seed=False)
    assert "boot.h" in (syntax_gate.check(tree, ["kernel/include/mm.h"]) or "")


def test_the_trees_own_header_wins_over_the_reference(tmp_path):
    tree = _tree(tmp_path, seed=True)
    (tree / "kernel/include/boot.h").write_text("#pragma once\n#error the tree's header was used\n")
    out = syntax_gate.check(tree, ["kernel/include/mm.h"]) or ""
    assert "the tree's header was used" in out
