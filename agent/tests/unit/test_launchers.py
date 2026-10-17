"""scripts/slm_run.py and scripts/vendor_research.py: bounded children, the operator's config,
and `collect` counting each file once."""

from __future__ import annotations

import importlib.util
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str):
    # Not as `vendor_research`: that name is agent/tools/vendor_research, which the launcher imports.
    spec = importlib.util.spec_from_file_location(f"{name}_launcher", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


slm_run = _load("slm_run")
vendor_research = _load("vendor_research")
LAUNCHERS = [slm_run, vendor_research]

# A stand-in for orchestrator.cli: pauses (writes the marker, exits 0) on SIGTERM, as the engine does.
CHILD = ("import signal, sys, time\n"
         "def pause(*_):\n"
         "    open(sys.argv[1], 'w').write('paused')\n"
         "    sys.exit(0)\n"
         "signal.signal(signal.SIGTERM, pause)\n"
         "open(sys.argv[2], 'w').write('ready')\n"
         "time.sleep(120)\n")


def _child(tmp_path: Path) -> tuple[list[str], Path, Path]:
    marker, ready = tmp_path / "paused", tmp_path / "ready"
    return [sys.executable, "-c", CHILD, str(marker), str(ready)], marker, ready


@pytest.mark.parametrize("launcher", LAUNCHERS, ids=lambda m: m.__name__)
def test_the_time_limit_pauses_the_child(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "GRACE", 10)
    cmd, marker, _ = _child(tmp_path)
    with open(tmp_path / "log", "w") as log:
        assert launcher.run_bounded(cmd, tmp_path, log, 2) == 124
    assert marker.read_text() == "paused"


@pytest.mark.parametrize("launcher", LAUNCHERS, ids=lambda m: m.__name__)
def test_ctrl_c_pauses_the_child_instead_of_orphaning_it(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "GRACE", 10)
    cmd, marker, ready = _child(tmp_path)

    def interrupt():
        while not ready.exists():
            threading.Event().wait(0.05)
        os.kill(os.getpid(), signal.SIGINT)        # the launcher's Ctrl-C

    t = threading.Thread(target=interrupt)
    t.start()
    with open(tmp_path / "log", "w") as log:
        assert launcher.run_bounded(cmd, tmp_path, log, 60) == 130
    t.join()
    assert marker.read_text() == "paused"


@pytest.mark.parametrize("launcher", LAUNCHERS, ids=lambda m: m.__name__)
def test_a_child_that_ignores_the_pause_is_killed_after_the_grace(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "GRACE", 1)
    cmd = [sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                                 "time.sleep(120)"]
    with open(tmp_path / "log", "w") as log:
        assert launcher.run_bounded(cmd, tmp_path, log, 1) == 124


def _start(launcher, tmp_path, monkeypatch, **extra):
    monkeypatch.setattr(launcher, "OUT", tmp_path / "out")
    (tmp_path / "out" / "r" / "kernel").mkdir(parents=True)   # slm_run: no kernel-base.sh
    seen = {}
    monkeypatch.setattr(launcher, "config_template", lambda: ROOT / "agent/config/auton.toml.example")
    monkeypatch.setattr(launcher, "run_bounded",
                        lambda cmd, cwd, log, seconds: seen.update(cmd=cmd, seconds=seconds) or 0)
    args = SimpleNamespace(name="r", resume=False, goal="g", model="m", base="kernel-base-v5",
                           timeout=77, scouts=1, readers=1, **extra)
    assert launcher.start(args) == 0
    return seen


@pytest.mark.parametrize("launcher", LAUNCHERS, ids=lambda m: m.__name__)
def test_start_needs_no_coreutils_timeout(launcher, tmp_path, monkeypatch):
    seen = _start(launcher, tmp_path, monkeypatch)
    assert seen["seconds"] == 77
    assert "timeout" not in seen["cmd"][0] and seen["cmd"][1:3] == ["-m", "orchestrator.cli"]


TOML = """model = "anthropic/claude-opus-4-6"
developer_count = 4
specialists = "all"
[llm.api_keys]
anthropic = "sk-ant-operator"
[workspace]
path = "../kernels/x86_64"
research = false
mode = "kernel_build"
kernel_tree = ""
"""


@pytest.mark.parametrize("launcher", LAUNCHERS, ids=lambda m: m.__name__)
def test_the_operators_auton_toml_is_the_template(launcher, tmp_path, monkeypatch):
    own, example = tmp_path / "auton.toml", tmp_path / "auton.toml.example"
    example.write_text(TOML.replace("sk-ant-operator", ""))
    monkeypatch.setattr(launcher, "TEMPLATES", (own, example))
    assert launcher.config_template() == example
    own.write_text(TOML)
    assert launcher.config_template() == own
    run = tmp_path / "run"
    run.mkdir()
    cfg = (launcher.config(run, "claude-cli/x", "kernel-base-v5") if launcher is slm_run
           else launcher.config(run, "claude-cli/x", 2, 3)).read_text()
    assert 'anthropic = "sk-ant-operator"' in cfg and 'model = "claude-cli/x"' in cfg
    assert f'path = "{run / "ws"}"' in cfg and "specialists = false" in cfg


@pytest.mark.parametrize("launcher", LAUNCHERS, ids=lambda m: m.__name__)
def test_a_template_missing_a_patched_key_fails_loudly(launcher, tmp_path, monkeypatch):
    own = tmp_path / "auton.toml"
    own.write_text("\n".join(l for l in TOML.splitlines() if not l.startswith("specialists")))
    monkeypatch.setattr(launcher, "TEMPLATES", (own,))
    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(SystemExit, match="specialists"):
        launcher.config(run, "m", "b") if launcher is slm_run else launcher.config(run, "m", 1, 1)


def _git(ws: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(ws), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


def test_collect_counts_a_merged_file_once(tmp_path, monkeypatch, capsys):
    ws = tmp_path / "t1" / "ws"
    (ws / "hardware" / "proposals").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(ws)], check=True)
    (ws / "hardware" / "proposals" / "zzz.yaml").write_text("vendor: zzz\n")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-q", "-m", "proposal")
    _git(ws, "branch", "agent/scout-01/x")
    _git(ws, "branch", "agent/scout-02/y")
    _git(ws, "checkout", "-q", "agent/scout-02/y")
    (ws / "hardware" / "proposals" / "zzz.yaml").write_text("vendor: zzz\nchanged: true\n")
    _git(ws, "commit", "-q", "-am", "a different version")
    monkeypatch.setattr(vendor_research, "OUT", tmp_path)
    vendor_research.collect(SimpleNamespace(name="t1"))
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.startswith(("PASS", "FAIL"))]
    assert len(lines) == 2, out                    # main's version (on two branches) and scout-02's
    assert lines[0].endswith("main:hardware/proposals/zzz.yaml  (also on agent/scout-01/x)")
    assert "agent/scout-02/y:hardware/proposals/zzz.yaml" in lines[1]
    counts = re.search(r"(\d+) pass, (\d+) fail", out)
    assert int(counts[1]) + int(counts[2]) == 2
