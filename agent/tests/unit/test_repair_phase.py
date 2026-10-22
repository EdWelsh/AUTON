"""The repair phase: a failing gate becomes a developer task instead of the end of the run."""

from __future__ import annotations

import asyncio
from pathlib import Path

from orchestrator.core import repair
from orchestrator.core.repair import GateReport

MAC_LINK = ['Undefined symbols for architecture arm64:',
            '  "_fat32_list", referenced from:',
            '      _main in fat32_test-fefa92.o',
            'ld: symbol(s) not found for architecture arm64']


def test_undefined_symbols_are_read_from_a_macos_and_a_gnu_link_error():
    assert repair.undefined_symbols(MAC_LINK) == ["fat32_list"]
    assert repair.undefined_symbols(["ld: foo.o: undefined reference to `fdt_find_compatible'"]) \
        == ["fdt_find_compatible"]
    assert repair.undefined_symbols(['  "_a", referenced from:', '  "_b", referenced from:']) == ["a", "b"]
    assert repair.undefined_symbols(["PASS  all"]) == []


def test_only_failing_gates_get_a_task_carrying_their_output():
    reports = [GateReport("tests/kernel/a.sh", 0, ("PASS",)),
               GateReport("tests/kernel/b.sh", 1, tuple(MAC_LINK))]
    (task,) = repair.repair_tasks(reports, 1)
    assert task["task_id"] == "repair-1a" and task["assigned_to"] == "developer"
    assert "fat32_list" in task["description"] and "b.sh" in task["title"]
    assert repair.repair_tasks([reports[0]], 1) == []


def test_a_not_generated_gate_is_told_to_wire_the_marker():
    (task,) = repair.repair_tasks([GateReport("g.sh", 2, ("no [F00F] line",))], 2)
    assert "kernel_main" in task["description"] and task["task_id"] == "repair-2a"


def test_run_gates_reports_exit_codes_with_the_tree_in_the_environment(tmp_path):
    ok = "echo tree=$KERNEL_TREE; exit 0"
    bad = "echo broke; exit 1"
    got = asyncio.run(repair.run_gates([ok, bad], tmp_path, tmp_path))
    assert [g.rc for g in got] == [0, 1]
    assert f"tree={tmp_path}" in got[0].tail[0] and got[1].tail == ("broke",)


def test_a_gate_that_cannot_run_is_not_generated_not_a_crash(tmp_path):
    got = asyncio.run(repair.run_gates(["true"], tmp_path / "missing" / "nowhere", tmp_path / "gone"))
    assert got[0].rc == 2 and "did not run" in got[0].tail[0]
