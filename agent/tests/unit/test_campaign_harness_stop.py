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
