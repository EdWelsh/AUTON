"""Run what a driver record's `verification` promises.

V2 made `verification` mandatory and mechanical — every record names commands
and markers rather than prose. Nothing ran them, and a field that is mandatory
and unchecked is worse than an absent one: it reads as a guarantee.

Three outcomes, and the third is the one that matters. `virtio-net.md` names
`tests/kernel/run_virtio_net_test.sh`, which does not exist because the driver
does not exist. Treating that as a failure blocks every build touching a planned
driver; treating it as a pass is the lie the field was created to prevent.

    python agent/tools/driver_verify.py --target agent/kernel_spec/targets/qemu-pc.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Where a passing run is remembered. Gitignored alongside the other build
# artefacts: evidence is per-checkout, and a recorded pass copied between
# machines would be a claim about a run that never happened here.
EVIDENCE = ROOT / ".cache" / "driver-evidence.json"

# A command that boots an image under QEMU takes minutes. A gate that makes
# every service build pay that is a gate people turn off, and a gate people turn
# off verifies nothing.
SLOW_COMMANDS = ("run-acceptance", "e2e", "auton-boot")


class Outcome(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"      # could not be checked — NOT a pass
    FAILED = "failed"


@dataclass
class Check:
    entry: str
    kind: str                      # cmd | marker
    outcome: Outcome
    detail: str = ""


@dataclass
class DriverResult:
    driver: str
    strategy: str
    status: str
    record_sha256: str
    checks: list[Check] = field(default_factory=list)

    @property
    def outcome(self) -> Outcome:
        """The worst of its checks. A driver is not verified because most of it
        was."""
        if any(c.outcome is Outcome.FAILED for c in self.checks):
            return Outcome.FAILED
        if any(c.outcome is Outcome.UNVERIFIED for c in self.checks):
            return Outcome.UNVERIFIED
        return Outcome.VERIFIED


@dataclass
class Report:
    target: str
    drivers: list[DriverResult] = field(default_factory=list)
    undeclared: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        c = {o.value: 0 for o in Outcome}
        for d in self.drivers:
            c[d.outcome.value] += 1
        return c

    def to_json(self) -> str:
        return json.dumps({
            "target": self.target,
            "counts": self.counts(),
            "undeclared_drivers": self.undeclared,
            "drivers": [
                {**{k: v for k, v in asdict(d).items() if k != "checks"},
                 "outcome": d.outcome.value,
                 "checks": [{**asdict(c), "outcome": c.outcome.value}
                            for c in d.checks]}
                for d in self.drivers],
        }, indent=2)


class VerifyError(Exception):
    """Names the driver and what could not be established."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence() -> dict:
    if not EVIDENCE.exists():
        return {}
    try:
        return json.loads(EVIDENCE.read_text())
    except (OSError, ValueError):
        return {}


def _remember(driver: str, record_hash: str, entry: str) -> None:
    """Bind the evidence to the record it passed against.

    A recorded pass against a *different* record is not evidence — the
    verification may have been rewritten since, and the old result says nothing
    about the new claim.
    """
    data = _evidence()
    data.setdefault(driver, {})[entry] = record_hash
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(data, indent=2) + "\n")


def _has_evidence(driver: str, record_hash: str, entry: str) -> bool:
    return _evidence().get(driver, {}).get(entry) == record_hash


def drivers_for_target(target) -> tuple[list, list[str]]:
    """Which records apply to an image built for this target.

    Joined from the target's own devices, reusing D7's resolution. Verifying
    every record in kernel_spec/drivers/ would check drivers this image does not
    contain, and the pass would mean nothing.
    """
    from device_drivers import driver_for_device
    from driver_spec import DriverError, load, records

    by_name = {}
    for p in records():
        try:
            rec = load(p)
        except DriverError:
            continue
        by_name[rec.driver] = rec

    applicable, undeclared = [], []
    for dev in target.devices:
        name = driver_for_device(dev.id)
        if name is None:
            continue                      # nothing binds; not this gate's problem
        rec = by_name.get(name)
        if rec is None:
            undeclared.append(f"{name} (for {dev.id})")
        elif rec not in applicable:
            applicable.append(rec)
    return applicable, undeclared


def _run_command(entry: str, slow: bool) -> Check:
    command = entry.split(":", 1)[1].strip()
    script = ROOT / command.split()[0]

    if not script.exists():
        # Named but absent. For `status: specified` this is the normal state and
        # must not read as either a pass or a failure.
        return Check(entry, "cmd", Outcome.UNVERIFIED,
                     f"{command.split()[0]} does not exist")
    if not slow and any(s in command for s in SLOW_COMMANDS):
        return Check(entry, "cmd", Outcome.UNVERIFIED,
                     f"skipped: boots an image; pass --slow to run it")
    try:
        proc = subprocess.run(
            ["/bin/sh", str(script)], cwd=ROOT, capture_output=True,
            text=True, timeout=600,
            env={**os.environ, "PATH": os.environ.get("PATH", "")})
    except subprocess.TimeoutExpired:
        return Check(entry, "cmd", Outcome.FAILED, "timed out after 600s")
    if proc.returncode == 0:
        return Check(entry, "cmd", Outcome.VERIFIED, "exit 0")
    if proc.returncode == 2:
        # The `run_leakage_test.sh` convention: nothing to check is distinct
        # from clean, and collapsing them is how an untested driver reads as a
        # tested one.
        return Check(entry, "cmd", Outcome.UNVERIFIED,
                     "exit 2 — nothing to check")
    tail = (proc.stderr or proc.stdout).strip().splitlines()
    return Check(entry, "cmd", Outcome.FAILED,
                 f"exit {proc.returncode}" + (f": {tail[-1][:120]}" if tail else ""))


