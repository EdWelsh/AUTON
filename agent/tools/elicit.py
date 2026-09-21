"""Ask about a target — only what derivation and probing could not answer.

D2 derives a target from an AUTON host's provenance. D3 derives one from a
hypervisor and machine type. D4 reads one off a running machine. This asks about
what is left, and the PRD's hypothesis is that what is left is usually nothing.

Three rules shape it:

**Questions come from the validator's own list.** `target_spec.missing_facts`
already computes what a definition still needs, per class, each with its reason.
A second list of questions would drift from it.

**The cheaper path is offered first.** Before any device question, this asks
whether `lspci -nn` can be run. A tool that asks twelve device questions when
one paste would do has made the form the product.

**A kernel cannot run inside a container.** That request means one of two
things, and guessing produces either an unbootable image or a useless one. The
distinction is surfaced, never resolved.

    python agent/tools/elicit.py --answers class=microvm,hypervisor=firecracker,machine=default
    python agent/tools/elicit.py --measure
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from target_spec import (  # noqa: E402
    CLASSES,
    FIRMWARE,
    PLATFORM_IMPLIES_DEVICES,
    Device,
    Target,
    missing_facts,
)

# What counts as declining to answer. `unknown` is deliberately NOT here: for a
# microVM guest "nobody can know, the host chooses the CPU" is a *statement*,
# and it is the one D3's derivation makes for the same reason. Declining is
# saying nothing; asserting unknowability is saying something.
DECLINED = {"", "?", "idk", "i don't know", "i dont know", "skip", "pass"}

# A kernel cannot run inside a container — a container shares the host's kernel,
# which is what a container *is*. The request is not incoherent; it means one of
# two things, and they produce different artifacts.
CONTAINER_WORDS = ("container", "docker", "k8s", "kubernetes", "pod", "oci")

CONTAINER_QUESTION = (
    "A kernel cannot run inside a container — a container shares the host's "
    "kernel, which is what a container is. Two things that request can mean, "
    "and they produce different artifacts:\n"
    "  microvm  — a microVM the container runtime schedules (Kata, Firecracker "
    "under containerd). AUTON is the guest kernel; the runtime is the "
    "scheduler.\n"
    "  artifact — an OCI image that ships the ISO for distribution, not "
    "execution.\n"
    "Which do you mean?"
)


@dataclass
class Question:
    """One question, with what would answer it without asking.

    `cheaper` names a command whose output would settle this and usually more
    besides. A question that could have been a paste is a question that should
    not have been asked.
    """
    field: str
    prompt: str
    options: tuple[str, ...] = ()
    cheaper: str = ""

    def render(self) -> str:
        out = self.prompt
        if self.options:
            out += f"\n  one of: {', '.join(self.options)}"
        if self.cheaper:
            out += f"\n  (or paste the output of `{self.cheaper}` instead)"
        return out


@dataclass
class Draft:
    """Facts gathered so far. Everything here was stated by a person."""
    name: str = "elicited"
    klass: str = ""
    arch: str = "x86_64"
    firmware: str = ""
    silicon: dict = field(default_factory=dict)
    platform: dict = field(default_factory=dict)
    devices: list[dict] = field(default_factory=list)
    declined: list[str] = field(default_factory=list)
    container_asked: bool = False
    probe_offered: bool = False
    probe_accepted: bool = False
    asked: int = 0

    def as_target(self) -> Target:
        """A provisional Target, so the validator can be asked what is missing.

        Built even when incomplete: `missing_facts` reasons about class and
        platform, and needs neither firmware nor silicon to do it.
        """
        return Target(
            target=self.name, klass=self.klass or "bare-metal", arch=self.arch,
            firmware=self.firmware or "none", silicon=dict(self.silicon),
            platform=dict(self.platform),
            devices=[Device(d["id"], d["role"], "user-stated")
                     for d in self.devices],
        )


def _is_declined(answer: str) -> bool:
    return answer.strip().lower() in DECLINED


def next_question(draft: Draft) -> Question | None:
    """The single next question, or None when nothing is left to ask.

    One at a time, deliberately. A form asks everything up front and therefore
    asks things that later answers would have made unnecessary — the probe offer
    below removes every device question, and cannot if the device questions were
    already on the page.
    """
    if "class" in draft.declined:
        # Nothing below this is answerable. Every remaining question is
        # per-class — what a microVM needs and what bare metal needs share
        # almost nothing — so asking them of a machine nobody has named
        # collects answers to the wrong questions.
        return None

    if draft.container_asked and not draft.klass and "class" not in draft.declined:
        return Question("container_meaning", CONTAINER_QUESTION,
                        options=("microvm", "artifact"))

    if not draft.klass and "class" not in draft.declined:
        return Question(
            "class",
            "What will this image run on?",
            options=CLASSES,
            cheaper="dmidecode -t system")

    # The cheap path, before anything about devices. `lspci -nn` answers the
    # device list and their roles in one paste.
    if (draft.klass in ("bare-metal", "vm") and not draft.probe_offered
            and not draft.devices):
        return Question(
            "probe",
            "Can you run `lspci -nn` on that machine and paste the output? "
            "It answers every device question at once.",
            options=("yes", "no"))

    for field_name, reason in missing_facts(draft.as_target()):
        key = field_name.split(".")[-1].strip("{}")
        if key in draft.declined:
            continue
        if field_name.startswith("platform."):
            # `missing_facts` names them together when several are absent —
            # `platform.{hypervisor,machine}`. One at a time is the rule, so the
            # first unanswered one is the question.
            for one in key.split(","):
                if one and one not in draft.declined and one not in draft.platform:
                    return Question(f"platform.{one}",
                                    f"{reason.capitalize()}. What is {one}?")
            continue
        if field_name == "devices":
            if draft.probe_accepted:
                continue
            return Question(
                "devices",
                f"{reason.capitalize()}. Name a device as "
                f"`<vendor>:<device> <role>`, or say done.",
                cheaper="lspci -nn")
        if field_name == "silicon":
            return Question(
                "silicon",
                f"{reason.capitalize()}. Give vendor/family/model/stepping.",
                cheaper="cat /proc/cpuinfo")
        if field_name == "firmware":
            return Question("firmware", f"{reason.capitalize()}. Which firmware?",
                            options=FIRMWARE, cheaper="dmidecode -t bios")

    if not draft.firmware and "firmware" not in draft.declined:
        return Question("firmware", "Which firmware brings this machine up?",
                        options=FIRMWARE, cheaper="dmidecode -t bios")
    if not draft.silicon and "silicon" not in draft.declined:
        return Question("silicon", "What CPU is in it?",
                        cheaper="cat /proc/cpuinfo")
    return None


def answer(draft: Draft, question: Question, reply: str) -> str:
    """Apply one answer. Returns a note when the answer needs surfacing.

    A declined question leaves the fact unstated — never filled with a plausible
    default. That is `machine_safety.py`'s rule in the interactive path: a form
    that will not let you say "I don't know" collects a guess and records it as
    a statement.
    """
    draft.asked += 1
    reply = reply.strip()

    if _is_declined(reply):
        key = question.field.split(".")[-1].strip("{}")
        draft.declined.append(key)
        if key == "container_meaning":
            # Declining which of the two meanings applies leaves no machine to
            # describe, so `class` is unanswered too. Without this the loop
            # re-asks forever — a form that cannot be escaped is worse than one
            # that is merely long.
            draft.declined.append("class")
        return ""

    if question.field == "class":
        if reply in CLASSES:
            # An exact class name is a choice from the offered list, not a
            # description. `k8s-pod` contains "k8s" and would otherwise trigger
            # the container question forever — the one class you cannot reach by
            # naming it. The disambiguation is for prose like "put it in a
            # docker container", where the meaning genuinely is unclear.
            draft.klass = reply
            return ""
        if any(w in reply.lower() for w in CONTAINER_WORDS):
            # Surfaced, not resolved. The PRD names guessing here as the risk:
            # one reading yields an unbootable image, the other a useless one,
            # and the user cannot tell which they got until it fails. Asked as
            # its own question rather than re-asking `class`, so the loop
            # advances and the disambiguation is answerable.
            draft.container_asked = True
            return CONTAINER_QUESTION
        draft.klass = reply
        return ""

    if question.field == "container_meaning":
        if reply == "artifact":
            draft.declined.append("class")
            return ("An OCI image shipping the ISO is a packaging job, not a "
                    "target definition — there is no machine to describe. "
                    "`package_image.py` produces the ISO; wrap it downstream.")
        draft.klass = reply
        return ""

    if question.field == "probe":
        draft.probe_offered = True
        draft.probe_accepted = reply.lower().startswith("y")
        return ("Paste it into `probe_ingest.py --lspci -` — that answers the "
                "devices, and `--cpuinfo`/`--dmidecode` answer the rest."
                if draft.probe_accepted else "")

    if question.field.startswith("platform."):
        draft.platform[question.field.split(".")[-1].strip("{}")] = reply
        draft.platform["source"] = "user-stated"
        return ""

    if question.field == "firmware":
        draft.firmware = reply
        return ""

    if question.field == "silicon":
        if reply.lower() in ("unknown", "none", "cannot know", "host chooses"):
            # The same block D3 emits for a microVM, and for the same reason:
            # a guest does not choose its CPU. Recorded as `assumed` rather than
            # omitted, so it parses and `assumed_facts` reports it.
            draft.silicon = {"vendor": "unknown", "family": "0", "model": "0",
                             "stepping": "0", "source": "assumed"}
            return ""
        parts = [p.strip() for p in reply.replace("/", " ").split()]
        if len(parts) < 4:
            return ("Need vendor, family, model and stepping — four values. "
                    "Say 'unknown' to leave it unstated.")
        draft.silicon = {"vendor": parts[0], "family": parts[1],
                         "model": parts[2], "stepping": parts[3],
                         "source": "user-stated"}
        return ""

    if question.field == "devices":
        if reply.lower() == "done":
            draft.declined.append("devices")
            return ""
        bits = reply.split()
        if len(bits) != 2:
            return "Give `<vendor>:<device> <role>`, or say done."
        draft.devices.append({"id": bits[0].lower(), "role": bits[1]})
        return ""
    return ""


def to_target(draft: Draft) -> str:
    """Render what was stated. Nothing declined is filled in — D6 then refuses
    the result, naming it."""
    lines = ["---", f"target: {draft.name}"]
    if draft.klass:
        lines.append(f"class: {draft.klass}")
    lines.append(f"arch: {draft.arch}")
    if draft.firmware:
        lines.append(f"firmware: {draft.firmware}")
    if draft.silicon:
        lines.append("silicon:")
        lines += [f"  {k}: {v}" for k, v in draft.silicon.items()]
    if draft.platform:
        lines.append("platform:")
        lines += [f"  {k}: {v}" for k, v in draft.platform.items()]
    lines.append("devices:")
    for d in draft.devices:
        lines += [f'  - id: "{d["id"]}"', f"    role: {d['role']}",
                  "    source: user-stated"]
    if draft.declined:
        lines.append("assumptions:")
        lines += [f'  - "{f}: declined — left unstated rather than guessed"'
                  for f in sorted(set(draft.declined))]
    lines += ["provenance:", "  stated_by: elicitation",
              f"  questions_asked: {draft.asked}", "---", "",
              f"# {draft.name}", "",
              f"Elicited in {draft.asked} question(s). Every fact here carries "
              f"`source: user-stated` — a person said so, and nothing observed "
              f"it. D8's errata join will often contradict a wrong claim.", ""]
    return "\n".join(lines)


def run(answers: dict[str, str], name: str = "elicited") -> tuple[Draft, list[str]]:
    """Drive the loop from pre-supplied answers. The interactive prompt is a
    thin shell over this, so the logic is testable without a terminal."""
    draft = Draft(name=name)
    notes: list[str] = []
    for _ in range(40):                       # a ceiling, not an expectation
        q = next_question(draft)
        if q is None:
            break
        key = q.field.split(".")[-1].strip("{}")
        reply = answers.get(key, answers.get(q.field, ""))
        note = answer(draft, q, reply)
        if note:
            notes.append(note)
    return draft, notes


def measure() -> list[tuple[str, int]]:
    """The PRD's hypothesis, as a number per class.

    "Most hardware definitions can be derived rather than elicited, and the ones
    that cannot should be a short conversation rather than a form."
    """
    from target_spec import derive_microvm, load

    rows: list[tuple[str, int]] = []

    # Derived: nothing is asked at all.
    derive_microvm("firecracker")
    rows.append(("microvm (derived from hypervisors.yaml)", 0))
    rows.append(("auton-hosted (derived from PROVENANCE.json)", 0))

    # Probed: one paste, no questions about devices.
    load(ROOT / "agent" / "kernel_spec" / "targets" / "qemu-pc.md")
    rows.append(("vm (probed with lspci/cpuinfo/dmidecode)", 0))

    for label, answers in (
        ("microvm (elicited)",
         {"class": "microvm", "hypervisor": "firecracker", "machine": "default",
          "firmware": "none", "silicon": "unknown"}),
        ("vm (elicited, probe accepted)",
         {"class": "vm", "probe": "yes", "firmware": "bios",
          "silicon": "GenuineIntel 6 6 3"}),
        ("bare-metal (elicited, probe accepted)",
         {"class": "bare-metal", "probe": "yes", "firmware": "uefi",
          "silicon": "GenuineIntel 6 142 10"}),
        ("bare-metal (elicited, probe refused, 1 device)",
         {"class": "bare-metal", "probe": "no", "firmware": "uefi",
          "silicon": "GenuineIntel 6 142 10", "devices": "8086:100e network"}),
    ):
        draft, _ = run(answers)
        rows.append((label, draft.asked))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--answers", default="", help="k=v,k=v — non-interactive")
    ap.add_argument("--name", default="elicited")
    ap.add_argument("--out", metavar="FILE")
    ap.add_argument("--measure", action="store_true")
    args = ap.parse_args(argv)

    if args.measure:
        print(f"{'path':46s} questions")
        for label, n in measure():
            print(f"{label:46s} {n:>9d}")
        return 0

    supplied = dict(
        kv.split("=", 1) for kv in args.answers.split(",") if "=" in kv)

    if supplied:
        draft, notes = run(supplied, args.name)
    else:
        draft, notes = Draft(name=args.name), []
        while (q := next_question(draft)) is not None:
            print(q.render())
            try:
                reply = input("> ")
            except EOFError:
                break
            note = answer(draft, q, reply)
            if note:
                print(note)
                notes.append(note)

    for n in notes:
        print(n, file=sys.stderr)
    text = to_target(draft)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} after {draft.asked} question(s)")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
