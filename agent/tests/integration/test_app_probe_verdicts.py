"""All three verdicts, from outside real containers (A10).

WORKED on the packaged flask app; FAILED when the same app is packaged without
its dependency (the probe can fail — the first ablation step, by hand); and
HONESTLY REFUSED when the application says what it lacks and stops.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from package_gate import load_bases  # noqa: E402

SUBJECT = ROOT / "agent" / "tests" / "fixtures" / "apps" / "flask-hello"
PROBE = ROOT / "agent" / "tests" / "fixtures" / "probes" / "flask-hello.yaml"
BASE = load_bases()["runtime:python-3.12"]


def _docker_ok() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "info"], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="no Docker daemon")


def _image(tmp_path, recipe: str, tag: str) -> str:
    ctx = tmp_path / tag
    shutil.copytree(SUBJECT, ctx)
    (ctx / "Dockerfile").write_text(recipe.format(base=BASE))
    subprocess.run(["docker", "build", "-q", "-t", tag, str(ctx)], check=True,
                   capture_output=True)
    return tag


def _probe(*args):
    return subprocess.run([sys.executable, str(ROOT / "agent/tools/app_probe.py"), *args],
                          capture_output=True, text=True, timeout=300)


FULL = """FROM {base}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
CMD ["python", "app.py"]
"""
NO_FLASK = """FROM {base}
WORKDIR /app
COPY app.py .
CMD ["python", "app.py"]
"""
REFUSES = """FROM {base}
CMD ["python", "-c", "print('AUTON-REFUSED: needs lib:libpq.so.5, which this image lacks')"]
"""


def test_worked(tmp_path):
    r = _probe("--image", _image(tmp_path, FULL, "auton-probe-test-full"), "--probe", str(PROBE))
    assert r.returncode == 0 and r.stdout.startswith("WORKED"), r.stdout + r.stderr


def test_failed_when_a_dependency_is_missing(tmp_path):
    spec = tmp_path / "fast.yaml"
    spec.write_text(PROBE.read_text().replace("start_timeout_s: 60", "start_timeout_s: 10"))
    r = _probe("--image", _image(tmp_path, NO_FLASK, "auton-probe-test-noflask"),
               "--probe", str(spec))
    assert r.returncode == 1 and r.stdout.startswith("FAILED"), r.stdout
    assert "ModuleNotFoundError" in r.stdout


def test_honestly_refused(tmp_path):
    r = _probe("--image", _image(tmp_path, REFUSES, "auton-probe-test-refuses"),
               "--probe", str(PROBE))
    assert r.returncode == 2 and r.stdout.startswith("HONESTLY REFUSED")
    assert "libpq" in r.stdout


def test_the_script_branch_takes_an_image_and_a_probe(tmp_path):
    tag = _image(tmp_path, FULL, "auton-probe-test-full")
    r = subprocess.run(["bash", str(ROOT / "scripts/run-intent-probe.sh"), "app", tag,
                        str(PROBE)], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and "WORKED" in r.stdout, r.stdout + r.stderr
    r = subprocess.run(["bash", str(ROOT / "scripts/run-intent-probe.sh"), "app", tag],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "probe.yaml" in r.stderr
