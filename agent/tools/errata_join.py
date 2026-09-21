"""Join a target's silicon to the errata table, before the build.

`machine_safety.py` can already answer "is this machine safe to run this image
on". It takes an `Identity` — vendor, family, model, stepping — which until D1
nothing in the tree recorded in a reviewable file. A target definition records
exactly that, and this is the join.

The case that matters is the one that looks like success. `firecracker.md`
records `vendor: unknown, family: 0, source: assumed`, because a microVM guest
inherits the host CPU and cannot read it. Handed to `assess_machine` as-is, that
produces a clean bill of health for silicon nobody has identified — which is
`machine_safety.py`'s own rule ("this machine has not been examined — that is
not the same as safe") violated from a new direction.

    python agent/tools/errata_join.py --target agent/kernel_spec/targets/qemu-pc.md \
        --intent "hand out addresses"
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from errata_table import Identity, Verdict  # noqa: E402
from machine_safety import assess_machine  # noqa: E402
from target_spec import Target, TargetError, load as load_target  # noqa: E402


class JoinError(Exception):
    """Names the target and the fact that could not support the lookup."""


@dataclass
class Join:
    """What the errata table could and could not say about this target.

    `unknown_because` is not a softer kind of clean. A caller that renders this
    must not print the word "safe" when it is set — the whole point is that
    nobody has looked.
    """
    target: str
    identity: Identity | None = None
    unknown_because: str = ""
    report: object | None = None
    blocking: list[str] = field(default_factory=list)
    inheritance: str = ""

    @property
    def examined(self) -> bool:
        return self.identity is not None and self.report is not None

    def summary(self) -> str:
        if self.unknown_because:
            return (f"UNKNOWN: {self.unknown_because} No errata verdict can be "
                    f"reached for {self.target!r}, and an unreached verdict is "
                    f"not a clean one.")
        return self.report.summary()


def silicon_identity(target: Target) -> Identity | None:
    """A target's silicon as an `Identity`, or None when it cannot support one.

    Returns None rather than a zeroed `Identity`. `Identity("unknown", 0, 0, 0)`
    is a perfectly valid object that `assess_machine` will happily answer about,
    and the answer will be "nothing applies" — a confident false statement. A
    missing return value cannot be mistaken for an answer; a zeroed one can.
    """
    sil = target.silicon
    if sil.get("source") == "assumed":
        return None
    try:
        family = int(sil["family"])
        model = int(sil["model"])
        stepping = int(sil.get("stepping", 0))
    except (KeyError, TypeError, ValueError):
        # Never int()-with-a-fallback: a non-numeric family becoming 0 is the
        # zeroed-Identity problem wearing a different hat.
        return None
    if not sil.get("vendor") or sil["vendor"] == "unknown":
        return None
    return Identity(sil["vendor"], family, model, stepping)


def _inheritance_note(target: Target) -> str:
    """Open question 4, answered where it can be and recorded where it cannot.

    D2 writes this question into every derived guest target. This is the phase
    that knows what an erratum applying to a machine means, so a silent absence
    here would read as "no".
    """
    if target.klass != "auton-hosted":
        return ""
    host = target.platform.get("host_image", "")
    return (
        f"INHERITANCE: this guest runs on host image {host[:12] or '<unstated>'}, "
        f"so it is affected by defects in that host's silicon whether or not the "
        f"host mitigates them. The host's own errata assessment is not reachable "
        f"from here — a package records its target, not its host's safety report "
        f"— so this remains PRD open question 4, unanswered. It is recorded "
        f"rather than omitted, because an omission would read as 'no'.")


def join(target: Target, capabilities: set[str]) -> Join:
    result = Join(target=target.target, inheritance=_inheritance_note(target))

    identity = silicon_identity(target)
    if identity is None:
        assumed = ", ".join(target.assumed_facts) or "silicon"
        result.unknown_because = (
            f"target {target.target!r} rests on assumed silicon ({assumed}); "
            f"its vendor/family/model cannot support a table lookup.")
        return result

    result.identity = identity
    result.report = assess_machine(identity, capabilities)
    result.blocking = _blocking(result.report, capabilities)
    return result


def _blocking(report, capabilities: set[str]) -> list[str]:
    """Errata that should stop a build: applicable, and explicitly beyond fixing.

    NARROWER THAN THE PLAN, and deliberately. The plan called for three
    conditions, the third being "the image uses the affected capability". That
    is not computable: an erratum record (`vendor_ingest.Record`) carries
    `applies_to` identity keys, `status`, `workaround` and `detail` — nothing
    that links a defect to a capability. `mitigation_registry.assess` does
    intersect capabilities, but with what a *mitigation needs*, not with what an
    *erratum affects*. Inventing the link would put a confident wrong claim into
    a safety report, which is the thing this phase exists to prevent.

    So the condition is `unmitigatable`: a mitigation record exists and says
    plainly that nothing can be done. Someone wrote `status: unmitigatable` — it
    is an explicit human judgement, not an inference, and an image on silicon
    that will compute wrong answers with no recourse is worth stopping.

    Errata with no mitigation record at all land in `applicable` and are
    *reported*, not blocked: on real hardware that is most of an Intel
    specification update, and refusing there would make the tool unusable.

    An UNKNOWN verdict triggers nothing here and is not counted as clear —
    `assess_machine` keeps `report.unknown` separate, and the caller prints it.
    """
    a = report.assessment
    if a is None:
        return []
    return sorted({e for e, _m, _why in a.unmitigatable})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", required=True, metavar="FILE")
    ap.add_argument("--intent", help="derive capabilities from this sentence")
    ap.add_argument("--capabilities", default="",
                    help="comma-separated, instead of --intent")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        target = load_target(args.target)
    except TargetError as exc:
        print(f"INVALID TARGET: {exc}", file=sys.stderr)
        return 1

    if args.intent:
        from intent_manifest import IntentError, build
        try:
            caps = set(build(args.intent, None, target).requires)
        except IntentError as exc:
            print(f"DECLINED: {exc}", file=sys.stderr)
            return 1
    else:
        caps = {c.strip() for c in args.capabilities.split(",") if c.strip()}

    r = join(target, caps)

    print(f"target: {r.target}")
    if r.identity:
        print(f"silicon: {r.identity.vendor} family {r.identity.family} "
              f"model {r.identity.model} stepping {r.identity.stepping} "
              f"(source {target.silicon['source']})")
    print()
    print(r.summary())
    if r.report:
        print()
        print("consulted:")
        for d in r.report.documents:
            print(f"  {d['document']}: {d['errata']} errata, "
                  f"{'covers' if d['matched'] else 'does not cover'} this silicon")
        if r.report.unknown:
            print()
            print(f"unknown ({len(r.report.unknown)}) — neither applicable nor clear:")
            for erratum, reason in r.report.unknown[:5]:
                print(f"  {erratum}: {reason}")
    if r.inheritance:
        print()
        print(r.inheritance)
    if r.blocking:
        print()
        print(f"BLOCKING: {', '.join(r.blocking)}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
