"""Turn a sentence into a capability manifest.

    AUTON train "I want to play Doom" --output ./Doom

This is the compiler's front end. It is small because intent-A did the hard
part: the capability vocabulary exists, slices are computable, and a
contradictory manifest is already refused with the path that caused it.

Matching is table-driven and deterministic, not a model. A model asked to
produce capability names produces plausible ones that are not in the index —
the same failure that put a phantom Realtek NIC in answers to questions naming
no device, measured at 5 citations per 50 turns
(.claude/PRPs/reports/e2e-intent-scoped-corpus.md). The index is the
vocabulary; this table is the join.

An intent the table does not cover is DECLINED, with the list of what is known.
It is never mapped to a default image, because an image that boots and does the
wrong thing is worse than a refusal at build time.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from capability_slice import (  # noqa: E402
    SliceError,
    capability_owner,
    capability_slice,
    load_specs,
)


class IntentError(Exception):
    """Carries what was not understood and what is. 'unknown intent' alone
    leaves the user guessing at the vocabulary."""


@dataclass(frozen=True)
class IntentRule:
    """One recognised purpose.

    `phrases` are matched as whole words against the normalised sentence.
    `requires` names capabilities from the index — validated at load, so a typo
    here is an error rather than a silently narrower image.
    """
    name: str
    phrases: tuple[str, ...]
    requires: tuple[str, ...]
    # What the image needs *hardware* for. Deliberately not merged into
    # `requires`: that names capabilities from the subsystem index, and a role
    # is not one. `net` is a subsystem name, and capability_slice(["boot",
    # "net"]) resolves to the same six subsystems as capability_slice(["boot",
    # "udp"]) — so putting a role in `requires` would be an alias for a
    # capability and would break services/README.md rule 2. The two lists
    # answer different questions: what the image does, and what it runs on.
    roles: tuple[str, ...] = ()
    assets: tuple[str, ...] = ()
    markers: tuple[str, ...] = ()
    note: str = ""


# Capabilities every image needs whatever it is for: something to boot, somewhere
# to allocate, a way to enumerate hardware, and a terminal to be asked questions
# through. The PRD's images are all chat-driven.
BASE_REQUIRES = ("boot", "allocator", "pci", "terminal", "scoped")

INTENTS: tuple[IntentRule, ...] = (
    IntentRule(
        name="play-doom",
        phrases=("play doom", "run doom", "doom"),
        # timer: doomgeneric asks the platform for milliseconds (DG_GetTicksMs)
        # and to sleep (DG_SleepMs). It is in every slice via the core today,
        # which is incidental — a service names what it calls.
        requires=("framebuffer", "input", "module-asset", "timer"),
        assets=("doom.wad",),
        markers=("[FB] mode set", "[INPUT] keyboard ready", "[DOOM] frame 1"),
        note="Needs a framebuffer and an input device; no network, no filesystem.",
    ),
    IntentRule(
        name="host-repo",
        phrases=("host this repo", "host a website", "serve this repo",
                 "web server", "serve files over http"),
        # module-asset: the repository travels in the image as repo.cpio, the
        # way Doom's WAD does. The alternative, a disk, is the file server's
        # signal (F8), not this one's — here the probe is a clone.
        requires=("ipv4", "tcp", "http-server", "dhcp-client", "module-asset"),
        roles=("network",),
        assets=("repo.cpio",),
        markers=("[NET] dhcp bound", "[HTTP] repo mounted", "[HTTP] listening on :80"),
        note="Needs the network stack and a NIC driver; no writable storage.",
    ),
    IntentRule(
        name="serve-dhcp",
        phrases=("hand out addresses", "dhcp server", "serve dhcp leases"),
        requires=("ipv4", "udp"),
        roles=("network",),
        markers=("[DHCP] listening on :67", "[DHCP] lease bound"),
        note="UDP only; explicitly not TCP.",
    ),
    IntentRule(
        name="serve-files",
        phrases=("file server", "share files", "serve a docroot"),
        requires=("ipv4", "tcp", "http-server", "vfs", "initramfs"),
        roles=("network",),
        assets=("docroot.cpio",),
        markers=("[HTTP] docroot mounted from module", "[HTTP] listening on :80"),
        note="Read-only storage from a boot module; no write path.",
    ),
    IntentRule(
        name="identify-hardware",
        phrases=("what hardware", "identify my hardware", "inspect this machine",
                 "is this machine safe"),
        requires=("device-registry", "driver-binding"),
        markers=("[DEV] PCI scan", "[CPU] "),
        note="The smallest useful image: enumerate and answer questions about it.",
    ),
)

# Excludes worth naming in a manifest. The true complement is most of the index
# and mostly uninteresting; these are the capabilities a reader would otherwise
# assume present, so their absence is the informative part.
NOTABLE_EXCLUDES = ("net", "fs", "sched", "ipc", "writable", "preemptive", "tcp")

# Applied when the sentence does not say. Recorded, never silent — an image that
# arrives without the input device its user assumed fails at boot rather than at
# build, which is the expensive end.
DEFAULTS = {
    "input": ("terminal", "serial console; pass --input keyboard for a framebuffer image"),
    # `e1000` was hardcoded into three intent rules, so every network image was
    # built for an Intel 82540EM whatever machine it was going to run on —
    # including a microVM with no PCI bus, where that driver binds to nothing.
    # It is still the default when no target is stated, because a caller with no
    # target has said nothing about the machine. The change is that it is now
    # *recorded as an assumption* rather than invisible in a rule table.
    "network": ("e1000", "the QEMU PC's NIC; state a target to choose from its "
                         "devices instead"),
}


@dataclass
class Manifest:
    intent: str
    matched: str
    requires: list[str]
    excludes: list[str]
    assets: list[str]
    markers: list[str]
    assumptions: list[str] = field(default_factory=list)
    # Which target chose each driver, and from which device. A reviewer reading
    # PROVENANCE.json can then see *why this image has this driver* without
    # re-deriving it.
    target: str = ""
    decisions: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "intent": self.intent,
            "matched_rule": self.matched,
            "requires": self.requires,
            "excludes": self.excludes,
            "assets": self.assets,
            "markers": self.markers,
            "assumptions": self.assumptions,
            "target": self.target,
            "decisions": self.decisions,
        }, indent=2)


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def match_intent(sentence: str, rules: tuple[IntentRule, ...] = INTENTS) -> IntentRule:
    norm = f" {' '.join(normalise(sentence).split())} "
    # Longest phrase first: "web server" must beat "server" if both were listed,
    # and "play doom" must beat the bare "doom".
    candidates = sorted(
        ((rule, phrase) for rule in rules for phrase in rule.phrases),
        key=lambda rp: -len(rp[1]),
    )
    for rule, phrase in candidates:
        if f" {phrase} " in norm:
            return rule
    raise IntentError(
        f"I do not know how to build an OS for {sentence!r}.\n"
        f"  Known intents: "
        + "; ".join(f"{r.name} ({r.phrases[0]!r})" for r in rules)
        + "\n  Add a rule to INTENTS rather than guessing — an image that boots "
          "and does the wrong thing is worse than this message."
    )


def derive_excludes(requires: list[str], specs=None) -> list[str]:
    """What the slice does not reach, reduced to what is worth stating.

    Derived rather than hand-supplied: a written `excludes` is a guess about
    what to leave out, and it silently omits whatever nobody thought of.
    """
    specs = specs if specs is not None else load_specs()
    owners = capability_owner(specs)
    reached = set(capability_slice(requires, [], specs).subsystems)
    reached_caps = set(capability_slice(requires, [], specs).capabilities)

    out = []
    for token in NOTABLE_EXCLUDES:
        if token in specs:
            if token not in reached:
                out.append(token)
        elif token in owners:
            # A capability whose owning subsystem is already excluded adds
            # nothing: `net` excluded already means no `tcp`. Listing both
            # reads as two decisions where one was made.
            if owners[token] in out:
                continue
            if token not in reached_caps:
                out.append(token)
    return out


class TargetMismatch(IntentError):
    """The machine cannot serve the intent.

    A separate class from IntentError because the sentence is fine — it is the
    pairing that does not work, and a caller may want to offer a different
    target rather than a different sentence.
    """


def _drivers_from_target(rule: "IntentRule", target,
                         known_capabilities: set[str]) -> tuple[list[str], list[str], list[dict]]:
    """Choose a driver per role from the target's own devices.

    Returns (drivers, assumptions, decisions). A table lookup joined on
    `Device.role`, never an inference: the same rule H2 set for device facts.
    """
    from device_drivers import ROLE_CAPS, driver_for_device

    drivers: list[str] = []
    assumptions: list[str] = []
    decisions: list[dict] = []

    for role in rule.roles:
        candidates = [d for d in target.devices if d.role == role]
        if not candidates:
            # Refuse on the role, not on a driver. "No driver for e1000" is a
            # different and less useful sentence than "this machine has no
            # network device" — and the second one is the true one.
            absent = next((a for a in target.absent if a.lower().startswith(role)), "")
            raise TargetMismatch(
                f"target {target.target!r} has no device with role {role!r}, "
                f"which {rule.name!r} needs"
                + (f" ({absent})" if absent else "")
                + ". Choose a different target, or an intent this machine can serve")

        undrivable = []
        for dev in candidates:
            driver = driver_for_device(dev.id)
            if driver is None:
                undrivable.append(dev.id)
                continue
            if driver not in known_capabilities:
                # The machine has the device, something knows which driver it
                # needs, and no subsystem spec provides that driver. Raised
                # here rather than at the index check below, because that one
                # would blame the rule table — and the rule table is innocent:
                # it no longer names a driver at all.
                raise TargetMismatch(
                    f"target {target.target!r} needs {driver!r} for its {role} "
                    f"device {dev.id}, and no subsystem spec provides it. "
                    f"`{driver}` is not in the capability index — see "
                    f"kernel_spec/subsystems/drivers.md `provides`. A driver "
                    f"record and an implementation are needed first "
                    f"(auton-driver-development.prd.md, V2 then V5)")
            if driver not in drivers:
                drivers.append(driver)
            decisions.append({
                "role": role, "device": dev.id, "driver": driver,
                "device_source": dev.source, "target": target.target,
            })
            break
        else:
            raise TargetMismatch(
                f"target {target.target!r} has {role} device(s) "
                f"{', '.join(undrivable)} that nothing in device_drivers.py can "
                f"drive. Add a driver record (kernel_spec/drivers/), or choose a "
                f"target whose {role} device is supported")
    return drivers, assumptions, decisions


def build(sentence: str, input_device: str | None = None, target=None) -> Manifest:
    specs = load_specs()
    rule = match_intent(sentence)

    requires = list(BASE_REQUIRES) + [c for c in rule.requires
                                      if c not in BASE_REQUIRES]
    assumptions: list[str] = []
    decisions: list[dict] = []

    # The driver comes from the machine when one is stated, and from a recorded
    # default when none is. Before this, it came from the intent rule — which
    # knows what the image is for and nothing about what it runs on.
    if rule.roles:
        if target is not None:
            chosen, extra, decisions = _drivers_from_target(
                rule, target, set(specs) | set(capability_owner(specs)))
            requires += [d for d in chosen if d not in requires]
            assumptions += extra
        else:
            for role in rule.roles:
                driver, why = DEFAULTS.get(role, (None, None))
                if driver is None:
                    raise IntentError(
                        f"intent {rule.name!r} needs a {role!r} device and no "
                        f"target was stated; there is no recorded default for "
                        f"that role")
                if driver not in requires:
                    requires.append(driver)
                assumptions.append(f"{role}: assuming {driver} — {why}")

    if "input" not in requires and "framebuffer" not in requires:
        if input_device:
            requires.append(input_device)
        elif target is not None and any(
                a.lower().startswith("display") for a in target.absent):
            # Not a better guess — a fact. The target records that the machine
            # has no display at all, which settles the question the assumption
            # existed to paper over. The PRD's metric is facts carrying a
            # source, not defaults carrying better odds.
            decisions.append({
                "role": "input", "device": None, "driver": "terminal",
                "device_source": "derived",
                "because": f"{target.target} records no display device",
                "target": target.target,
            })
        else:
            default, why = DEFAULTS["input"]
            assumptions.append(f"input: assuming {why}")

    # Validate before deriving: an unknown capability here would produce an
    # excludes list computed from a slice that does not exist.
    known = set(specs) | set(capability_owner(specs))
    unknown = [c for c in requires if c not in known]
    if unknown:
        raise IntentError(
            f"intent {rule.name!r} requires capabilities absent from the index: "
            f"{', '.join(unknown)}. The rule table and the specs disagree."
        )

    try:
        capability_slice(requires, [], specs)
    except SliceError as exc:
        raise IntentError(f"intent {rule.name!r} does not resolve: {exc}") from exc

    excludes = derive_excludes(requires, specs)
    return Manifest(
        intent=sentence,
        matched=rule.name,
        requires=requires,
        excludes=excludes,
        assets=list(rule.assets),
        markers=list(rule.markers),
        assumptions=assumptions,
        target=getattr(target, "target", ""),
        decisions=decisions,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sentence", nargs="+")
    ap.add_argument("--output", help="write the manifest here")
    ap.add_argument("--target", metavar="FILE",
                    help="a target definition (kernel_spec/targets/*.md); the "
                         "driver is chosen from its devices instead of assumed")
    ap.add_argument("--input", dest="input_device",
                    help="name the input device instead of accepting the default")
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
        manifest = build(" ".join(args.sentence), args.input_device, target)
    except TargetMismatch as exc:
        # Distinct from DECLINED: the sentence is fine, the pairing is not.
        print(f"MISMATCH: {exc}", file=sys.stderr)
        return 2
    except IntentError as exc:
        print(f"DECLINED: {exc}", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(manifest.to_json() + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(manifest.to_json())
    for d in manifest.decisions:
        why = d.get("because") or f"{d['device']} ({d['device_source']})"
        print(f"CHOSE: {d['driver']} for {d['role']} — {why}", file=sys.stderr)
    for a in manifest.assumptions:
        print(f"ASSUMED: {a}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