def _check_marker(entry: str, serial: str | None) -> Check:
    marker = entry.split(":", 1)[1].strip()
    if serial is None:
        # A marker can only be observed at boot. A gate that pretends otherwise
        # either blocks every build or verifies nothing.
        return Check(entry, "marker", Outcome.UNVERIFIED,
                     "no boot log; a marker is observed at run time")
    if marker in serial:
        return Check(entry, "marker", Outcome.VERIFIED, "observed")
    return Check(entry, "marker", Outcome.FAILED, "not in the boot log")


def verify(target, serial: str | None = None, slow: bool = False) -> Report:
    report = Report(target=target.target)
    applicable, undeclared = drivers_for_target(target)
    report.undeclared = undeclared

    for rec in applicable:
        record_hash = _sha256(rec.path)
        result = DriverResult(driver=rec.driver, strategy=rec.strategy,
                              status=rec.status, record_sha256=record_hash)
        for entry in rec.verification:
            if entry.startswith("cmd:"):
                check = _run_command(entry, slow)
                if check.outcome is Outcome.VERIFIED:
                    _remember(rec.driver, record_hash, entry)
                elif (check.outcome is Outcome.UNVERIFIED
                      and _has_evidence(rec.driver, record_hash, entry)):
                    check = Check(entry, "cmd", Outcome.VERIFIED,
                                  "recorded pass against this record")
            else:
                check = _check_marker(entry, serial)
            result.checks.append(check)
        report.drivers.append(result)
    return report


def gate(target, serial: str | None = None, slow: bool = False) -> Report:
    """The build gate. Refuses on a failure, and on an unproven claim.

    `status: implemented` is a claim about this tree. `driver_spec` already
    refuses it when `provides` has no source mapping; this closes the other half
    — the driver is mapped and nobody has checked it works.
    """
    from build_service import GateFailure

    report = verify(target, serial, slow)

    failed = [d for d in report.drivers if d.outcome is Outcome.FAILED]
    if failed:
        lines = [f"    {d.driver}: " + "; ".join(
            f"{c.entry} — {c.detail}" for c in d.checks
            if c.outcome is Outcome.FAILED) for d in failed]
        raise GateFailure(
            "[gate: drivers] driver verification failed:\n" + "\n".join(lines) +
            "\n  A driver that fails its own stated check is not shippable. Fix "
            "the driver, or the check if the check is wrong.")

    unproven = [d for d in report.drivers
                if d.status == "implemented" and d.outcome is not Outcome.VERIFIED]
    if unproven:
        lines = [f"    {d.driver}: " + "; ".join(
            f"{c.entry} — {c.detail}" for c in d.checks
            if c.outcome is not Outcome.VERIFIED) for d in unproven]
        raise GateFailure(
            "[gate: drivers] record(s) claim status 'implemented' with no "
            "observed pass:\n" + "\n".join(lines) +
            "\n  'implemented' is a claim about this tree. Run the verification, "
            "or set status to 'specified' until it is written.")
    return report


def main(argv: list[str] | None = None) -> int:
    from target_spec import TargetError, load as load_target

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", required=True, metavar="FILE")
    ap.add_argument("--serial", metavar="FILE", help="a boot log to check markers against")
    ap.add_argument("--slow", action="store_true", help="run commands that boot an image")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        target = load_target(args.target)
    except TargetError as exc:
        print(f"INVALID TARGET: {exc}", file=sys.stderr)
        return 1

    serial = Path(args.serial).read_text() if args.serial else None
    report = verify(target, serial, args.slow)

    if args.json:
        print(report.to_json())
    else:
        print(f"target: {report.target}")
        for d in report.drivers:
            print(f"  {d.driver:14s} {d.strategy:11s} {d.status:12s} "
                  f"{d.outcome.value}")
            for c in d.checks:
                print(f"      {c.outcome.value:11s} {c.entry}")
                if c.detail:
                    print(f"      {'':11s}   {c.detail}")
        for u in report.undeclared:
            print(f"  no record: {u}", file=sys.stderr)
        counts = report.counts()
        print(f"\n{counts['verified']} verified, {counts['unverified']} "
              f"unverified, {counts['failed']} failed")

    if report.counts()["failed"]:
        return 1
    if report.counts()["unverified"]:
        return 3            # not a pass; matches target_spec's EXIT_UNVERIFIABLE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
