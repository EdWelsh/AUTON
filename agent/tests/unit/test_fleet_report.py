"""Fleet conformance reports (H10e): what may leave a machine, and what may not.

This is the one place in the project where data would move off a user's
machine, so the schema is an allowlist and these tests are about refusals.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from fleet_report import (ALLOWED, ReportError, aggregate, from_verdicts,  # noqa: E402
                          report_text, serialise)

GOOD = {"silicon": "6:151:2", "vendor": "GenuineIntel", "virtualised": 0,
        "suite": "abc123", "checked": 22, "divergences": [], "not_assertable": []}


def test_a_well_formed_report_serialises():
    out = serialise(dict(GOOD))
    assert out["schema"] == 1 and out["silicon"] == "6:151:2"
    assert set(out) <= set(ALLOWED)


def test_a_mac_address_is_refused_by_name():
    with pytest.raises(ReportError, match="MAC address"):
        serialise({**GOOD, "mac_address": "00:11:22:33:44:55"})


@pytest.mark.parametrize("field", ["hostname", "ip_address", "board_serial",
                                   "machine_uuid", "username", "install_path"])
def test_every_identifying_field_is_refused(field):
    with pytest.raises(ReportError, match="refusing to include"):
        serialise({**GOOD, field: "x"})


def test_a_field_nobody_considered_is_refused():
    """The allowlist's whole purpose: a denylist ships the first thing somebody
    forgot to think of."""
    with pytest.raises(ReportError, match="allowlist"):
        serialise({**GOOD, "browser_history": "..."})


def test_a_report_that_cannot_be_grouped_by_part_is_refused():
    with pytest.raises(ReportError, match="family:model:stepping"):
        serialise({**GOOD, "silicon": "12th Gen Core i7"})


def test_a_report_is_built_from_the_same_verdicts_the_user_saw():
    verdicts = ("IDENTITY GenuineIntel 6:151:2 x86_64 12th Gen Core i7\n"
                "OK fp-div-one-third 3fd5555555555555\n"
                "DIVERGE fp-div-fdiv-historical got 3ff5575400000000 want 3ff557541c7c6b43\n"
                "NOT-ASSERTABLE ud-control-nop wanted none, faulted\n")
    r = from_verdicts(verdicts, suite="rev1")
    assert r["silicon"] == "6:151:2" and r["vendor"] == "GenuineIntel"
    assert r["checked"] == 3 and len(r["divergences"]) == 1
    assert r["divergences"][0]["id"] == "fp-div-fdiv-historical"
    assert "FDIV" in r["divergences"][0]["clause"] or "IEEE" in r["divergences"][0]["clause"]
    assert r["not_assertable"] == ["ud-control-nop"]
    assert set(r) <= set(ALLOWED)


def test_a_virtualised_machine_is_marked():
    verdicts = "IDENTITY GenuineIntel 6:151:2 x86_64 QEMU Virtual CPU hypervisor\nOK x\n"
    assert from_verdicts(verdicts)["virtualised"] == 1


class TestTheAggregator:
    def _r(self, silicon="6:151:2", virt=0, diverged=("fp-div-fdiv-historical",)):
        return {"schema": 1, "silicon": silicon, "vendor": "GenuineIntel",
                "virtualised": virt, "checked": 22,
                "divergences": [{"id": d, "clause": "c", "expected": "a", "observed": "b"}
                                for d in diverged],
                "not_assertable": []}

    def test_divergences_are_counted_per_part(self):
        aggs = aggregate([self._r(), self._r(), self._r(diverged=())])
        a = aggs["6:151:2"]
        assert a.machines == 3 and a.by_entry["fp-div-fdiv-historical"] == 2

    def test_a_virtualised_divergence_never_counts(self):
        """It is the hypervisor's, and counting it would manufacture a fleet
        signal out of emulation."""
        aggs = aggregate([self._r(virt=1), self._r(virt=1), self._r()])
        a = aggs["6:151:2"]
        assert a.machines == 3 and a.virtualised == 2 and a.real_machines == 1
        assert a.by_entry["fp-div-fdiv-historical"] == 1

    def test_the_rate_is_over_real_machines_only(self):
        text = report_text(aggregate([self._r(), self._r(virt=1)]))
        assert "1 of 1 machines (100.0%)" in text
        assert "1 virtualised" in text

    def test_parts_are_kept_apart(self):
        aggs = aggregate([self._r(), self._r(silicon="6:158:10", diverged=())])
        assert set(aggs) == {"6:151:2", "6:158:10"}
        assert "no divergences on metal" in report_text(aggs)


def test_the_module_sends_nothing():
    """There is no endpoint, by decision (kernel_spec/decisions/fleet-endpoint.md).
    A module that imports a network client is a module that can be made to use
    one by a later edit nobody reviews."""
    source = (ROOT / "agent" / "tools" / "fleet_report.py").read_text()
    for banned in ("import requests", "import httpx", "urllib.request", "socket.",
                   "http.client", "urlopen("):
        assert banned not in source, f"{banned} appears in a tool that must not send"


def test_the_endpoint_question_is_written_down():
    text = (ROOT / "agent" / "kernel_spec" / "decisions" / "fleet-endpoint.md").read_text()
    for required in ("retention", "jurisdiction", "abuse"):
        assert required in text.lower(), f"the decision record does not mention {required}"


def test_the_consent_flow_is_specified_with_a_default_of_no():
    """The spec is the contract an image is graded against; if it does not say
    the default is no, an implementation defaulting to yes would pass review."""
    spec = (ROOT / "agent" / "kernel_spec" / "subsystems" / "slm.md").read_text()
    section = spec.split("## Sharing a conformance report")[1].split("\n## ")[0]
    assert "[y/N]" in section, "the prompt must show which answer is the default"
    assert "default is no" in section.lower()
    assert "shown before the question is answered" in section
    assert "[CONF] not shared" in section
    for forbidden in ("hostname", "serial number", "user"):
        assert forbidden in section, f"the spec should name {forbidden} as excluded"
