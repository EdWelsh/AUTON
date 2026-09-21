"""Running what a driver record's `verification` promises.

V2 made the field mandatory and mechanical. Nothing ran it, and a field that is
mandatory and unchecked is worse than an absent one — it reads as a guarantee.

The state these tests exist to protect is the third one. `virtio-net.md` names a
command that does not exist, because the driver does not exist. Treating that as
a failure blocks every build touching a planned driver; treating it as a pass is
exactly the lie the field was created to prevent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from build_service import GateFailure  # noqa: E402
from driver_verify import (  # noqa: E402
    Outcome,
    drivers_for_target,
    gate,
    verify,
)
from target_spec import load  # noqa: E402

TARGETS = ROOT / "agent" / "kernel_spec" / "targets"
QEMU = TARGETS / "qemu-pc.md"
FIRECRACKER = TARGETS / "firecracker.md"

BOOT_LOG = """\
[BOOT] OK
[SLM] Loaded driver: e1000
[NET] dhcp bound
"""


@pytest.fixture
def isolated_evidence(tmp_path, monkeypatch):
    """Evidence is per-checkout. A test must not read or write the real one."""
    import driver_verify

    monkeypatch.setattr(driver_verify, "EVIDENCE", tmp_path / "evidence.json")
    return tmp_path / "evidence.json"


class TestOnlyTheDriversThisImageContains:
    def test_the_join_is_from_the_target(self):
        """Verifying every record in kernel_spec/drivers/ would check drivers
        this image does not contain, and the pass would mean nothing."""
        applicable, _ = drivers_for_target(load(QEMU))

        assert [r.driver for r in applicable] == ["e1000"]

    def test_a_different_target_yields_a_different_driver(self):
        applicable, _ = drivers_for_target(load(FIRECRACKER))

        assert "virtio-net" in [r.driver for r in applicable]
        assert "e1000" not in [r.driver for r in applicable]

    def test_a_device_needing_a_driver_with_no_record_is_reported(self, tmp_path):
        """Silence there would hide a driver the image needs and nothing
        describes.

        Firecracker was this case — its storage device resolved to `virtio-blk`
        and no record existed — until V6 wrote one. The gap the join found is
        now closed, so the mechanism is exercised against a device whose driver
        still has no record."""
        target = tmp_path / "e1000e-box.md"
        target.write_text(
            "---\ntarget: e1000e-box\nclass: vm\narch: x86_64\n"
            "firmware: bios\nsilicon:\n  vendor: GenuineIntel\n  family: 6\n"
            "  model: 6\n  stepping: 3\n  source: probed\ndevices:\n"
            '  - id: "8086:10d3"\n    role: network\n    source: probed\n'
            "provenance:\n  stated_by: test\n---\n")

        _, undeclared = drivers_for_target(load(target))

        assert any("e1000e" in u for u in undeclared)

    def test_firecracker_no_longer_has_an_undeclared_driver(self):
        """V6 closed the gap V9's join surfaced."""
        _, undeclared = drivers_for_target(load(FIRECRACKER))

        assert undeclared == []

    def test_a_device_nothing_binds_to_is_not_reported(self):
        """QEMU's host bridge needs no driver. Reporting it would train a reader
        to ignore the list."""
        _, undeclared = drivers_for_target(load(QEMU))

        assert undeclared == []


