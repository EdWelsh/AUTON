"""Build a Manifest from an artifact record: a second constructor, not a
second pipeline (application-to-environment A6).

    python agent/tools/artifact_manifest.py analysis/app.artifact.yaml --substrate docker

`intent_manifest.build(sentence)` was the only way to make a `Manifest`. This
makes the same dataclass from a validated artifact record, so everything
downstream — slice closure, excludes, the leakage gate, packaging — runs
unchanged, and refuses the same way.

Substrates decide what "requires" means:

- **docker, kubernetes, server** — the host kernel supplies the kernel, so the
  manifest's kernel `requires` is empty and `capability_slice` is never asked.
  What the application needs is carried in `Manifest.application`.
- **auton** — AUTON's own kernel. Each application fact must bridge to kernel
  capabilities (`agent/app_spec/kernel_bridge.yaml`); one that does not is
  REFUSED, because the kernel has no POSIX, no libc and no shell by design, and
  a mapping to something that merely sounds close is the phantom-capability
  failure one layer up. The bridged capabilities then close over the kernel
  index exactly as a sentence's do, and a contradiction is refused with its path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from artifact_spec import ArtifactError, kernel_capabilities, validate  # noqa: E402
from capability_slice import (  # noqa: E402
    SliceError,
    capability_owner,
    capability_slice,
    load_specs,
)
from intent_manifest import (  # noqa: E402
    BASE_REQUIRES,
    DEFAULTS,
    IntentError,
    IntentRule,
    Manifest,
    _drivers_from_target,
    derive_excludes,
)

SUBSTRATES = ("docker", "kubernetes", "server", "auton")
CONTAINER_SUBSTRATES = ("docker", "kubernetes", "server")


def _cite(raw: dict) -> str:
    ev = (raw.get("evidence") or [{}])[0]
    if not ev.get("file"):
        return ""
    return f"{ev['file']}:{ev['line']}: {str(ev.get('quote', '')).strip()}"


def _decisions(facts: list[dict]) -> list[dict]:
    """One per fact that carries evidence: what, from which source, because of
    which line. The shape driver decisions already use, so a reviewer reads
    both the same way."""
    out = []
    for raw in facts:
        if raw.get("source") == "unknown":
            continue
        because = (_cite(raw) or f"observation {raw.get('observation')}")
        out.append({"capability": raw["capability"], "source": raw["source"],
                    "because": because})
    return out


def build_from_artifact(record: str | Path, substrate: str = "docker", *,
                        subject: Path | None = None, target=None,
                        excludes: list[str] | tuple[str, ...] = (),
                        allow_observed: bool = True) -> Manifest:
    """A Manifest from a validated artifact record.

    `allow_observed` is True here, unlike for an agent's branch: by the time a
    record is turned into a manifest, `observed` facts in it came from
    observe.py, which is the only writer that stamps an observation id.
    """
    if substrate not in SUBSTRATES:
        raise IntentError(f"substrate {substrate!r} is not one of {', '.join(SUBSTRATES)}")
    try:
        report = validate(record, subject=subject, allow_observed=allow_observed)
    except ArtifactError as exc:
        raise IntentError(f"artifact record unreadable: {exc}") from exc
    if not report.ok:
        raise IntentError("artifact record refused:\n  " + "\n  ".join(report.problems))

    art = report.artifact
    facts = [art.runtime, *art.facts]
    app_caps = [f["capability"] for f in facts]
    commit = str(art.subject.get("commit") or "uncommitted")[:12]
    application = {
        "name": art.application,
        "substrate": substrate,
        "runtime": art.runtime["capability"],
        "requires": [f["capability"] for f in art.facts],
        "subject": dict(art.subject),
    }
    common = dict(intent=f"application:{art.application}@{commit}", matched="artifact",
                  assets=[], markers=[], decisions=_decisions(facts),
                  application=application)

    if substrate in CONTAINER_SUBSTRATES:
        return Manifest(requires=[], excludes=list(excludes),
                        assumptions=list(report.assumptions),
                        target=getattr(target, "target", ""), **common)
    return _for_auton(app_caps, report.assumptions, target, list(excludes), common)


def _for_auton(app_caps: list[str], assumptions: list[str], target,
               excludes: list[str], common: dict) -> Manifest:
    unbridged = [c for c in app_caps if kernel_capabilities(c) is None]
    if unbridged:
        raise IntentError(
            f"on the auton substrate every application capability must map to the "
            f"kernel, and {', '.join(unbridged)} do(es) not: AUTON's kernel has no "
            f"POSIX, no libc and no shell by design (intent-to-OS PRD). Choose a "
            f"container or VM substrate ({', '.join(CONTAINER_SUBSTRATES)}), or add a "
            f"bridge entry once the kernel provides it")

    specs = load_specs()
    known = set(specs) | set(capability_owner(specs))
    requires = list(BASE_REQUIRES)
    for cap in app_caps:
        for k in kernel_capabilities(cap) or []:
            if k not in requires:
                requires.append(k)
    assumptions = list(assumptions)
    decisions = list(common.pop("decisions"))

    # A network capability needs a network device, chosen as a sentence's is.
    if any(c.startswith(("listen:", "dial:")) for c in app_caps):
        if target is not None:
            rule = IntentRule(name=common["intent"], phrases=(), requires=(),
                              roles=("network",))
            drivers, extra, chosen = _drivers_from_target(rule, target, known)
            requires += [d for d in drivers if d not in requires]
            assumptions += extra
            decisions += chosen
        else:
            driver, why = DEFAULTS["network"]
            requires.append(driver)
            assumptions.append(f"network: assuming {driver} — {why}")

    unknown = [c for c in requires if c not in known]
    if unknown:
        raise IntentError(f"kernel_bridge.yaml names capabilities absent from the kernel "
                          f"index: {', '.join(unknown)}")
    try:
        capability_slice(requires, excludes, specs)
    except SliceError as exc:
        raise IntentError(f"{common['intent']} does not resolve: {exc}") from exc

    derived = derive_excludes(requires, specs)
    return Manifest(requires=requires,
                    excludes=sorted(set(derived) | set(excludes)),
                    assumptions=assumptions, decisions=decisions,
                    target=getattr(target, "target", ""), **common)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("record", help="an artifact record (*.artifact.yaml)")
    ap.add_argument("--substrate", default="docker", choices=SUBSTRATES)
    ap.add_argument("--subject", help="the staged application, to check quotes against")
    ap.add_argument("--exclude", action="append", default=[],
                    help="a kernel capability to exclude (auton substrate)")
    ap.add_argument("--target", metavar="FILE", help="a target definition (auton substrate)")
    ap.add_argument("--output", help="write the manifest here")
    args = ap.parse_args(argv)

    target = None
    if args.target:
        from target_spec import TargetError, load as load_target
        try:
            target = load_target(args.target)
        except TargetError as exc:
            print(f"INVALID TARGET: {exc}", file=sys.stderr)
            return 1
    try:
        manifest = build_from_artifact(
            args.record, args.substrate, target=target, excludes=args.exclude,
            subject=Path(args.subject) if args.subject else None)
    except IntentError as exc:
        print(f"DECLINED: {exc}", file=sys.stderr)
        return 1

    text = manifest.to_json()
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    for a in manifest.assumptions:
        print(f"ASSUMED: {a}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
