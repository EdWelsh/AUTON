"""Tests for the acceptance-marker evaluator (kernel_spec/tests/acceptance_tests.py).

Exercises the serial-matching/gating logic without booting QEMU.
"""

import importlib.util
from pathlib import Path

import pytest

_AT_PATH = (
    Path(__file__).resolve().parents[2]
    / "kernel_spec" / "tests" / "acceptance_tests.py"
)
_spec = importlib.util.spec_from_file_location("auton_acceptance_tests", _AT_PATH)
at = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(at)


GOOD_SERIAL = "\n".join(
    [
        "AUTON Kernel booting",
        "[BOOT] Multiboot2 magic valid",
        "[BOOT] Long mode enabled",
        "[BOOT] 64-bit GDT loaded",
        "[BOOT] Interrupts initialized",
        "[BOOT] Hardware summary: 127 MB RAM",
        "[DRV] Serial 16550 initialized",
        "[MM] PMM initialized: 32639 pages free",
        "[SCHED] Scheduler initialized",
        "[DEV] PCI scan: 4 devices found",
        "[SLM] Rule engine initialized",
        "[SLM] Hardware scan complete: 4 devices",
        "[SLM] Loaded driver: e1000",
        "[SLM] Ready",
        "[BOOT] OK",
    ]
)


def test_good_serial_passes_core_gate():
    results = at.evaluate(GOOD_SERIAL, "x86_64")
    assert results["ok"] is True
    assert not results["boot"]["failed"]  # all boot markers present


def test_full_boot_to_slm_recognized():
    test = next(t for t in at.INTEGRATION_TESTS if t.name == "full_boot_to_slm")
    assert at.test_passes(test, GOOD_SERIAL)


def test_missing_slm_ready_fails_gate():
    serial = GOOD_SERIAL.replace("[SLM] Ready", "")
    results = at.evaluate(serial, "x86_64")
    assert results["ok"] is False


def test_empty_serial_fails_gate():
    results = at.evaluate("", "x86_64")
    assert results["ok"] is False
    assert results["boot"]["passed"] == []


def test_agent_extended_groups_are_partial_not_fatal():
    """fs/net markers absent from the seed must not break the core gate."""
    results = at.evaluate(GOOD_SERIAL, "x86_64")
    assert results["ok"] is True
    assert len(results["fs"]["passed"]) < results["fs"]["total"]


@pytest.mark.parametrize("name", at.CORE_GATE_TESTS)
def test_core_gate_tests_exist(name):
    all_names = {t.name for ts in at.get_all_tests("x86_64").values() for t in ts}
    assert name in all_names