class TestUnverifiedIsNotVerified:
    def test_a_named_but_absent_command_is_unverified(self, tmp_path, monkeypatch):
        """`status: specified` means the driver is not written. Its command not
        existing is the normal state, not a failure.

        Exercised against a synthetic path because V5 created
        `run_virtio_net_test.sh` — the situation this covers is now rarer in the
        tree, which does not make it less real."""
        import driver_verify

        monkeypatch.setattr(driver_verify, "ROOT", tmp_path)
        check = driver_verify._run_command("cmd: nowhere/absent.sh", slow=True)

        assert check.outcome is Outcome.UNVERIFIED
        assert "does not exist" in check.detail

    def test_virtio_nets_command_now_exists_and_reports_nothing_to_check(
            self, isolated_evidence):
        """V5 created it, and it exits 2 with no generated tree — `nothing to
        check`, which is neither a pass nor a failure."""
        report = verify(load(FIRECRACKER), slow=True)
        vn = next(d for d in report.drivers if d.driver == "virtio-net")
        cmd = next(c for c in vn.checks if c.kind == "cmd")

        assert cmd.outcome is Outcome.UNVERIFIED
        assert "nothing to check" in cmd.detail

    def test_a_marker_with_no_boot_log_is_unverified(self, isolated_evidence):
        """A marker can only be observed at boot. A gate that pretends otherwise
        either blocks every build or verifies nothing."""
        report = verify(load(QEMU))
        markers = [c for c in report.drivers[0].checks if c.kind == "marker"]

        assert markers
        assert all(c.outcome is Outcome.UNVERIFIED for c in markers)

    def test_a_marker_in_the_boot_log_is_verified(self, isolated_evidence):
        report = verify(load(QEMU), serial=BOOT_LOG)
        markers = [c for c in report.drivers[0].checks if c.kind == "marker"]

        assert all(c.outcome is Outcome.VERIFIED for c in markers)

    def test_a_marker_absent_from_the_boot_log_fails(self, isolated_evidence):
        report = verify(load(QEMU), serial="[BOOT] OK\n")
        markers = [c for c in report.drivers[0].checks if c.kind == "marker"]

        assert all(c.outcome is Outcome.FAILED for c in markers)

    def test_a_driver_is_not_verified_because_most_of_it_was(self, isolated_evidence):
        """The worst of its checks wins."""
        report = verify(load(QEMU), serial=BOOT_LOG)
        d = report.drivers[0]

        assert any(c.outcome is Outcome.VERIFIED for c in d.checks)
        assert d.outcome is Outcome.UNVERIFIED

    def test_three_outcomes_not_two(self):
        assert len(set(Outcome)) == 3

    def test_unverified_exits_nonzero(self, isolated_evidence, capsys):
        """Exit status is what a build script reads."""
        import driver_verify

        rc = driver_verify.main(["--target", str(FIRECRACKER)])
        capsys.readouterr()
        assert rc == 3


class TestASlowCommandIsSkippedNotFaked:
    def test_a_command_that_boots_an_image_is_skipped_by_default(self, isolated_evidence):
        """A gate that makes every service build boot QEMU is a gate people turn
        off, and a gate people turn off verifies nothing."""
        report = verify(load(QEMU))
        cmd = next(c for c in report.drivers[0].checks if c.kind == "cmd")

        assert cmd.outcome is Outcome.UNVERIFIED
        assert "--slow" in cmd.detail

    def test_skipping_is_unverified_never_verified(self, isolated_evidence):
        report = verify(load(QEMU))
        assert report.counts()["verified"] == 0


class TestEvidenceIsBoundToTheRecord:
    def test_a_recorded_pass_is_reused(self, isolated_evidence, monkeypatch):
        import driver_verify

        rec = next(r for r in drivers_for_target(load(QEMU))[0])
        h = driver_verify._sha256(rec.path)
        entry = next(e for e in rec.verification if e.startswith("cmd:"))
        driver_verify._remember(rec.driver, h, entry)

        report = verify(load(QEMU))
        cmd = next(c for c in report.drivers[0].checks if c.kind == "cmd")

        assert cmd.outcome is Outcome.VERIFIED
        assert "recorded pass" in cmd.detail

    def test_evidence_for_a_different_record_does_not_count(self, isolated_evidence):
        """A recorded pass against a different record says nothing about this
        claim — the verification may have been rewritten since."""
        import driver_verify

        rec = next(r for r in drivers_for_target(load(QEMU))[0])
        entry = next(e for e in rec.verification if e.startswith("cmd:"))
        driver_verify._remember(rec.driver, "a" * 64, entry)

        report = verify(load(QEMU))
        cmd = next(c for c in report.drivers[0].checks if c.kind == "cmd")

        assert cmd.outcome is Outcome.UNVERIFIED


