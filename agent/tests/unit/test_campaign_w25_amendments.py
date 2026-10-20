"""The w25 amendments as data: R8 is not re-run, and no fallback tree is the untouched base."""

from __future__ import annotations

import importlib.util
import json
import subprocess

import pytest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("campaign_w25", ROOT / "scripts" / "campaign.py")
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def _git(ws: Path, *args: str, email: str = "agent@auton.local") -> None:
    subprocess.run(["git", "-C", str(ws), "-c", f"user.email={email}", "-c", "user.name=t",
                    *args], check=True, capture_output=True)


def _base_tree(ws: Path, seed: bool = True) -> None:
    """What generation_run.make_base leaves: kernel-base.sh's commit, then the seed's."""
    ws.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(ws)], check=True)
    (ws / "kernel_main.c").write_text('kprintf("[MM] PMM initialized");\n')
    _git(ws, "add", "-A")
    _git(ws, "commit", "-q", "-m", "base: kernel-base-v5", email="base@auton")
    if seed:
        (ws / "mm_ref.h").write_text("/* frozen */\n")
        _git(ws, "add", "-A")
        _git(ws, "commit", "-q", "-m", "seed", email="auton@local")


def _model_commit(ws: Path) -> None:
    (ws / "pmm.c").write_text("int pmm_alloc(void) { return 0; }\n")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-q", "-m", "PMM")


def _finished(d: Path, rcs, base="kernel-base-v5"):
    (d / "RESULT.json").write_text(json.dumps(
        {"finished": "x", "base": base, "sessions": [], "gates": [{"rc": rc} for rc in rcs]}))


def test_an_untouched_base_is_not_a_changed_tree(tmp_path):
    _base_tree(tmp_path / "ws")
    assert not campaign.tree_changed(tmp_path / "ws", {"base": "kernel-base-v5"})
    _model_commit(tmp_path / "ws")
    assert campaign.tree_changed(tmp_path / "ws", {"base": "kernel-base-v5"})


def test_a_tree_built_on_an_earlier_run_counts_only_its_own_work(tmp_path):
    up = tmp_path / "r1" / "ws"
    _base_tree(up)
    _model_commit(up)                               # R1's work, not R2's
    ws = tmp_path / "r2" / "ws"
    subprocess.run(["git", "clone", "-q", "--branch", "main", str(up), str(ws)], check=True)
    assert not campaign.tree_changed(ws, {"base": str(up)})
    (ws / "fat32.c").write_text("int fat32_mount(void) { return 0; }\n")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-q", "-m", "FAT32")
    assert campaign.tree_changed(ws, {"base": str(up)})


def test_a_fallback_that_passed_only_on_the_untouched_base_is_not_a_base(tmp_path, monkeypatch):
    """w25: both R1 attempts at gates [2, 2, 0], the boot marker printed by the base itself."""
    monkeypatch.setattr(campaign, "OUT", tmp_path)
    for k in (1, 2):
        _base_tree(tmp_path / f"r1-attempt{k}" / "ws")
        _finished(tmp_path / f"r1-attempt{k}", [2, 2, 0])
    runs = {"r1": {"name": "r1", "base": "kernel-base-v5", "fallback": "tree:r1-attempt2"},
            "r2": {"name": "r2", "base": "run:r1"}}
    with pytest.raises(campaign.Blocked):
        campaign.base_for(runs["r2"], runs)
    _model_commit(tmp_path / "r1-attempt2" / "ws")
    args, note = campaign.base_for(runs["r2"], runs)
    assert args == ["--base-tree", str(tmp_path / "r1-attempt2" / "ws")] and "fallback" in note


def test_runs_yaml_skips_r8_and_names_no_r1_fallback_tree():
    runs = {r["name"]: r for r in yaml.safe_load((ROOT / "docs/campaign/runs.yaml").read_text())["runs"]}
    assert runs["r8-virtio-console"].get("skip")
    assert str(runs["r1-mm"].get("fallback")) == "none"


def test_the_campaign_does_not_start_a_skipped_run(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign, "OUT", tmp_path)
    monkeypatch.setattr(campaign, "preflight", lambda: None)
    started = []
    monkeypatch.setattr(campaign, "run_one", lambda run, runs, spec: started.append(run["name"]))
    assert campaign.main([]) == 0
    assert "r8-virtio-console" not in started and started[0] == "r1-mm"
    assert "r8-virtio-console: skipped" in (tmp_path / "campaign.log").read_text()
