"""scripts/campaign.py stops on a harness failure instead of spending attempts (w18)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "campaign.py"
spec = importlib.util.spec_from_file_location("campaign", SCRIPT)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def _result(seconds, rcs):
    return {"sessions": [{"seconds": seconds}], "gates": [{"rc": rc} for rc in rcs]}


def test_not_generated_in_minutes_is_a_harness_failure():
    assert campaign.harness_suspect(_result(374, [2, 2, 2]))


def test_not_generated_after_real_work_is_a_result():
    assert not campaign.harness_suspect(_result(4 * 18000, [2, 2, 2]))


def test_generated_wrong_quickly_is_still_a_result():
    assert not campaign.harness_suspect(_result(300, [1, 2]))


def _pmset(monkeypatch, stdout=None, raises=None):
    def fake(*_a, **_k):
        if raises:
            raise raises
        return type("R", (), {"stdout": stdout})()
    monkeypatch.setattr(campaign.subprocess, "run", fake)


def test_battery_power_is_reported(monkeypatch):
    _pmset(monkeypatch, "Now drawing from 'Battery Power'\n -InternalBattery-0 80%")
    assert campaign.on_battery() is True


def test_ac_power_is_not_battery(monkeypatch):
    _pmset(monkeypatch, "Now drawing from 'AC Power'\n")
    assert campaign.on_battery() is False


def test_no_pmset_means_unknown_not_a_warning(monkeypatch):
    _pmset(monkeypatch, raises=FileNotFoundError())
    assert campaign.on_battery() is None
    _pmset(monkeypatch, "garbage")
    assert campaign.on_battery() is None


def test_a_tree_where_every_gate_said_not_generated_is_not_a_base():
    assert not campaign.generated_something({"gates": [{"rc": 2}, {"rc": 2}]})
    assert campaign.generated_something({"gates": [{"rc": 2}, {"rc": 1}]})
    assert not campaign.generated_something(None)
