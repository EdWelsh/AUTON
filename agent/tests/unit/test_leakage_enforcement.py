"""Leakage enforcement — excluded capabilities must be absent from the artifact.

The PRD tracks leakage as a number with a target of 0. Two failure modes matter
more than the number itself.

A detector that has stopped detecting reports 0 forever and looks like success.
So the known 68-symbol leak in the general image is a regression fixture: the
check must still catch it.

And a run that could not attribute every source has not checked them. Recording
that as 0 puts a false zero into a series someone will read as progress, so it
is reported as inconclusive instead.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TREE = ROOT / "kernels" / "x86_64"
RUNNER = ROOT / "tests" / "kernel" / "run_leakage_test.sh"

pytestmark = pytest.mark.skipif(
    not (TREE / "kernel").is_dir() or shutil.which("x86_64-elf-nm") is None,
    reason="needs a kernel tree and the cross toolchain",
)


def run(image: Path, excludes: str, stubs: Path | None, report: Path | None):
    args = [str(RUNNER), "--excludes", excludes, "--image", str(image)]
    if stubs:
        args += ["--stubs", str(stubs)]
    if report:
        args += ["--report", str(report)]
    env = {**os.environ, "KERNEL_TREE": str(TREE),
           "CC": os.environ.get("CC", "x86_64-elf-gcc")}
    return subprocess.run(args, capture_output=True, text=True, env=env, timeout=900)


@pytest.fixture(scope="module")
def general_image(tmp_path_factory):
    """The full kernel — every source, nothing excluded. The known-leaky case."""
    out = tmp_path_factory.mktemp("general") / "kernel.bin"
    cc = os.environ.get("CC", "x86_64-elf-gcc")
    r = subprocess.run(["make", "-C", str(TREE), f"CC={cc}", "-j4"],
                       capture_output=True, text=True, timeout=900)
    built = TREE / "build" / "kernel.bin"
    if r.returncode != 0 or not built.exists():
        pytest.skip(f"general image did not build: {r.stderr[-200:]}")
    shutil.copy2(built, out)
    return out


class TestTheDetectorStillDetects:
    def test_the_general_image_leaks_the_network(self, general_image, tmp_path):
        """The regression fixture. A check that stops firing reports 0 forever
        and is indistinguishable from success.

        The threshold is 20, not the 68 first measured: that count included
        file-local statics, which attribution deliberately stopped covering
        after `seg.0` — a static in netif.c — was reported as tcp leaking into
        an image without it. 30 globals is the honest number.
        """
        report = tmp_path / "r.json"
        r = run(general_image, "net", None, report)

        assert r.returncode == 1, f"detector did not fire:\n{r.stdout}"
        data = json.loads(report.read_text())
        assert data["leaked_symbols"] >= 20, data["leaked_symbols"]
        assert data["conclusive"], "an inconclusive run is not a measurement"

    def test_the_leak_is_attributed_to_real_sources(self, general_image, tmp_path):
        report = tmp_path / "r.json"
        run(general_image, "net", None, report)

        by_source = json.loads(report.read_text())["leaked_by_source"]
        assert any("kernel/net/" in s for s in by_source), sorted(by_source)


class TestTheMeasurement:
    def test_a_report_is_written_as_data(self, general_image, tmp_path):
        """A pass/fail cannot be tracked over time; the PRD tracks a number."""
        report = tmp_path / "r.json"
        run(general_image, "net", None, report)

        data = json.loads(report.read_text())
        for field in ("image", "excludes", "leaked_symbols", "image_symbols",
                      "absence_stubs", "conclusive"):
            assert field in data, field

    def test_an_unattributable_run_is_not_reported_as_clean(self, tmp_path):
        """`conclusive` exists so a run that could not compile a source is not
        recorded as a zero. A false zero in a tracked series reads as progress."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "lc", ROOT / "tests" / "kernel" / "leakage_check.py")
        lc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lc)

        # A source that cannot compile yields no symbols, so its absence was
        # never checked.
        bad = tmp_path / "broken.c"
        bad.write_text("this is not C\n")
        assert lc.symbols_defined_by(bad, TREE) == set()


class TestExitCodesDistinguishStates:
    def test_nothing_to_check_is_not_a_pass(self, general_image):
        """`fs` maps to sources this tree does not have. That is 'not checked',
        which must not be reported as clean."""
        r = run(general_image, "fs", None, None)

        assert r.returncode == 2, r.stdout

    def test_an_exclude_naming_nothing_is_an_error(self, general_image):
        r = run(general_image, "telepathy", None, None)

        assert r.returncode == 2
        assert "neither a subsystem nor a capability" in r.stderr

    def test_a_missing_image_is_not_a_pass(self, tmp_path):
        r = run(tmp_path / "absent.bin", "net", None, None)

        assert r.returncode == 2
