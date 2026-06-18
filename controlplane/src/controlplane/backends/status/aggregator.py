"""Live snapshot aggregation for the unified status capability.

Each source (Docker, Kubernetes, host processes) is probed against the REAL
local CLI. A missing tool degrades gracefully via :func:`shutil.which` — the
source reports itself "unavailable" instead of crashing. This unit deliberately
does NOT import the sibling docker/kubernetes/server backend packages (they land
in separate PRs and may be absent); it queries the underlying CLIs directly so
it stays independently mergeable.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - we invoke fixed, argument-list commands only
from dataclasses import dataclass, field
from pathlib import Path

# Wall-clock budget per probe. A wedged daemon (e.g. a hung Docker socket) must
# never stall the whole snapshot, so every subprocess call is time-boxed.
_PROBE_TIMEOUT_SECONDS = 5

# Cap how many lines of a noisy source we surface, keeping the combined view
# concise as the prompt requires.
_MAX_LINES = 12

# Optional host process table written by the server backend (Unit for servers).
_AUTON_PROCESS_TABLE = Path.home() / ".auton" / "processes"


@dataclass(frozen=True)
class SourceReport:
    """The result of probing one status source.

    Immutable by design (repo coding-style: never mutate, return new copies).
    """

    name: str
    available: bool
    summary: str
    error: str | None = None


@dataclass(frozen=True)
class Snapshot:
    """A combined, point-in-time view across every status source."""

    reports: tuple[SourceReport, ...] = field(default_factory=tuple)

    def render(self) -> str:
        """A concise, human-readable combined view of all sources."""
        blocks = [f"{r.name}:\n  {r.summary.replace(chr(10), chr(10) + '  ')}" for r in self.reports]
        return "\n".join(blocks)


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a fixed command, capturing output, never raising on exit code."""
    return subprocess.run(  # nosec B603 - args is a fixed list, shell=False
        args,
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT_SECONDS,
        check=False,
    )


def _clip(text: str) -> str:
    """Trim trailing whitespace and cap to a sane number of lines."""
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return ""
    if len(lines) > _MAX_LINES:
        hidden = len(lines) - _MAX_LINES
        lines = lines[:_MAX_LINES] + [f"... (+{hidden} more)"]
    return "\n".join(lines)


def _unavailable(name: str, tool: str) -> SourceReport:
    return SourceReport(
        name=name,
        available=False,
        summary=f"unavailable ({tool} not installed)",
    )


def _probe_cli(name: str, tool: str, args: list[str], empty_label: str) -> SourceReport:
    """Shared CLI-probe shape: guard with which, run, never raise."""
    if shutil.which(tool) is None:
        return _unavailable(name, tool)
    try:
        proc = _run(args)
    except (subprocess.TimeoutExpired, OSError) as exc:  # daemon hung / spawn failed
        return SourceReport(
            name=name,
            available=False,
            summary=f"error querying {tool}: {exc}",
            error=str(exc),
        )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"{tool} exited {proc.returncode}"
        return SourceReport(name=name, available=False, summary=err, error=err)
    body = _clip(proc.stdout)
    return SourceReport(name=name, available=True, summary=body or empty_label)


def snapshot_docker() -> SourceReport:
    """Container snapshot via ``docker ps`` (degrades if docker is absent)."""
    return _probe_cli(
        "docker",
        "docker",
        ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"],
        "no running containers",
    )


def snapshot_kubernetes() -> SourceReport:
    """Pod snapshot via ``kubectl get pods -A`` (degrades if kubectl is absent)."""
    return _probe_cli(
        "kubernetes",
        "kubectl",
        ["kubectl", "get", "pods", "-A", "--no-headers"],
        "no pods",
    )


def _process_table_report() -> SourceReport | None:
    """Prefer the AUTON server process table if the host backend wrote one."""
    try:
        if not _AUTON_PROCESS_TABLE.is_file():
            return None
        body = _clip(_AUTON_PROCESS_TABLE.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not body:
        return None
    return SourceReport(name="processes", available=True, summary=body)


def snapshot_processes() -> SourceReport:
    """Host process snapshot.

    Prefers the AUTON process table at ``~/.auton/processes`` when present;
    otherwise falls back to a real ``ps`` listing of the top processes.
    """
    table = _process_table_report()
    if table is not None:
        return table

    if shutil.which("ps") is None:  # pragma: no cover - ps virtually always exists
        return _unavailable("processes", "ps")

    # Portable across BSD/macOS and GNU/Linux ps; sort by CPU, take a handful.
    args = ["ps", "-A", "-o", "pid,comm,%cpu,%mem"]
    try:
        proc = _run(args)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return SourceReport(
            name="processes",
            available=False,
            summary=f"error querying ps: {exc}",
            error=str(exc),
        )
    if proc.returncode != 0:
        err = (proc.stderr or "").strip() or f"ps exited {proc.returncode}"
        return SourceReport(name="processes", available=False, summary=err, error=err)

    lines = proc.stdout.strip().splitlines()
    header = lines[0] if lines else ""
    body_lines = lines[1:]
    total = len(body_lines)
    # Show the busiest few rather than the full table, keeping the view concise.
    body_lines.sort(key=_cpu_key, reverse=True)
    shown = [header] + body_lines[: _MAX_LINES - 1]
    summary = "\n".join(shown)
    if total > _MAX_LINES - 1:
        summary += f"\n... ({total} processes total)"
    return SourceReport(name="processes", available=True, summary=summary)


def _cpu_key(row: str) -> float:
    """Sort key: the %cpu column of a ``ps`` row (best-effort)."""
    parts = row.split()
    if len(parts) < 3:
        return 0.0
    try:
        return float(parts[2])
    except ValueError:
        return 0.0


def collect_snapshot() -> Snapshot:
    """Probe every source and return the combined immutable snapshot."""
    reports = (
        snapshot_docker(),
        snapshot_kubernetes(),
        snapshot_processes(),
    )
    return Snapshot(reports=reports)


def render_status(_text: str = "") -> str:
    """Format the full snapshot as the chat reply body."""
    snap = collect_snapshot()
    available = sum(1 for r in snap.reports if r.available)
    header = f"What's running ({available}/{len(snap.reports)} sources live):"
    return f"{header}\n\n{snap.render()}"
