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
        requires=("framebuffer", "input", "module-asset"),
        assets=("doom.wad",),
        markers=("[FB] mode set", "[INPUT] keyboard ready", "[DOOM] frame 1"),
        note="Needs a framebuffer and an input device; no network, no filesystem.",
    ),
    IntentRule(
        name="host-repo",
        phrases=("host this repo", "host a website", "serve this repo",
                 "web server", "serve files over http"),
        requires=("e1000", "ipv4", "tcp", "http-server", "dhcp-client"),
        markers=("[NET] dhcp bound", "[HTTP] listening on 80"),
        note="Needs the network stack and a NIC driver; no writable storage.",
    ),
    IntentRule(
        name="serve-dhcp",
        phrases=("hand out addresses", "dhcp server", "serve dhcp leases"),
        requires=("e1000", "ipv4", "udp"),
        markers=("[DHCP] listening on :67", "[DHCP] lease bound"),
        note="UDP only; explicitly not TCP.",
    ),
    IntentRule(
        name="serve-files",
        phrases=("file server", "share files", "serve a docroot"),
        requires=("e1000", "ipv4", "tcp", "http-server", "vfs", "initramfs"),
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

    def to_json(self) -> str:
        return json.dumps({
            "intent": self.intent,
            "matched_rule": self.matched,
            "requires": self.requires,
            "excludes": self.excludes,
            "assets": self.assets,
            "markers": self.markers,
            "assumptions": self.assumptions,
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


def build(sentence: str, input_device: str | None = None) -> Manifest:
    specs = load_specs()
    rule = match_intent(sentence)

    requires = list(BASE_REQUIRES) + [c for c in rule.requires
                                      if c not in BASE_REQUIRES]
    assumptions: list[str] = []

    if "input" not in requires and "framebuffer" not in requires:
        if input_device:
            requires.append(input_device)
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
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sentence", nargs="+")
    ap.add_argument("--output", help="write the manifest here")
    ap.add_argument("--input", dest="input_device",
                    help="name the input device instead of accepting the default")
    args = ap.parse_args(argv)

    try:
        manifest = build(" ".join(args.sentence), args.input_device)
    except IntentError as exc:
        print(f"DECLINED: {exc}", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(manifest.to_json() + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(manifest.to_json())
    for a in manifest.assumptions:
        print(f"ASSUMED: {a}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
