"""Fleet conformance reports: the format, and the aggregator (hardware-truth H10e).

    python agent/tools/fleet_report.py --show <verdicts.txt>     # what WOULD be sent
    python agent/tools/fleet_report.py --aggregate reports/      # what many say together

Mercurial cores were found at fleet scale, roughly one machine in a thousand,
and `agent/hardware/CONFORMANCE-HARDWARE.md` says plainly that this project
cannot reach that scale in-house. Scale could come from deployments instead —
images that opted in contributing their conformance results.

Because that moves data **off a user's machine**, two rules shape this file:

1. **The schema is an allowlist.** `serialise()` copies the fields named in
   `ALLOWED` and refuses anything else, so a field nobody considered cannot
   ride along. A denylist would ship the first thing somebody forgot.
2. **Nothing is sent from here.** There is no endpoint, no upload, no network
   call in this module: it builds a report and prints it. Where such a report
   could go is a deployment decision recorded in
   `agent/kernel_spec/decisions/fleet-endpoint.md`, and it is the owner's.

A virtualised machine's verdict proves nothing about silicon (the hypervisor
bit, H5): those reports are counted separately and never toward a flag.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Exactly what may leave a machine. Every field is about the SILICON and the
# check, never about the user, the network, or the installation.
ALLOWED = (
    "schema",            # this format's version
    "silicon",           # family:model:stepping[:microcode]
    "vendor",            # GenuineIntel / AuthenticAMD
    "virtualised",       # 1 when the hypervisor bit is set: proves nothing about silicon
    "suite",             # the corpus revision the checks came from
    "checked",           # how many clause-cited checks ran
    "divergences",       # [{id, clause, expected, observed}]
    "not_assertable",    # ids reported, never failures
)

# Fields that must never appear, checked by name as well as by the allowlist,
# so a refusal names the specific mistake rather than "unknown field".
FORBIDDEN_HINTS = {
    "mac": "a MAC address identifies a machine, and a defect report does not need one",
    "hostname": "a hostname identifies a machine",
    "ip": "an address identifies a network",
    "serial": "a serial number identifies a unit, not a silicon revision",
    "uuid": "a machine UUID identifies a machine",
    "user": "who is running it is never relevant to whether a chip divides correctly",
    "username": "who is running it is never relevant to whether a chip divides correctly",
    "path": "a filesystem path can carry a name",
}

SCHEMA = 1
SILICON_RE = re.compile(r"^\d+:\d+:\d+(?::\w+)?$")


class ReportError(Exception):
    pass


@dataclass
class Report:
    silicon: str
    vendor: str
    virtualised: int = 0
    suite: str = ""
    checked: int = 0
    divergences: list[dict] = field(default_factory=list)
    not_assertable: list[str] = field(default_factory=list)


def serialise(fields: dict) -> dict:
    """The report as it would be sent, or a refusal naming the offending field."""
    for key in fields:
        low = key.lower()
        for hint, why in FORBIDDEN_HINTS.items():
            if hint in low:
                raise ReportError(f"refusing to include {key!r}: {why}")
        if key not in ALLOWED:
            raise ReportError(
                f"refusing to include {key!r}: the schema is an allowlist, and a field "
                f"nobody considered must not ride along. Allowed: {', '.join(ALLOWED)}")
    if not SILICON_RE.match(str(fields.get("silicon", ""))):
        raise ReportError(
            f"silicon {fields.get('silicon')!r} is not family:model:stepping — a report "
            f"that cannot be grouped by part is not worth sending")
    out = {"schema": SCHEMA}
    out.update({k: v for k, v in fields.items() if k != "schema"})
    return out


def from_verdicts(text: str, suite: str = "") -> dict:
    """Build a report from a conformance run's verdicts, using the same parser
    the local summary uses, so what is shown is what was measured."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from conformance import summarise

    s = summarise(text)
    identity = s.identity
    vendor = next((v for v in ("GenuineIntel", "AuthenticAMD") if v in identity), "")
    match = re.search(r"\b\d+:\d+:\d+(?::\w+)?\b", identity)
    return serialise({
        "silicon": match.group(0) if match else "",
        "vendor": vendor,
        "virtualised": 1 if "hypervisor" in identity.lower() else 0,
        "suite": suite,
        "checked": s.checked,
        "divergences": [{"id": d.id, "clause": d.clause,
                         "expected": d.expected, "observed": d.observed}
                        for d in s.diverged],
        "not_assertable": list(s.not_assertable),
    })


@dataclass
class Aggregate:
    silicon: str
    machines: int = 0
    virtualised: int = 0
    checked: int = 0
    by_entry: dict = field(default_factory=lambda: defaultdict(int))

    @property
    def real_machines(self) -> int:
        """Reports from bare metal. A virtualised divergence is the emulator's."""
        return self.machines - self.virtualised


def aggregate(reports: list[dict]) -> dict[str, Aggregate]:
    out: dict[str, Aggregate] = {}
    for r in reports:
        key = r.get("silicon", "")
        agg = out.setdefault(key, Aggregate(key))
        agg.machines += 1
        agg.checked += int(r.get("checked", 0))
        if r.get("virtualised"):
            agg.virtualised += 1
            continue                     # never counted toward a divergence
        for d in r.get("divergences", []):
            agg.by_entry[d["id"]] += 1
    return out


def report_text(aggs: dict[str, Aggregate]) -> str:
    lines = []
    for silicon, a in sorted(aggs.items()):
        lines.append(f"{silicon}: {a.machines} report(s), {a.virtualised} virtualised "
                     f"({a.real_machines} on metal), {a.checked} checks")
        if not a.by_entry:
            lines.append("  no divergences on metal")
        for entry, n in sorted(a.by_entry.items(), key=lambda kv: -kv[1]):
            rate = n / a.real_machines if a.real_machines else 0
            lines.append(f"  {entry}: {n} of {a.real_machines} machines ({rate:.1%})")
    if not aggs:
        lines.append("no reports")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--show", type=Path, help="a verdicts file: print the report that "
                                              "WOULD be sent, and send nothing")
    ap.add_argument("--aggregate", type=Path, help="a directory of report JSON files")
    ap.add_argument("--suite", default="", help="the corpus revision")
    args = ap.parse_args(argv)

    if args.show:
        try:
            report = from_verdicts(args.show.read_text(), args.suite)
        except ReportError as exc:
            print(f"no report: {exc}")
            return 2
        print(json.dumps(report, indent=1))
        print("\nNothing was sent: this tool has no endpoint. See "
              "agent/kernel_spec/decisions/fleet-endpoint.md")
        return 0
    if args.aggregate:
        reports = [json.loads(p.read_text()) for p in sorted(args.aggregate.glob("*.json"))]
        print(report_text(aggregate(reports)))
        return 0
    ap.error("give --show FILE or --aggregate DIR")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