class TestTheGate:
    def test_a_failing_check_refuses_the_build(self, isolated_evidence):
        with pytest.raises(GateFailure, match=r"\[gate: drivers\]"):
            gate(load(QEMU), serial="[BOOT] OK\n")

    def test_the_refusal_says_what_to_do(self, isolated_evidence):
        with pytest.raises(GateFailure) as exc:
            gate(load(QEMU), serial="[BOOT] OK\n")

        assert "Fix the driver, or the check if the check is wrong" in str(exc.value)

    def test_implemented_with_no_observed_pass_is_refused(self, isolated_evidence):
        """`status: implemented` is a claim about this tree. driver_spec refuses
        it when `provides` has no source mapping; this closes the other half —
        the driver is mapped and nobody has checked it works."""
        with pytest.raises(GateFailure, match="no observed pass"):
            gate(load(QEMU))

    def test_that_refusal_names_the_alternative(self, isolated_evidence):
        with pytest.raises(GateFailure) as exc:
            gate(load(QEMU))

        assert "set status to 'specified'" in str(exc.value)

    def test_a_specified_driver_does_not_refuse(self, isolated_evidence):
        """A record for a driver that does not exist yet is the point of having
        records. Refusing it would make the format unusable for planning.

        Firecracker now carries two — virtio-net and virtio-blk — and neither
        refuses."""
        report = gate(load(FIRECRACKER))

        assert report.counts()["unverified"] == 2
        assert report.counts()["failed"] == 0

    def test_a_fully_verified_implemented_driver_passes(self, isolated_evidence):
        import driver_verify

        rec = next(r for r in drivers_for_target(load(QEMU))[0])
        h = driver_verify._sha256(rec.path)
        for entry in rec.verification:
            if entry.startswith("cmd:"):
                driver_verify._remember(rec.driver, h, entry)

        report = gate(load(QEMU), serial=BOOT_LOG)

        assert report.counts()["verified"] == 1


class TestThePackageCarriesTheResult:
    def test_a_targeted_package_writes_drivers_json(self, tmp_path, isolated_evidence):
        from package_image import package

        out = tmp_path / "out"
        package("what hardware is this", out, ROOT / "kernels" / "x86_64",
                target=QEMU)

        record = json.loads((out / "spec" / "drivers.json").read_text())
        assert record["target"] == "qemu-pc"
        assert record["counts"]["unverified"] == 1

    def test_it_is_written_even_when_the_build_never_ran(self, tmp_path, isolated_evidence):
        """Which drivers an image needs follows from the machine it is built
        for. An INCOMPLETE package still made that claim."""
        from package_image import package

        out = tmp_path / "out"
        pkg = package("what hardware is this", out, ROOT / "kernels" / "x86_64",
                      target=QEMU)

        assert not pkg.complete
        assert (out / "spec" / "drivers.json").exists()

    def test_the_three_states_survive_into_the_package(self, tmp_path, isolated_evidence):
        """Flattening to a boolean would lose the distinction the gate exists
        for, exactly as D8 kept `unknown` separate from `not_applicable`."""
        from package_image import package

        out = tmp_path / "out"
        package("what hardware is this", out, ROOT / "kernels" / "x86_64",
                target=QEMU)

        counts = json.loads((out / "spec" / "drivers.json").read_text())["counts"]
        assert set(counts) == {"verified", "unverified", "failed"}

    def test_a_package_with_no_target_has_no_driver_record(self, tmp_path):
        from package_image import package

        out = tmp_path / "out"
        pkg = package("what hardware is this", out, ROOT / "kernels" / "x86_64")

        assert pkg.drivers == {}
        assert not (out / "spec" / "drivers.json").exists()


class TestTheExitTwoConvention:
    """`run_leakage_test.sh` distinguishes exit 2 — *nothing to check* — from
    exit 0 — *clean*. V5's `run_virtio_net_test.sh` will exit 2 when there is no
    generated tree to test, and collapsing the two is how an untested driver
    reads as a tested one."""

    def _script(self, tmp_path, monkeypatch, exit_code):
        import driver_verify

        monkeypatch.setattr(driver_verify, "ROOT", tmp_path)
        script = tmp_path / "check.sh"
        script.write_text(f"#!/bin/sh\nexit {exit_code}\n")
        script.chmod(0o755)
        return driver_verify._run_command("cmd: check.sh", slow=True)

    def test_exit_zero_is_verified(self, tmp_path, monkeypatch):
        assert self._script(tmp_path, monkeypatch, 0).outcome is Outcome.VERIFIED

    def test_exit_two_is_unverified_not_verified(self, tmp_path, monkeypatch):
        check = self._script(tmp_path, monkeypatch, 2)

        assert check.outcome is Outcome.UNVERIFIED
        assert "nothing to check" in check.detail

    def test_exit_two_is_unverified_not_failed(self, tmp_path, monkeypatch):
        """Nothing to check is not a failure either — a driver that has not been
        written has not failed its test."""
        assert self._script(tmp_path, monkeypatch, 2).outcome is not Outcome.FAILED

    def test_any_other_nonzero_exit_fails(self, tmp_path, monkeypatch):
        check = self._script(tmp_path, monkeypatch, 1)

        assert check.outcome is Outcome.FAILED
        assert "exit 1" in check.detail
