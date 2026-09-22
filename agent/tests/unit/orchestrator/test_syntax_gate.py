"""A branch whose C does not compile goes back to its author, unreviewed.

w13 generate-mm: gemma4 wrote kernel/include/mm.h with `ttypedef enum`, the
reviewer model approved it in ten seconds, and it merged.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.core import syntax_gate
from orchestrator.core.task_graph import TaskState

from .test_review_path import _chain, _engine, _ok, _repo

CC = syntax_gate.compiler()
needs_cc = pytest.mark.skipif(CC is None, reason="no C compiler")


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    return tmp_path


@needs_cc
def test_a_clean_header_and_source_pass(tmp_path):
    t = _tree(tmp_path, {"kernel/include/mm.h": "#include <stdint.h>\nvoid pmm_init(void);\n",
                         "kernel/mm/pmm.c": '#include "mm.h"\nvoid pmm_init(void) {}\n'})
    assert syntax_gate.check(t, ["kernel/include/mm.h", "kernel/mm/pmm.c"]) is None


@needs_cc
def test_the_generate_mm_header_is_refused(tmp_path):
    t = _tree(tmp_path, {"kernel/include/mm.h": "ttypedef enum x { A } x_t;\n"})
    errors = syntax_gate.check(t, ["kernel/include/mm.h"])
    assert errors and "kernel/include/mm.h" in errors
    assert str(tmp_path) not in errors, "paths are shown relative to the tree"


@needs_cc
def test_a_header_that_cannot_stand_alone_is_refused(tmp_path):
    t = _tree(tmp_path, {"kernel/include/mm.h": "void pmm_init(const boot_mmap_t *m);\n"})
    assert syntax_gate.check(t, ["kernel/include/mm.h"])


def test_non_c_and_non_kernel_files_are_not_checked(tmp_path):
    t = _tree(tmp_path, {"docs/x.md": "ttypedef", "tests/t.c": "ttypedef"})
    assert syntax_gate.check(t, ["docs/x.md", "tests/t.c"], cc="false") is None


@needs_cc
async def test_the_engine_requeues_without_asking_the_reviewer(tmp_path):
    ws, g = _repo(tmp_path), _chain()
    g.update_state("t-1", TaskState.MERGED)
    ws.create_branch("dev-01", "x", "2")
    (tmp_path / "kernel" / "include").mkdir(parents=True)
    (tmp_path / "kernel" / "include" / "mm.h").write_text("ttypedef enum x { A } x_t;\n")
    eng = _engine(ws, g)

    await eng._handle_result(g.get_task("t-2"), _ok("t-2", "agent/dev-01/x-2"))

    node = g.get_task("t-2")
    assert eng._reviewer.agent.review_branch.await_count == 0
    assert node.state is not TaskState.APPROVED
    assert node.review_rounds == 1
    assert "does not compile" in str(node.data.get("feedback") or node.data)
