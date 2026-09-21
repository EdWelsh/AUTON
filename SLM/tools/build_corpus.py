"""Generate the AUTON chat corpus from the kernel's own ground truth.

Why synthesized rather than collected: the answers must be the strings this
kernel actually produces. A corpus of plausible-sounding OS answers would teach
the model confident wrongness, which the eval rubric prices as garbage. Here the
answer side is pinned to roles.c's capability table, slm.c's PCI knowledge base
and the system-query handlers, so what the model is taught and what is true of
the machine cannot drift apart.

Every record carries BOTH a question and an answer. The previous corpus stored
answers in a `next_action` field that the tokenizer never read, so the model was
fitted on questions alone and could not emit answer vocabulary at all.

Usage:
    python SLM/tools/build_corpus.py --output SLM/datasets/os_chat.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

# --- ground truth ---------------------------------------------------------- #
# Mirrors kernels/x86_64/kernel/slm/slm.c:kb_rules.
# Moved to agent/tools/device_drivers.py. The factory used to read its device
# knowledge from this file, so a change made to improve a training set silently
# changed what got built. The dependency now runs the other way.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent" / "tools"))
from device_drivers import PCI_DEVICE_DRIVERS as PCI_KB  # noqa: E402

# Every PCI id on the bus AUTON actually boots on, in bus order. Single source
# of truth: SYS_FACTS["devices"] and UNKNOWN_DEVICES are both derived from it,
# so the corpus cannot teach an id the machine does not have.
BUS_DEVICES = ["8086:1237", "8086:7000", "1234:1111", "8086:100e"]

# On the bus but absent from the KB — the honest "not in my knowledge base"
# answer needs real examples.
#
# This list previously carried 10ec:8139 and 1022:2000, which are on no bus this
# OS boots. 14 records each taught a deflection template with a real-looking id
# baked in, and the model emitted it for questions containing no device at all:
# `check for exposed APIs` came back citing a Realtek NIC. Measured at 5 phantom
# citations per 50 novel turns against 0 from the deterministic path. An id that
# is not on the bus must never appear in a response.
_KB_IDS = {f"{v}:{d}" for v, d, _, _ in PCI_KB}
UNKNOWN_DEVICES = [ident for ident in BUS_DEVICES if ident not in _KB_IDS]

# Mirrors kernels/x86_64/kernel/slm/roles.c:caps, de-duplicated by display name.
ROLES_WORKING = [
    ("web server", "in-kernel HTTP on port 80"),
    ("DNS server", "answers A queries on port 53 with this host's IP"),
]
ROLES_ROADMAP = [
    ("file server", "needs a filesystem; would serve a docroot over HTTP"),
    ("email server", "needs SMTP/IMAP and mail storage"),
    ("database server", "needs persistent storage and a query engine"),
    ("SSH server", "needs crypto (key exchange, ciphers) and a PTY"),
    ("DHCP server", "this host is a DHCP client; serving leases is next"),
    ("desktop apps", "the AUTON host control plane launches Win/Mac/Linux apps from chat; "
                     "in-kernel needs a process model + window system"),
    ("containers", "host control plane runs Docker today; in-kernel needs an OCI runtime"),
    ("kubernetes", "host control plane drives kubectl today; in-kernel needs a container "
                   "runtime + scheduler"),
    ("workloads", "the host control plane runs server/docker/k8s workloads from chat"),
]

def _devices_fact(shipped_drivers: set[str] | None = None) -> str:
    """The `devices` answer, rendered from BUS_DEVICES so it cannot disagree
    with what the corpus is allowed to cite.

    A device is annotated with its driver only when the image actually ships
    that driver. The NIC is on the bus of a Doom image too, but writing
    `8086:100e(e1000)` there claims a binding that does not exist.
    """
    parts = []
    for ident in BUS_DEVICES:
        v, d = ident.split(":")
        drv = next((k for kv, kd, _, k in PCI_KB if (kv, kd) == (v, d)), None)
        if drv and shipped_drivers is not None and drv not in shipped_drivers:
            drv = None
        parts.append(f"{ident}({drv})" if drv else ident)
    return f"Devices: {len(BUS_DEVICES)} on PCI bus 0. " + " ".join(parts)


# Live system facts as the kernel reports them.
SYS_FACTS = {
    "ip": "My IP is 10.0.2.15 (gateway 10.0.2.2, dns 10.0.2.3).",
    "hostname": "Hostname is auton.",
    "memory": "Memory: 255 MB RAM.",
    "devices": _devices_fact(),  # unscoped default
    "uptime": "Uptime: 12 seconds.",
    "status": "AUTON auton: IP 10.0.2.15, 255 MB RAM, 4 devices, up 12s.",
}

# Rendered per image: an OS with no network must not offer to answer questions
# about one. The declining behaviour itself is core and ships everywhere.
REFUSAL_TEMPLATE = ("I am AUTON, an operating system. I answer questions about this "
                    "machine — {subjects}. I do not know about {topic}.")

# --- question phrasings ----------------------------------------------------- #
# Many phrasings per fact: one phrasing per fact would reproduce exactly the
# brittleness the rule engine already has.

PCI_ID_Q = [
    "what is pci {v}:{d}", "identify device {v}:{d}", "what is device {v}:{d}",
    "tell me about {v}:{d}", "what hardware is {v}:{d}", "lookup pci {v}:{d}",
    "do you know {v}:{d}", "what is the device at {v}:{d}",
    "identify the pci device {v}:{d}", "which device is {v}:{d}",
    "what card is {v}:{d}", "describe pci {v}:{d}",
]
# Hardware questions carrying no PCI id. The model had no record for these, so
# it reached for the nearest neighbour — the unknown-device template — and
# emitted a deflection citing a device the asker never mentioned. The fix is not
# only to stop teaching off-bus ids (BUS_DEVICES) but to teach the behaviour
# that belongs here: ask for the id.
#
# Phrased by category, never by id, and kept clear of SYS_Q["devices"]
# ("what devices", "list devices"), which correctly answers with the bus list.
NO_ID_Q = [
    "what device is this", "identify this device", "what card is this",
    "tell me about this card", "lookup this device", "what is this chip",
    "which driver does this card need", "what driver for this device",
    "do i have a gpu", "what gpu do i have", "i need gpu access",
    "what graphics card is installed", "do i have a sound card",
    "what sound card do i have", "is there a usb controller",
    "what storage controller do i have", "identify my network card by name",
    "what model is my nic",
]

# No id, so no id may appear in the answer. It points at the one command that
# produces real ids instead of inventing one.
NO_ID_A = ("I identify devices by PCI id, not by category. Run `devices` to list "
           "what is on this bus, then ask me about a specific vendor:device id.")

DRIVER_Q = [
    "which driver for {v}:{d}", "what driver does {v}:{d} need",
    "recommend a driver for {v}:{d}", "driver for {v}:{d}",
    "what driver should i load for {v}:{d}", "which module handles {v}:{d}",
    "what kernel driver supports {v}:{d}", "pick a driver for {v}:{d}",
    "is there a driver for {v}:{d}", "what drives {v}:{d}",
]
ROLE_Q = [
    "can you be a {r}", "can you run a {r}", "be a {r}", "i need a {r}",
    "set up a {r}", "install a {r}", "turn this into a {r}",
    "would you run a {r}", "can this machine be a {r}", "configure a {r}",
    "start a {r}", "i want a {r} on this box", "make this a {r}",
    "is a {r} something you can do",
]
SYS_Q = {
    "ip": ["what is my ip", "what ip do i have", "tell me my ip address",
           "what is this machine's ip", "do i have an ip yet", "show my ip",
           "what address am i on", "what is my network address", "ip address please",
           "did i get an ip"],
    "hostname": ["what is my hostname", "what is this host called", "tell me the hostname",
                 "what name does this machine have", "show hostname", "who am i called",
                 "what is the machine name", "hostname?"],
    "memory": ["how much memory", "how much ram", "what is the memory size",
               "how much ram does this box have", "memory please", "show memory",
               "what is total ram", "how much memory is installed"],
    "devices": ["what devices", "list devices", "what hardware do you have",
                "show the pci bus", "what is attached", "how many devices are there",
                "enumerate the devices", "what is on the bus"],
    "uptime": ["uptime", "how long have you been up", "how long have you been running",
               "what is the uptime", "how long since boot", "time since boot"],
    "status": ["status", "give me a summary", "how is the system",
               "summarize this machine", "overall status", "system status",
               "give me an overview"],
}
OOD_TOPICS = [
    ("the weather", ["what is the weather", "is it raining", "what's the forecast",
                     "will it snow tomorrow", "how hot is it outside",
                     "weather report please", "is it sunny", "what's the temperature",
                     "do i need an umbrella", "how cold is it"]),
    ("world events or sport", ["who won the world cup", "what happened in the news",
                               "who is the president", "what won best picture",
                               "who won the election", "what is the score",
                               "tell me the headlines", "who is the prime minister",
                               "when is the next olympics", "what happened yesterday"]),
    ("general trivia or arithmetic", ["what is 47 times 19", "how many continents are there",
                                      "what is the capital of france", "spell encyclopedia",
                                      "what is 2 plus 2", "how many days in a year",
                                      "what is the square root of 64", "define photosynthesis",
                                      "how tall is everest", "what year was rome founded",
                                      "convert 10 miles to km", "what is 100 divided by 7"]),
    ("creative writing", ["write me a poem", "tell me a joke", "write a short story",
                          "compose a haiku about disks", "write a song",
                          "make up a limerick", "tell me a riddle", "write an essay"]),
    ("cooking, travel or health", ["how do i make bread", "what should i cook tonight",
                                   "book me a flight", "where should i go on holiday",
                                   "am i getting a cold", "how many calories in an apple",
                                   "recommend a restaurant"]),
]
NONSENSE = ["zxqw flibberty gronk", "asdfgh qwerty", "blorp zonk widget",
            "xyzzy plugh frotz", "qqq www eee", "hgfds lkjhg", "wibble wobble",
            "foo bar baz qux", "aaa bbb ccc", "mnbvc xzasd", "plover fjord",
            "glorp snark boojum", "ssss tttt uuuu", "random gibberish here"]


# Named software people ask for by product rather than by role. Measured:
# "can i run nginx" had "what roles can you run" as its nearest neighbour at
# 0.29 and was answered with a PCI-id clarification.
#
# The honest answer names the role AUTON *can* be, and says plainly that it
# does not run the binary — there is no process model to run one in. Claiming
# otherwise would be the capability bluffing the rubric exists to punish.
SOFTWARE_TO_ROLE = [
    (["nginx", "apache", "httpd", "caddy", "lighttpd"], "web server",
     "in-kernel HTTP on port 80"),
    (["bind", "dnsmasq", "unbound", "coredns"], "DNS server",
     "answers A queries on port 53"),
    (["postgres", "postgresql", "mysql", "mariadb", "sqlite", "redis"],
     "database server", "roadmap: needs persistent storage and a query engine"),
    (["openssh", "sshd", "dropbear"], "SSH server",
     "roadmap: needs crypto and a PTY"),
    (["postfix", "exim", "dovecot", "sendmail"], "email server",
     "roadmap: needs SMTP/IMAP and mail storage"),
    (["docker", "podman", "containerd"], "containers",
     "roadmap: needs an OCI runtime"),
]

SOFTWARE_Q = [
    "can i run {s}", "do you support {s}", "is {s} available",
    "can you run {s}", "i want to run {s}", "install {s}",
    "does this have {s}", "run {s} on this machine",
]

# How the network is configured, asked as a whole rather than field by field.
# The corpus taught `what is my ip` and `what is my gateway` separately and
# nothing that answered the general question, whose nearest neighbour was
# "i want a workloads on this box" at 0.27.
NETCONF_Q = [
    "how is the network set up", "describe the network configuration",
    "what is the network config", "tell me about networking here",
    "how is this machine networked", "summarise the network",
    "what are my network settings", "network configuration",
]

# --- shell idioms ----------------------------------------------------------- #
# People type Linux commands at an OS prompt. 15 of the 65 eval prompts are
# exactly this — `lsmod`, `meminfo`, `ip a`, `netstat -tulnp` — drawn from real
# human sessions, and the corpus taught **nothing** about them. The model
# therefore declined every one, which the rubric grades as garbage because the
# machine can answer most of them.
#
# The answers map an idiom to AUTON's own facts. They do not pretend to be
# Linux: `ps` is answered by saying there is no process model, because that is
# true and useful, where emulating `ps` output would be a fabrication.
#
# Each entry is (idiom phrasings, answer, capabilities the answer depends on).
# The eval's own idioms are excluded automatically by the collision filter, so
# what this teaches is the *class*, and the eval measures generalisation to
# idioms it has never seen.
SHELL_IDIOMS = [
    (["lspci", "list pci devices", "show pci", "pci list", "enumerate pci"],
     lambda f: f["devices"], {"dev"}),
    (["modinfo", "list modules", "show loaded modules", "what modules are loaded",
      "list drivers", "show drivers"],
     lambda f: f["drivers"], {"drivers"}),
    (["vmstat", "how much memory is in use", "memory usage", "show memory"],
     lambda f: f["memory"], {"mm"}),
    (["uname", "what system is this", "what os is this", "os version"],
     lambda f: "AUTON, an agent-built operating system. Not Linux: no kernel "
               "version string and no process model. What else is present "
               "depends on what this image was built for.", set()),
    (["ip addr", "ifconfig", "show my address", "what is my address"],
     lambda f: f["ip"], {"net"}),
    (["ip route", "show routing table", "what is my default gateway",
      "print the route table"],
     lambda f: "Gateway is 10.0.2.2 (dns 10.0.2.3). One route: everything "
               "non-local goes to the gateway.", {"net"}),
    (["ss -l", "list listening ports", "what ports are open", "show open ports"],
     lambda f: "Listening depends on the role. `be a web server` opens port 80; "
               "`be a DNS server` opens 53. Nothing listens by default.", {"net"}),
    (["ps aux", "list processes", "show running processes", "what is running"],
     lambda f: "AUTON has no process model. The kernel runs one thing at a time "
               "in ring 0, so there is nothing to list.", set()),
    (["df -h", "show disk usage", "how much disk space", "list mounts"],
     lambda f: "Nothing is mounted and nothing persists across a reboot in "
               "this image. Ask about storage if you need it.", set()),
    (["dmesg", "show the boot log", "kernel log", "print the log"],
     lambda f: "The boot log is on the serial console — every line prefixed "
               "[BOOT], [MM], [DEV], [SLM]. It is not stored, so it cannot be "
               "replayed.", {"sys"}),
    (["w", "who is logged in", "list users", "show sessions"],
     lambda f: "AUTON has no users and no login. The serial console is the only "
               "session.", set()),
    (["top", "show system load", "what is the load average"],
     lambda f: f["status"], {"sys"}),
]

# Roles the machine can be asked to become. The corpus taught the individual
# roles but never how to *list* them, so "which roles are available" was
# declined by a machine holding the list.
ROLE_LIST_Q = [
    "list the roles", "what roles can you run", "what can this machine become",
    "show me the roles", "what server roles do you support",
    "enumerate the roles", "which capabilities do you have",
    "what can you be", "what are my options",
]

def _pci_answer(desc: str, drv: str) -> str:
    return f"{desc}. Recommended driver: {drv}."


ROOT = Path(__file__).resolve().parents[2]
EVAL_PROMPTS = ROOT / "tests" / "eval" / "prompts.jsonl"


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9: ]+", "", text.lower()).strip()


def _eval_prompt_index() -> tuple[set[str], list[set[str]]]:
    """Normalized eval prompts, for exclusion at generation time.

    Natural phrasings collide with the eval set by construction — both are
    drawn from the same small domain — so filtering has to happen here, not be
    hoped for. SLM/tests/test_corpus_disjoint.py then verifies it held.
    """
    if not EVAL_PROMPTS.exists():
        raise SystemExit(f"eval prompt set not found: {EVAL_PROMPTS}. "
                         "The corpus cannot be built without it to exclude.")
    exact: set[str] = set()
    token_sets: list[set[str]] = []
    for line in EVAL_PROMPTS.read_text().splitlines():
        if not line.strip():
            continue
        prompt = json.loads(line)["prompt"]
        norm = _normalize(prompt)
        exact.add(norm)
        token_sets.append(set(norm.split()))
    return exact, token_sets


# --- capability scoping ----------------------------------------------------- #
# A manifest says which capabilities an image has. A record that talks about a
# capability the image does not have is not merely useless — it is the
# cross-intent mis-routing the 22% garbage rate is made of. An image with no
# network should have no DHCP-lease answer to reach for.
#
# Records carry the capabilities their *answer* depends on. An untagged record
# is core behaviour (declining out-of-domain questions, self-description) and
# ships in every image.

# Which capability a driver implies, so a NIC record is dropped from an image
# with no network without anyone maintaining a second list.
from device_drivers import DRIVER_CAPS  # noqa: E402,F401  (see PCI_KB above)

# Which capability each role needs before it could ever run.
ROLE_CAPS = {
    "web server": {"net"}, "DNS server": {"net"}, "file server": {"net", "fs"},
    "email server": {"net", "fs"}, "database server": {"fs"}, "SSH server": {"net"},
    "DHCP server": {"net"},
    # These four say in their own roadmap notes that they need a process model,
    # a scheduler or a container runtime. Tagging them {"sys"} left the
    # kubernetes roadmap in a Doom image — and "can i run nginx" answered with
    # the kubernetes roadmap is one of the measured garbage cases the scoping
    # hypothesis is about.
    "desktop apps": {"sched"}, "containers": {"sched"},
    "kubernetes": {"sched"}, "workloads": {"sched"},
}

SYS_CAPS = {
    "ip": {"net"}, "hostname": {"sys"}, "memory": {"mm"},
    "devices": {"dev"}, "uptime": {"sys"}, "status": {"sys"},
}


def _base_capability(entry: str) -> str:
    """`drivers(framebuffer, input)` -> `drivers`. The PRD writes manifests with
    parenthesised features; corpus scoping only needs the base name."""
    return entry.split("(", 1)[0].strip()


def _resolve_to_subsystems(tokens: set[str]) -> set[str]:
    """Map capability names to the subsystems that own them, keeping any token
    that is already a subsystem. Returns an empty set if the spec index is not
    importable, so corpus building never hard-depends on the agent package.
    """
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "agent" / "tools"))
        from capability_slice import capability_owner, load_specs
        owners = capability_owner(load_specs())
        specs = load_specs()
    except Exception:
        return set()
    out = set()
    for t in tokens:
        if t in specs:
            out.add(t)
        elif t in owners:
            out.add(owners[t])
        else:
            out.add(t)          # unknown: keep it, and let the caller notice
    return out


class Manifest:
    """A capability manifest. `excludes` is the load-bearing field — without it
    "minimal" cannot be tested, so it is required rather than defaulted."""

    def __init__(self, requires: list[str], excludes: list[str], intent: str = ""):
        self.intent = intent
        raw_req = {_base_capability(e) for e in requires}
        raw_exc = {_base_capability(e) for e in excludes}
        overlap = raw_req & raw_exc
        if overlap:
            raise ValueError(f"manifest both requires and excludes: {sorted(overlap)}")

        # Corpus records are tagged with subsystem-level capabilities (`net`,
        # `fs`), while a manifest may name either a subsystem or a fine-grained
        # capability (`ipv4`, `http-server`). Resolve through the spec index so
        # one manifest serves both this and the build's source resolution —
        # they disagreed about granularity until the intent compiler was
        # round-tripped against the hand-written pair.
        self.requires = _resolve_to_subsystems(raw_req) or raw_req
        self.excludes = _resolve_to_subsystems(raw_exc) or raw_exc

    @staticmethod
    def load(path: str | Path) -> "Manifest":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for field in ("requires", "excludes"):
            if field not in data:
                raise ValueError(f"{path}: manifest must declare '{field}'")
        return Manifest(data["requires"], data["excludes"], data.get("intent", ""))

    def admits(self, caps: set[str]) -> bool:
        """Core records (no caps) always ship. Otherwise every capability the
        answer depends on must be required, and none may be excluded."""
        if not caps:
            return True
        if caps & self.excludes:
            return False
        return caps <= self.requires


# The unscoped default: everything the corpus knows how to generate. Keeps
# `build()` with no manifest byte-identical to its previous behaviour.
UNSCOPED = Manifest(
    requires=["boot", "mm", "dev", "drivers", "net", "fs", "slm", "sys", "pkg",
              "ipc", "sched"],
    excludes=[],
)


# Vocabulary that betrays a capability in an answer. Used to tag the
# troubleshooting records, whose answers are written by hand, and — more
# importantly — to check the *built artifact* for leaks. A manifest's excludes
# are only meaningful if violating them is detectable on the output.
CAP_MARKERS = {
    "net": ("10.0.2.15", "10.0.2.2", "10.0.2.3", "dhcp", "gateway", "dns",
            "nic", "e1000", "virtio-net", "port 80", "network", "internet",
            "web server", "ip is", "my ip"),
    "fs": ("filesystem", "virtio-blk", "docroot", "mail storage",
           "persistent storage"),
    "mm": ("255 mb", "ram", "memory"),
    "dev": ("pci", "on the bus", "devices:"),
    "drivers": ("driver",),
}


def mentions(text: str, marker: str) -> bool:
    """Whole-token match, so `nic` does not fire inside `panic`."""
    return re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", text.lower()) is not None


def capabilities_mentioned(text: str) -> set[str]:
    return {cap for cap, words in CAP_MARKERS.items()
            if any(mentions(text, w) for w in words)}


def _infer_caps(*parts: str) -> set[str]:
    """Capabilities a record depends on, read from what it actually says.

    Reads the question as well as the answer: "what driver for a realtek nic"
    is a network question however the answer is phrased, and tagging on the
    answer alone left it in an image with no network.

    The troubleshooting answers are prose, so tagging them by hand would drift
    from their text the first time one is reworded. Reading the text keeps the
    tag and the answer in step; the leak test then checks the result
    independently, against the built artifact.
    """
    return capabilities_mentioned(" ".join(parts))


def _sys_facts(manifest: "Manifest") -> dict[str, str]:
    """Live-state answers, rendered for one image.

    `status` is a composite — it cites the IP, the RAM and the device count in
    one line. On an image with no network that sentence is simply false, and
    shipping it unchanged would teach the model to claim an address it does not
    have. It is assembled from the parts that are in scope instead.
    """
    parts = ["AUTON auton:"]
    if "net" in manifest.requires:
        parts.append("IP 10.0.2.15,")
    parts.append("255 MB RAM,")
    if "dev" in manifest.requires:
        parts.append(f"{len(BUS_DEVICES)} devices,")
    parts.append("up 12s.")
    shipped = {drv for drv, caps in DRIVER_CAPS.items()
               if caps <= manifest.requires}
    bound = [f"{drv} for {ident}" for ident in BUS_DEVICES
             for kv, kd, _, drv in PCI_KB
             if f"{kv}:{kd}" == ident and drv in shipped]
    drivers = ("Loaded drivers: " + ", ".join(bound) + ". AUTON binds drivers at "
               "boot; there is no runtime module loader."
               if bound else
               "No drivers are bound in this image beyond the console. AUTON "
               "binds at boot; there is no runtime module loader.")
    return {**SYS_FACTS,
            "devices": _devices_fact(shipped),
            "drivers": drivers,
            "status": " ".join(parts)}


def _refusal_subjects(manifest: "Manifest") -> str:
    """What the refusal claims this image can answer about. Listing `network`
    on an image with no network is the same defect as citing a PCI id that is
    not on the bus — an honest decline that advertises a capability it lacks."""
    subjects = ["its hardware"]
    if "drivers" in manifest.requires:
        subjects.append("drivers")
    if "net" in manifest.requires:
        subjects.append("network")
    subjects.append("the roles it can run")
    return ", ".join(subjects[:-1]) + " and " + subjects[-1]


def build(seed: int = 0, manifest: Manifest | None = None) -> list[dict]:
    manifest = manifest or UNSCOPED
    rng = random.Random(seed)
    out_of_scope = {"n": 0}
    sys_facts = _sys_facts(manifest)
    refusal = REFUSAL_TEMPLATE.replace("{subjects}", _refusal_subjects(manifest))
    rows: list[dict] = []
    eval_exact, eval_tokens = _eval_prompt_index()
    excluded = {"n": 0}

    def _collides(text: str) -> bool:
        norm = _normalize(text)
        if norm in eval_exact:
            return True
        mine = set(norm.split())
        if not mine:
            return False
        for et in eval_tokens:
            union = mine | et
            if union and len(mine & et) / len(union) >= 0.9:
                return True
        return False

    def add(text: str, response: str, intent: str, fact: str,
            caps: set[str] | None = None) -> None:
        # Scoping is checked first, but the eval-collision filter below is
        # unconditional: narrowing the corpus must never become a way to smuggle
        # an eval prompt back in.
        if not manifest.admits(caps or set()):
            out_of_scope["n"] += 1
            return
        # Eval prompts are held out by construction. Dropping a phrasing costs
        # one paraphrase; keeping it would make every later score meaningless.
        if _collides(text):
            excluded["n"] += 1
            return
        rows.append({"text": text, "response": response, "intent": intent,
                     "fact": fact, "caps": sorted(caps or ())})

    # HARDWARE_IDENTIFY — known devices
    for vendor, dev, desc, drv in PCI_KB:
        for tmpl in PCI_ID_Q:
            add(tmpl.format(v=vendor, d=dev), _pci_answer(desc, drv),
                "HARDWARE_IDENTIFY", f"pci:{vendor}:{dev}",
                {"dev"} | DRIVER_CAPS.get(drv, set()))
    # HARDWARE_IDENTIFY — honest misses
    for ident in UNKNOWN_DEVICES:
        v, d = ident.split(":")
        for tmpl in PCI_ID_Q[:8]:
            add(tmpl.format(v=v, d=d),
                f"Unknown PCI device {v}:{d}. No matching driver in the knowledge base.",
                "HARDWARE_IDENTIFY", f"pci-unknown:{ident}", {"dev"})

    # HARDWARE_IDENTIFY — no id given, so ask for one
    for q in NO_ID_Q:
        # "what model is my nic" is a network question whatever the answer
        # says, so the question is read too — otherwise it ships in an image
        # with no network and reintroduces exactly the cross-intent reach the
        # scoping is meant to remove.
        caps = {"dev"} | _infer_caps(q)
        add(q, NO_ID_A, "HARDWARE_IDENTIFY", "clarify:no-device-id", caps)
        add(q + "?", NO_ID_A, "HARDWARE_IDENTIFY", "clarify:no-device-id", caps)

    # SYSTEM_MANAGE — shell idioms mapped to this machine's own facts
    #
    # The largest single gap the eval measured: 15 of 65 prompts are shell
    # idioms and the corpus taught none of them, so the model declined all 15.
    # Answering from `sys_facts` keeps them grounded — no idiom invents a
    # number the machine does not have.
    for phrasings, answer_fn, caps in SHELL_IDIOMS:
        answer = answer_fn(sys_facts)
        for phrasing in phrasings:
            add(phrasing, answer, "SYSTEM_MANAGE", f"idiom:{phrasings[0]}", set(caps))
            add(phrasing + "?", answer, "SYSTEM_MANAGE", f"idiom:{phrasings[0]}", set(caps))
            add("run " + phrasing, answer, "SYSTEM_MANAGE", f"idiom:{phrasings[0]}", set(caps))

    # APP_INSTALL — software asked for by product name, answered by role
    for names, role, note in SOFTWARE_TO_ROLE:
        answer = (f"I do not run {names[0]} — there is no process model to run a "
                  f"binary in. What I can do is be a {role} ({note}). "
                  f"Ask for the role by name.")
        caps = ROLE_CAPS.get(role, set())
        for name in names:
            for tmpl in SOFTWARE_Q:
                add(tmpl.format(s=name), answer, "APP_INSTALL",
                    f"software:{role}", set(caps))

    # INSTALL_CONFIGURE — the network as a whole, not field by field
    for q in NETCONF_Q:
        add(q, sys_facts["ip"] + " " + f"Netmask 255.255.255.0, one NIC "
            f"(8086:100e, e1000).", "INSTALL_CONFIGURE", "sys:netconf", {"net"})
        add(q + "?", sys_facts["ip"] + " " + f"Netmask 255.255.255.0, one NIC "
            f"(8086:100e, e1000).", "INSTALL_CONFIGURE", "sys:netconf", {"net"})

    # APP_INSTALL — listing the roles, which the corpus never taught
    # Built from the roles this image could actually become. Listing a role
    # whose capabilities the manifest excludes is a capability claim the image
    # cannot honour — the same defect as a phantom PCI id, in a different field.
    working = [r for r, _ in ROLES_WORKING if manifest.admits(ROLE_CAPS.get(r, set()))]
    roadmap = [r for r, _ in ROLES_ROADMAP if manifest.admits(ROLE_CAPS.get(r, set()))]
    if working or roadmap:
        parts = []
        if working:
            parts.append(", ".join(working) + " (working)")
        if roadmap:
            parts.append(", ".join(roadmap[:4]) + " (roadmap)")
        role_list = "I can be: " + "; ".join(parts) + ". Ask for one by name."
        for q in ROLE_LIST_Q:
            add(q, role_list, "APP_INSTALL", "role:list")
            add(q + "?", role_list, "APP_INSTALL", "role:list")

    # DRIVER_SELECT
    for vendor, dev, desc, drv in PCI_KB:
        for tmpl in DRIVER_Q:
            add(tmpl.format(v=vendor, d=dev), f"Recommended driver: {drv}.",
                "DRIVER_SELECT", f"driver:{vendor}:{dev}",
                {"dev", "drivers"} | DRIVER_CAPS.get(drv, set()))
    for ident in UNKNOWN_DEVICES:
        v, d = ident.split(":")
        for tmpl in DRIVER_Q[:6]:
            add(tmpl.format(v=v, d=d),
                f"Unknown PCI device {v}:{d}. No matching driver in the knowledge base.",
                "DRIVER_SELECT", f"driver-unknown:{ident}", {"dev", "drivers"})

    # INSTALL_CONFIGURE + SYSTEM_MANAGE — live state
    sys_intent = {"ip": "INSTALL_CONFIGURE", "hostname": "INSTALL_CONFIGURE",
                  "memory": "SYSTEM_MANAGE", "devices": "SYSTEM_MANAGE",
                  "uptime": "SYSTEM_MANAGE", "status": "SYSTEM_MANAGE"}
    for key, questions in SYS_Q.items():
        for q in questions:
            add(q, sys_facts[key], sys_intent[key], f"sys:{key}", SYS_CAPS[key])

    # APP_INSTALL — roles, working and roadmap
    for role, note in ROLES_WORKING:
        for tmpl in ROLE_Q:
            add(tmpl.format(r=role),
                f"Configuring this machine as a {role} ({note}).",
                "APP_INSTALL", f"role-working:{role}", ROLE_CAPS.get(role, set()))
    for role, note in ROLES_ROADMAP:
        for tmpl in ROLE_Q:
            add(tmpl.format(r=role),
                f"Role '{role}': roadmap - {note}. I recognize the request and will run "
                f"it once that subsystem exists.",
                "APP_INSTALL", f"role-roadmap:{role}", ROLE_CAPS.get(role, set()))

    # TROUBLESHOOT — diagnostics over real state, including false premises
    trouble = [
        ("the network is down", "The NIC is up: 8086:100e bound to e1000, IP 10.0.2.15 from DHCP. "
                                "Nothing indicates a network fault."),
        ("my network is not working", "The NIC is up: 8086:100e bound to e1000, IP 10.0.2.15 from "
                                      "DHCP. Nothing indicates a network fault."),
        ("the nic is not working", "The NIC is up: 8086:100e bound to e1000, IP 10.0.2.15 from "
                                   "DHCP. Nothing indicates a network fault."),
        ("is anything wrong", "AUTON auton: IP 10.0.2.15, 255 MB RAM, 4 devices, up 12s. "
                              "No faults detected."),
        ("is this machine healthy", "AUTON auton: IP 10.0.2.15, 255 MB RAM, 4 devices, up 12s. "
                                    "No faults detected."),
        ("did dhcp succeed", "Yes. DHCP assigned 10.0.2.15, gateway 10.0.2.2, dns 10.0.2.3."),
        ("check whether dhcp worked", "Yes. DHCP assigned 10.0.2.15, gateway 10.0.2.2, "
                                      "dns 10.0.2.3."),
        ("why can i not reach the internet",
         "Networking is user-mode NAT: outbound works through the gateway at 10.0.2.2, "
         "inbound needs a host port forward."),
        ("my web server is not responding",
         "Check the web server is running (be a web server) and that port 80 is forwarded "
         "from the host."),
        ("what driver is loaded", "The e1000 driver is loaded for 8086:100e."),
        ("which driver is currently in use", "The e1000 driver is loaded for 8086:100e."),
        ("what is my gateway", "Gateway is 10.0.2.2 (dns 10.0.2.3)."),
        ("what is my dns server", "DNS is 10.0.2.3 (gateway 10.0.2.2)."),
        ("tell me about the network card",
         "Intel 82540EM Gigabit Ethernet (e1000) at 8086:100e, driver e1000 loaded."),
        ("describe the network card",
         "Intel 82540EM Gigabit Ethernet (e1000) at 8086:100e, driver e1000 loaded."),
        ("what network card is in this machine",
         "Intel 82540EM Gigabit Ethernet (e1000) at 8086:100e, driver e1000 loaded."),
        ("which driver is loaded right now", "The e1000 driver is loaded for 8086:100e."),
        ("what driver am i using", "The e1000 driver is loaded for 8086:100e."),
        ("is e1000 loaded", "Yes. The e1000 driver is loaded for 8086:100e."),
        ("which driver should i use for my nic",
         "The NIC is 8086:100e; its driver is e1000, already loaded."),
        ("what driver does my network card need",
         "The NIC is 8086:100e; its driver is e1000, already loaded."),
        ("do you have a driver for the intel gigabit card",
         "Yes. 8086:100e is Intel 82540EM Gigabit Ethernet; driver e1000."),
        ("what driver would a realtek card need",
         "Realtek is not in the knowledge base. Give me its PCI id and I will look it up."),
        ("what about a broadcom card",
         "Broadcom is not in the knowledge base. Give me its PCI id and I will look it up."),
        ("how much free memory is there",
         "Memory: 255 MB RAM total. The PMM tracks free pages; free memory is not "
         "reported separately yet."),
        ("how much memory is available",
         "Memory: 255 MB RAM total. The PMM tracks free pages; free memory is not "
         "reported separately yet."),
        ("why is boot slow",
         "Boot time is not instrumented. Uptime since boot is reported by 'uptime'."),
        ("why did the boot take so long",
         "Boot time is not instrumented. Uptime since boot is reported by 'uptime'."),
        ("i cannot reach the internet",
         "Networking is user-mode NAT: outbound works through the gateway at 10.0.2.2, "
         "inbound needs a host port forward."),
        ("no internet access from this box",
         "Networking is user-mode NAT: outbound works through the gateway at 10.0.2.2, "
         "inbound needs a host port forward."),
        ("the network is unreachable",
         "Networking is user-mode NAT: outbound works through the gateway at 10.0.2.2, "
         "inbound needs a host port forward."),
        ("what should i check if the web server does not respond",
         "Check the web server is running (be a web server) and that port 80 is forwarded "
         "from the host."),
        # DHCP client state kept routing to the DHCP *server* roadmap answer:
        # the words overlap, and the corpus had one phrasing for the client case.
        ("did dhcp give me an address",
         "Yes. DHCP assigned 10.0.2.15, gateway 10.0.2.2, dns 10.0.2.3."),
        ("was dhcp successful", "Yes. DHCP assigned 10.0.2.15, gateway 10.0.2.2, dns 10.0.2.3."),
        ("check dhcp", "Yes. DHCP assigned 10.0.2.15, gateway 10.0.2.2, dns 10.0.2.3."),
        ("is dhcp working", "Yes. DHCP assigned 10.0.2.15, gateway 10.0.2.2, dns 10.0.2.3."),
        ("did i get a lease", "Yes. DHCP assigned 10.0.2.15, gateway 10.0.2.2, dns 10.0.2.3."),
        ("did the dhcp client get an address",
         "Yes. DHCP assigned 10.0.2.15, gateway 10.0.2.2, dns 10.0.2.3."),
        # Gateway/DNS as first-class questions, not only inside the IP answer.
        ("what is the gateway", "Gateway is 10.0.2.2 (dns 10.0.2.3)."),
        ("what gateway am i using", "Gateway is 10.0.2.2 (dns 10.0.2.3)."),
        ("tell me the gateway", "Gateway is 10.0.2.2 (dns 10.0.2.3)."),
        ("what is the default route", "Gateway is 10.0.2.2 (dns 10.0.2.3)."),
        ("which dns server am i using", "DNS is 10.0.2.3 (gateway 10.0.2.2)."),
        # Free vs total memory was answered with the total.
        ("how much ram is free",
         "Memory: 255 MB RAM total. The PMM tracks free pages; free memory is not "
         "reported separately yet."),
        ("how much free ram",
         "Memory: 255 MB RAM total. The PMM tracks free pages; free memory is not "
         "reported separately yet."),
        ("what is free memory",
         "Memory: 255 MB RAM total. The PMM tracks free pages; free memory is not "
         "reported separately yet."),
        # Diagnostic phrasings that were answered with a device dump.
        ("the nic is broken what do i do",
         "The NIC is up: 8086:100e bound to e1000, IP 10.0.2.15 from DHCP. "
         "Nothing indicates a network fault."),
        ("help me fix the network",
         "The NIC is up: 8086:100e bound to e1000, IP 10.0.2.15 from DHCP. "
         "Nothing indicates a network fault."),
        ("what should i check for a web server problem",
         "Check the web server is running (be a web server) and that port 80 is forwarded "
         "from the host."),
        ("the web server does not answer",
         "Check the web server is running (be a web server) and that port 80 is forwarded "
         "from the host."),
        # Unknown-vendor driver questions answered with e1000.
        ("what driver for a realtek nic",
         "Realtek is not in the knowledge base. Give me its PCI id and I will look it up."),
        ("driver for realtek",
         "Realtek is not in the knowledge base. Give me its PCI id and I will look it up."),
        ("do you support realtek cards",
         "Realtek is not in the knowledge base. Give me its PCI id and I will look it up."),
        ("the nic seems broken",
         "The NIC is up: 8086:100e bound to e1000, IP 10.0.2.15 from DHCP. "
         "Nothing indicates a network fault."),
    ]
    for q, a in trouble:
        caps = _infer_caps(q, a)
        add(q, a, "TROUBLESHOOT", f"trouble:{q[:24]}", caps)
        # a couple of natural variants so the mapping is not one-phrasing-deep
        add(q + "?", a, "TROUBLESHOOT", f"trouble:{q[:24]}", caps)
        add("help - " + q, a, "TROUBLESHOOT", f"trouble:{q[:24]}", caps)

    # OUT_OF_DOMAIN — declining is a first-class skill
    for topic, questions in OOD_TOPICS:
        for q in questions:
            add(q, refusal.format(topic=topic), "OUT_OF_DOMAIN", f"ood:{topic}")
    for q in NONSENSE:
        add(q, refusal.format(topic="that"), "OUT_OF_DOMAIN", "ood:nonsense")

    rng.shuffle(rows)
    print(f"  excluded {excluded['n']} phrasings colliding with the eval set")
    if out_of_scope["n"]:
        print(f"  dropped {out_of_scope['n']} records outside the manifest "
              f"(excludes: {', '.join(sorted(manifest.excludes)) or 'none'})")
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the AUTON chat corpus")
    ap.add_argument("--output", default="SLM/datasets/os_chat.jsonl")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--manifest", default=None,
                    help="capability manifest; generate only the intents this "
                         "image serves. Unscoped when omitted.")
    ap.add_argument("--min-tokens", type=int, default=2048,
                    help="floor below which train.py cannot form a batch "
                         "(seq_len x batch_size). Default 64x32.")
    args = ap.parse_args(argv)

    manifest = Manifest.load(args.manifest) if args.manifest else None
    if manifest:
        print(f"scoping to {args.manifest}"
              + (f" — {manifest.intent!r}" if manifest.intent else ""))
    rows = build(args.seed, manifest)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    intents: dict[str, int] = {}
    for r in rows:
        intents[r["intent"]] = intents.get(r["intent"], 0) + 1
    print(f"wrote {out} — {len(rows)} records, {out.stat().st_size} bytes")
    for k in sorted(intents):
        print(f"  {k:20s} {intents[k]}")
    print(f"  distinct answers: {len({r['response'] for r in rows})}")
    print(f"  distinct facts:   {len({r['fact'] for r in rows})}")

    # Rung 3a produced a 61-token corpus and train.py rejected it at the stock
    # 64x32, after the tokenizer had already run. Scoping makes that failure
    # much more likely, so it is caught here — where the fix is a smaller batch
    # or more in-scope paraphrases, not a mystery three stages later.
    approx = sum(len(r["text"].split()) + len(r["response"].split()) for r in rows)
    print(f"  approx tokens:    {approx}")
    if approx < args.min_tokens:
        print(f"WARNING: ~{approx} tokens is below the {args.min_tokens} floor. "
              f"train.py cannot form a batch at the default seq_len x batch_size; "
              f"lower --batch-size or add in-scope paraphrases — never "
              f"out-of-scope classes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
