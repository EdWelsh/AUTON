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


# --- Canonical marker sets (consumed by the shell harnesses) ---------------


class TestSerialMarkerSets:
    """Guards the single source of truth the shell harnesses read.

    scripts/lib/markers.sh asks acceptance_tests.py for these lists rather than
    restating them. That only holds if the sets stay tied to real tests, so a
    pattern deleted from a test can never leave a marker set silently pointing
    at nothing.
    """

    def test_every_marker_is_owned_by_a_real_test(self):
        owned = at.all_test_patterns("x86_64")
        for set_name, patterns in at.SERIAL_MARKER_SETS.items():
            for pattern in patterns:
                assert pattern in owned, (
                    f"marker set {set_name!r} lists {pattern!r}, which no "
                    f"AcceptanceTest claims — the shell would check a marker "
                    f"nothing defines"
                )

    def test_boot_set_matches_a_healthy_boot(self):
        import re

        for pattern in at.marker_patterns("boot"):
            assert re.search(pattern, GOOD_SERIAL), (
                f"{pattern!r} does not match the known-good serial log"
            )

    def test_marker_patterns_rejects_an_unknown_set(self):
        with pytest.raises(KeyError, match="unknown marker set"):
            at.marker_patterns("no-such-set")

    def test_sets_are_non_empty(self):
        # An empty set would make a harness report a vacuous pass.
        for set_name, patterns in at.SERIAL_MARKER_SETS.items():
            assert patterns, f"marker set {set_name!r} is empty"

    def test_boot_set_has_no_duplicates(self):
        patterns = at.marker_patterns("boot")
        assert len(patterns) == len(set(patterns))

    def test_list_patterns_cli_emits_one_per_line(self, capsys):
        rc = at.main(["--list-patterns", "boot"])
        assert rc == 0
        out = capsys.readouterr().out.splitlines()
        assert out == list(at.marker_patterns("boot"))

    def test_list_patterns_cli_rejects_unknown_set(self, capsys):
        rc = at.main(["--list-patterns", "nope"])
        assert rc == 2
        assert "unknown marker set" in capsys.readouterr().err
