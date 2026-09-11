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
PCI_KB = [
    ("8086", "100e", "Intel 82540EM Gigabit Ethernet (e1000)", "e1000"),
    ("8086", "10d3", "Intel 82574L Gigabit Ethernet (e1000e)", "e1000e"),
    ("1af4", "1000", "Virtio network device", "virtio-net"),
    ("1af4", "1001", "Virtio block device", "virtio-blk"),
]

# Devices present on the bus AUTON actually boots on, but absent from the KB.
# Teaching the honest "not in my knowledge base" answer needs real examples.
UNKNOWN_DEVICES = ["8086:1237", "8086:7000", "1234:1111", "10ec:8139", "1022:2000"]

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

# Live system facts as the kernel reports them.
SYS_FACTS = {
    "ip": "My IP is 10.0.2.15 (gateway 10.0.2.2, dns 10.0.2.3).",
    "hostname": "Hostname is auton.",
    "memory": "Memory: 255 MB RAM.",
    "devices": "Devices: 4 on PCI bus 0. 8086:1237 8086:7000 1234:1111 8086:100e(e1000)",
    "uptime": "Uptime: 12 seconds.",
    "status": "AUTON auton: IP 10.0.2.15, 255 MB RAM, 4 devices, up 12s.",
}

REFUSAL = ("I am AUTON, an operating system. I answer questions about this machine — "
           "its hardware, drivers, network and the roles it can run. I do not know about {topic}.")

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
                     "will it snow tomorrow", "how hot is it outside"]),
    ("world events or sport", ["who won the world cup", "what happened in the news",
                               "who is the president", "what won best picture"]),
    ("general trivia or arithmetic", ["what is 47 times 19", "how many continents are there",
                                      "what is the capital of france", "spell encyclopedia"]),
    ("creative writing", ["write me a poem", "tell me a joke", "write a short story",
                          "compose a haiku about disks"]),
]
NONSENSE = ["zxqw flibberty gronk", "asdfgh qwerty", "blorp zonk widget",
            "xyzzy plugh frotz", "qqq www eee"]


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


def build(seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
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

    def add(text: str, response: str, intent: str, fact: str) -> None:
        # Eval prompts are held out by construction. Dropping a phrasing costs
        # one paraphrase; keeping it would make every later score meaningless.
        if _collides(text):
            excluded["n"] += 1
            return
        rows.append({"text": text, "response": response, "intent": intent, "fact": fact})

    # HARDWARE_IDENTIFY — known devices
    for vendor, dev, desc, drv in PCI_KB:
        for tmpl in PCI_ID_Q:
            add(tmpl.format(v=vendor, d=dev), _pci_answer(desc, drv),
                "HARDWARE_IDENTIFY", f"pci:{vendor}:{dev}")
    # HARDWARE_IDENTIFY — honest misses
    for ident in UNKNOWN_DEVICES:
        v, d = ident.split(":")
        for tmpl in PCI_ID_Q[:8]:
            add(tmpl.format(v=v, d=d),
                f"Unknown PCI device {v}:{d}. No matching driver in the knowledge base.",
                "HARDWARE_IDENTIFY", f"pci-unknown:{ident}")

    # DRIVER_SELECT
    for vendor, dev, desc, drv in PCI_KB:
        for tmpl in DRIVER_Q:
            add(tmpl.format(v=vendor, d=dev), f"Recommended driver: {drv}.",
                "DRIVER_SELECT", f"driver:{vendor}:{dev}")
    for ident in UNKNOWN_DEVICES:
        v, d = ident.split(":")
        for tmpl in DRIVER_Q[:6]:
            add(tmpl.format(v=v, d=d),
                f"Unknown PCI device {v}:{d}. No matching driver in the knowledge base.",
                "DRIVER_SELECT", f"driver-unknown:{ident}")

    # INSTALL_CONFIGURE + SYSTEM_MANAGE — live state
    sys_intent = {"ip": "INSTALL_CONFIGURE", "hostname": "INSTALL_CONFIGURE",
                  "memory": "SYSTEM_MANAGE", "devices": "SYSTEM_MANAGE",
                  "uptime": "SYSTEM_MANAGE", "status": "SYSTEM_MANAGE"}
    for key, questions in SYS_Q.items():
        for q in questions:
            add(q, SYS_FACTS[key], sys_intent[key], f"sys:{key}")

    # APP_INSTALL — roles, working and roadmap
    for role, note in ROLES_WORKING:
        for tmpl in ROLE_Q:
            add(tmpl.format(r=role),
                f"Configuring this machine as a {role} ({note}).",
                "APP_INSTALL", f"role-working:{role}")
    for role, note in ROLES_ROADMAP:
        for tmpl in ROLE_Q:
            add(tmpl.format(r=role),
                f"Role '{role}': roadmap - {note}. I recognize the request and will run "
                f"it once that subsystem exists.",
                "APP_INSTALL", f"role-roadmap:{role}")

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
        ("how much ram is free", "Memory: 255 MB RAM total; the PMM reports free pages at boot."),
        ("what is my gateway", "Gateway is 10.0.2.2 (dns 10.0.2.3)."),
        ("what is my dns server", "DNS is 10.0.2.3 (gateway 10.0.2.2)."),
    ]
    for q, a in trouble:
        add(q, a, "TROUBLESHOOT", f"trouble:{q[:24]}")
        # a couple of natural variants so the mapping is not one-phrasing-deep
        add(q + "?", a, "TROUBLESHOOT", f"trouble:{q[:24]}")
        add("help - " + q, a, "TROUBLESHOOT", f"trouble:{q[:24]}")

    # OUT_OF_DOMAIN — declining is a first-class skill
    for topic, questions in OOD_TOPICS:
        for q in questions:
            add(q, REFUSAL.format(topic=topic), "OUT_OF_DOMAIN", f"ood:{topic}")
    for q in NONSENSE:
        add(q, REFUSAL.format(topic="that"), "OUT_OF_DOMAIN", "ood:nonsense")

    rng.shuffle(rows)
    print(f"  excluded {excluded['n']} phrasings colliding with the eval set")
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the AUTON chat corpus")
    ap.add_argument("--output", default="SLM/datasets/os_chat.jsonl")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    rows = build(args.seed)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
