"""Tests for the unified status / "what's running" aggregator.

No mocks: every source is exercised against the REAL local CLI when it is
present (``shutil.which``), and asserted to degrade to an "unavailable" line
when it is absent. ``ps`` is effectively always present, so it is always
exercised for real.
"""

from __future__ import annotations

import shutil

from controlplane.backends.status.aggregator import (
    Snapshot,
    SourceReport,
    collect_snapshot,
    snapshot_docker,
    snapshot_kubernetes,
    snapshot_processes,
)
from controlplane.backends.status.plugin import get_capabilities
from controlplane.core import (
    CapabilityStatus,
    Registry,
    Router,
)


def test_processes_source_is_real_and_available() -> None:
    # ps is ~always present; exercise the real subprocess path.
    report = snapshot_processes()
    assert isinstance(report, SourceReport)
    assert report.name == "processes"
    if shutil.which("ps"):
        assert report.available is True
        assert report.error is None
        # A live process listing is never empty.
        assert report.summary
    else:  # pragma: no cover - ps virtually always exists
        assert report.available is False


def test_docker_source_degrades_or_reports_real() -> None:
    report = snapshot_docker()
    assert report.name == "docker"
    if shutil.which("docker") is None:
        assert report.available is False
        assert "unavailable" in report.summary.lower()
    else:
        # Real call: either it lists containers or surfaces a real error,
        # but it must never raise.
        assert isinstance(report.summary, str)


def test_kubernetes_source_degrades_or_reports_real() -> None:
    report = snapshot_kubernetes()
    assert report.name == "kubernetes"
    if shutil.which("kubectl") is None:
        assert report.available is False
        assert "unavailable" in report.summary.lower()
    else:
        assert isinstance(report.summary, str)


def test_collect_snapshot_combines_all_sources() -> None:
    snap = collect_snapshot()
    assert isinstance(snap, Snapshot)
    names = {r.name for r in snap.reports}
    assert {"docker", "kubernetes", "processes"} <= names
    text = snap.render()
    assert "processes" in text.lower()
    # Unavailable sources are reported with a reason, never silently dropped.
    # The reason is "unavailable" when the tool is missing, or the tool's real
    # error (e.g. kubectl with no reachable cluster) when it is present.
    for report in snap.reports:
        if not report.available:
            assert report.summary.strip()


def test_capability_is_working_with_status_keywords() -> None:
    caps = get_capabilities()
    assert len(caps) == 1
    cap = caps[0]
    assert cap.name == "status"
    assert cap.status is CapabilityStatus.WORKING
    for kw in ("what's running", "whats running", "status", "overview"):
        assert kw in cap.keywords


def test_routing_reaches_status_capability() -> None:
    result = Router(Registry()).route("what's running")
    assert result.handled is True
    assert result.text
    assert "processes" in result.text.lower()
