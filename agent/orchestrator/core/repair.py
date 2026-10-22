"""The repair phase: run the operator's gates when the task graph is done, and turn each
failure into a task for a developer, instead of ending the run on a known failure.

Observed 2026-10-22: R2 and R9 ended one task short of a pass, on a link error naming one
undefined function; R11 on one failing check; R10 and R12 on a boot marker nothing printed.
The gate said exactly what was wrong, and only after the run was over.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.core.events import emit
from orchestrator.core.proc import communicate

GATE_TIMEOUT = 1800
TAIL_LINES = 40
MEANING = {0: "pass", 1: "generated wrong", 2: "not generated"}
# ld: Undefined symbols ... "_fat32_list", referenced from ...  (macOS) / undefined reference to `x' (GNU)
_UNDEFINED = re.compile(r"""(?:"_?(\w+)", referenced from|undefined reference to [`'](\w+)')""")


@dataclass(frozen=True)
class GateReport:
    cmd: str
    rc: int
    tail: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.rc == 0


def undefined_symbols(lines: list[str] | tuple[str, ...]) -> list[str]:
    """Function names a link failure says nobody defined, in the order first seen."""
    seen: dict[str, None] = {}
    for m in _UNDEFINED.finditer("\n".join(lines)):
        seen.setdefault(next(g for g in m.groups() if g), None)
    return list(seen)


async def run_gates(commands: list[str], workspace: Path, repo: Path) -> list[GateReport]:
    """Run each gate exactly as the campaign does: from the repo root, KERNEL_TREE the workspace."""
    env = {**os.environ, "KERNEL_TREE": str(workspace)}
    reports = []
    for cmd in commands:
        try:
            proc = await asyncio.create_subprocess_exec(
                "bash", "-c", cmd, cwd=str(repo), env=env, start_new_session=True,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            out, _ = await communicate(proc, GATE_TIMEOUT)
        except (asyncio.TimeoutError, OSError) as exc:
            reports.append(GateReport(cmd, 2, (f"[gate did not run: {type(exc).__name__}]",)))
            continue
        lines = out.decode("utf-8", errors="replace").strip().splitlines()
        reports.append(GateReport(cmd, proc.returncode, tuple(lines[-TAIL_LINES:])))
    return reports


def repair_tasks(reports: list[GateReport], round_no: int) -> list[dict[str, Any]]:
    """One developer task per failing gate, carrying the gate's own words."""
    tasks = []
    for n, rep in enumerate(r for r in reports if not r.passed):
        symbols = undefined_symbols(rep.tail)
        hints = []
        if symbols:
            hints.append("The link names functions nobody defines: " + ", ".join(symbols)
                         + ". Define each one, with the signature the header in the tree declares.")
        if rep.rc == 2:
            hints.append("Exit 2 means a file or output the gate expects was never produced. "
                         "Create it where the gate and the spec say it lives; if it is a boot "
                         "marker, the code must be called from kernel_main and print it.")
        tasks.append({
            "task_id": f"repair-{round_no}{chr(ord('a') + n)}",
            "title": f"Repair gate: {rep.cmd.split('/')[-1]} (exit {rep.rc})",
            "subsystem": "repair",
            "assigned_to": "developer",
            "priority": 1,
            "dependencies": [],
            "description": (
                f"The operator's gate `{rep.cmd}` ran on the merged tree and did not pass "
                f"(exit {rep.rc}: {MEANING.get(rep.rc, 'failed')}). Its last lines:\n\n"
                + "\n".join(rep.tail) + "\n\n" + "\n".join(hints)
                + "\n\nChange only what these lines show is wrong or missing, then build the "
                "kernel. The reviewer re-runs the gate before this merges."),
            "acceptance_criteria": [f"`{rep.cmd}` exits 0 on this tree"],
        })
    return tasks


def record(round_no: int, reports: list[GateReport]) -> None:
    emit("gate_check", round=round_no, results=[{"cmd": r.cmd, "rc": r.rc} for r in reports])
