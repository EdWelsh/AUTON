"""Tests for the registry-driven capability help listing (Unit 13)."""

from __future__ import annotations

from controlplane.core import Capability, CapabilityResult, CapabilityStatus, Registry
from controlplane.core.help import capabilities_table, format_capabilities


def _noop(_text: str) -> CapabilityResult:
    return CapabilityResult.ok("ok")


def _mixed_registry() -> Registry:
    caps = [
        Capability(
            name="docker",
            keywords=("docker",),
            status=CapabilityStatus.WORKING,
            note="run containers",
            handler=_noop,
        ),
        Capability(
            name="kubernetes",
            keywords=("k8s", "kube"),
            status=CapabilityStatus.ROADMAP,
            note="orchestrate pods",
        ),
        Capability(
            name="firefox",
            keywords=("firefox",),
            status=CapabilityStatus.WORKING,
            note="launch the browser",
            handler=_noop,
        ),
        # Duplicate display name — must collapse to the first seen.
        Capability(
            name="docker",
            keywords=("container",),
            status=CapabilityStatus.WORKING,
            note="SHOULD NOT APPEAR",
            handler=_noop,
        ),
    ]
    return Registry(caps)


def test_format_includes_every_unique_name_and_note() -> None:
    out = format_capabilities(_mixed_registry())

    assert "docker — run containers" in out
    assert "kubernetes — orchestrate pods" in out
    assert "firefox — launch the browser" in out


def test_format_dedupes_by_name() -> None:
    out = format_capabilities(_mixed_registry())

    # The duplicate "docker" capability collapses to a single listing line.
    # (A plain count("docker") is unreliable: the footer hint also says "docker".)
    assert out.count("docker — run containers") == 1
    assert "SHOULD NOT APPEAR" not in out


def test_format_marks_status() -> None:
    out = format_capabilities(_mixed_registry())

    assert "✓ ready" in out
    assert "… roadmap" in out


def test_ready_first_orders_working_before_roadmap() -> None:
    out = format_capabilities(_mixed_registry(), ready_first=True)

    # Both WORKING capabilities should appear before the ROADMAP one.
    assert out.index("docker") < out.index("kubernetes")
    assert out.index("firefox") < out.index("kubernetes")


def test_ready_first_false_preserves_discovery_order() -> None:
    out = format_capabilities(_mixed_registry(), ready_first=False)

    # Discovery order is docker, kubernetes, firefox (dup docker dropped).
    assert out.index("docker") < out.index("kubernetes") < out.index("firefox")


def test_header_and_footer_present() -> None:
    out = format_capabilities(_mixed_registry())
    lines = out.splitlines()

    assert lines[0].strip() != ""  # a header line
    assert "run nginx in docker" in out
    assert "launch firefox" in out


def test_empty_registry_is_graceful() -> None:
    out = format_capabilities(Registry([]))

    assert isinstance(out, str)
    assert out  # non-empty, no crash
    assert "run nginx in docker" in out  # footer hint still present


def test_capabilities_table_shape() -> None:
    rows = capabilities_table(_mixed_registry())

    assert [r["name"] for r in rows] == ["docker", "kubernetes", "firefox"]
    docker_row = rows[0]
    assert docker_row["status"] == "working"
    assert docker_row["ready"] is True
    assert docker_row["note"] == "run containers"
    assert docker_row["marker"] == "✓ ready"

    kube_row = rows[1]
    assert kube_row["ready"] is False
    assert kube_row["marker"] == "… roadmap"
