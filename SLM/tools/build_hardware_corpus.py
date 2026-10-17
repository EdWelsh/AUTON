"""Generate the hardware reference corpus from AUTON's derived hardware tables.

os_chat.jsonl (build_corpus.py) teaches the kernel to answer about *this
machine*, and is pinned to what the kernel prints. This corpus is the other kind
of knowledge the data spec asks for (hardware documentation): who makes what,
which processors implement which instructions, how software detects them, and
where silicon disagrees with the documents.

The same rule holds: **every answer is generated from a table, never written.**

    agent/hardware/registry/vendors.json   PCI / USB / CPUID / MIDR vendor ids
    agent/hardware/isa/<arch>.json         processor -> features; x86 CPUID bits
    agent/hardware/isa/exceptions.yaml     never-shipped / removed / fused-off / ...

Each row's `fact` names the table row it came from, so a wrong answer can be
traced to a wrong table row and fixed there.

Kept separate from os_chat.jsonl on purpose. Vendor ids are exactly what the
phantom-citation measurement punished: a model that memorises 5,000 of them may
cite one for a question about a device that is not on the bus. Questions here
are phrased as reference questions ("which company has PCI vendor id ..."), and
mixing this corpus into chat training is a decision for the training config, to
be measured with eval_scope.py, not a default.

    python SLM/tools/build_hardware_corpus.py --output SLM/datasets/hardware_reference.jsonl
    python SLM/tools/build_hardware_corpus.py --profile kernel \
        --output SLM/datasets/hardware_kernel.jsonl

Two profiles, because the kernel's tokenizer decides what can be learned:

- **reference** (default): every vendor, processor and CPUID bit. 13,718 distinct
  words; it does NOT fit the in-kernel model's 1,024-word vocabulary
  (vocab_budget.py), so it is for a host-side model.
- **kernel**: questions about *this machine's* CPU, answered from what QEMU's
  default CPU model (qemu64, agent/hardware/isa/qemu.json) reports, the CPU every
  gate boots on. Vocabulary-bounded, and worded as a kernel implementing
  subsystems/cpu.md answers. A kernel's deterministic `cpu_has()` handler answers
  these first; the model learns the phrasings so the fallback agrees with it.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent" / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

REGISTRY = ROOT / "agent" / "hardware" / "registry" / "vendors.json"
ISA = ROOT / "agent" / "hardware" / "isa"

# Features worth asking about per processor: the ones a kernel or a user decides on.
NOTABLE = {
    "x86": ["sse2", "sse4.2", "avx", "avx2", "fma", "fma4", "xop", "avx512f", "rtm", "aes",
            "sha", "rdrnd", "rdseed", "bmi2", "popcnt", "movbe", "xsave", "fsgsbase", "invpcid",
            "cx16", "64bit", "amx-tile", "avx10.1-512", "sse4a", "tbm"],
    "aarch64": ["neon", "crc", "lse", "sve", "sve2", "sme", "aes", "sha2", "sha3", "pauth",
                "bti", "mte", "fullfp16", "dotprod", "i8mm", "bf16"],
    "riscv": ["m", "a", "f", "d", "c", "v", "zba", "zbb", "zbs", "zicsr", "zifencei", "h",
              "zfh", "zicbom"],
    "powerpc": ["altivec", "vsx", "power8-vector", "power9-vector", "power10-vector",
                "htm", "crypto", "mma", "64bit-support"],
    "systemz": ["vector", "vector-enhancements-1", "vector-enhancements-2", "transactional-execution",
                "nnp-assist", "message-security-assist-extension9", "guarded-storage"],
}
ARCH_NAME = {"x86": "x86", "aarch64": "AArch64", "riscv": "RISC-V", "powerpc": "POWER",
             "systemz": "IBM Z"}

VENDOR_Q = {
    "pci": ["which company has pci vendor id {i}", "who is pci vendor {i}",
            "pci vendor {i}", "what vendor is {i} on pci"],
    "usb": ["which company has usb vendor id {i}", "who is usb vendor {i}", "usb vendor {i}"],
    "x86-cpuid-vendor": ["which cpu vendor reports {q}", "who makes a cpu that says {q}",
                         "cpuid vendor string {q}"],
    "arm-midr-implementer": ["which arm implementer is {i}", "midr implementer {i}",
                             "who is arm implementer code {i}"],
}
HAS_Q = ["does {p} support {f}", "does {p} have {f}", "{f} on {p}?", "can {p} run {f}"]
CPUID_Q = ["how do i detect {f}", "which cpuid bit is {f}", "cpuid for {f}",
           "how does software know the cpu has {f}"]
EXC_Q = ["did {v} ever ship {f}", "is {f} available on {p}", "why is {f} missing on {p}",
         "{v} {f} history"]


def _row(text, response, fact, caps=("hardware-reference",)):
    return {"text": text, "response": response, "intent": "HARDWARE_IDENTIFY",
            "fact": fact, "caps": list(caps)}


def vendor_rows(reg: dict) -> list[dict]:
    rows = []
    for e in reg["vendors"]:
        for i in e["ids"]:
            # The name this id's own source gives: a merged entry's first spelling
            # can be another source's ("AuthenticAMD" is not "AMD/ATI").
            scheme, ident, name = i["scheme"], i["id"], i.get("name") or e["names"][0]
            for tmpl in VENDOR_Q.get(scheme, []):
                q = tmpl.format(i=ident, q=f'"{ident}"')
                if scheme == "x86-cpuid-vendor":
                    a = f'The CPUID vendor string "{ident}" is {name}.'
                elif scheme == "arm-midr-implementer":
                    a = f"Arm MIDR implementer {ident} is {name}."
                else:
                    a = f"{scheme.upper()} vendor id {ident} is assigned to {name}."
                rows.append(_row(q, a, f"registry:{scheme}:{ident}"))
    return rows


def feature_rows(arch: str, table: dict, exceptions: list[dict]) -> list[dict]:
    import isa_tables

    rows = []
    # Only features the table lists on some processor. One listed on none (x86 rtm,
    # avx10.1-512) is a feature LLVM does not record per part: asking about it
    # would answer "No" for every part, including the ones that ship it.
    notable = [f for f in NOTABLE.get(arch, []) if f in table["features"]
               and any(f in v for v in table["processors"].values())]
    for proc in table["processors"]:
        if proc in ("generic",):
            continue
        for f in notable:
            r = isa_tables.has({arch: table}, arch, proc, f, exceptions)
            kinds = ", ".join(n["kind"].replace("-", " ") for n in r["exceptions"])
            if r["verdict"].startswith("absent"):
                a = f"No: {f} is absent on {proc} ({kinds})."
            elif r["exceptions"]:
                a = (f"Maybe: {proc} can lack {f} ({kinds}). The documents and the silicon "
                     f"disagree here; only the running CPU's feature report can say.")
            elif r["nominal"]:
                a = (f"Yes: {proc} is listed with {f}. A kernel still checks the CPU's own "
                     f"feature report before using it.")
            else:
                a = f"No: {proc} is not listed with {f}."
            for tmpl in HAS_Q[:2]:
                rows.append(_row(tmpl.format(p=proc, f=f), a, f"isa:{arch}:{proc}:{f}"))
    return rows


def cpuid_rows(cpuid: dict) -> list[dict]:
    rows = []
    for name, rec in cpuid.items():
        flag = rec.get("cpuinfo") or name
        if rec.get("linux_defined") or not rec.get("leaf"):
            continue
        where = f"CPUID leaf {rec['leaf']}"
        if rec.get("subleaf") is not None:
            where += f" subleaf {rec['subleaf']}"
        reg = rec.get("register") or "?"
        a = f"{flag}: {where}, register {reg}, bit {rec['bit']}."
        if rec.get("description"):
            a += f" ({rec['description']})"
        for tmpl in CPUID_Q:
            rows.append(_row(tmpl.format(f=flag), a, f"cpuid:{name}"))
    return rows


def exception_rows(exceptions: list[dict]) -> list[dict]:
    rows = []
    for e in exceptions:
        procs = e["applies_to"] or [f"any {e.get('vendor', '')} part".strip()]
        note = " ".join(str(e.get("note", "")).split())
        src = e["source"] + ("" if e.get("verified") else " (not yet verified against the vendor document)")
        a = f"{e['feature']}: {e['kind'].replace('-', ' ')}. {note} Source: {src}."
        for p in procs[:4]:
            for tmpl in EXC_Q:
                rows.append(_row(tmpl.format(v=e.get("vendor", "the vendor"), f=e["feature"], p=p),
                                 a, f"exception:{e['arch']}:{e['feature']}:{e['kind']}"))
    return rows


CPU_WHAT_Q = ["what cpu is this", "which cpu do i have", "what processor is this", "cpu info",
              "show cpu", "what cpu", "which processor", "identify the cpu"]
CPU_LIST_Q = ["what features does this cpu have", "list cpu features", "cpu flags",
              "show cpu features", "what instructions does this cpu support", "cpu capabilities"]
CPU_HAS_Q = ["does this cpu support {f}", "does this machine have {f}", "can i use {f}",
             "is {f} available", "does this cpu have {f}", "{f} support"]


def kernel_rows(qemu: dict) -> list[dict]:
    """This machine's CPU, as QEMU's default model reports it."""
    name = qemu["default"]
    m = qemu["models"][name]
    who = (f"{m['vendor']} family {m['family']} model {m['model_number']} "
           f"stepping {m['stepping']} (QEMU {name})")
    have = set(m["features"])
    caps = ("cpu-features",)
    rows = []
    for q in CPU_WHAT_Q:
        for t in (q, q + "?"):
            rows.append(_row(t, f"This CPU is {who}.", f"qemu:{name}:identity", caps))
    listing = "This CPU reports: " + " ".join(sorted(have)) + "."
    for q in CPU_LIST_Q:
        for t in (q, q + "?"):
            rows.append(_row(t, listing, f"qemu:{name}:features", caps))
    for f in sorted(have | set(NOTABLE["x86"])):
        a = (f"Yes. This CPU reports {f}." if f in have
             else f"No. This CPU does not report {f}.")
        for tmpl in CPU_HAS_Q:
            q = tmpl.format(f=f)
            for t in (q, q + "?"):
                rows.append(_row(t, a, f"qemu:{name}:{f}", caps))
    return rows


def build_kernel(seed: int = 0) -> list[dict]:
    import qemu_cpu

    rows = [r for r in kernel_rows(qemu_cpu.load()) if not _is_eval_prompt(r["text"])]
    random.Random(seed).shuffle(rows)
    return rows


def _is_eval_prompt(text: str) -> bool:
    """The chat eval's prompts are held out of every corpus a kernel model trains
    on (build_corpus.py applies the same rule, with the same index)."""
    import build_corpus

    global _EVAL
    if "_EVAL" not in globals():
        _EVAL = build_corpus._eval_prompt_index()
    exact, token_sets = _EVAL
    norm = build_corpus._normalize(text)
    if norm in exact:
        return True
    mine = set(norm.split())
    return bool(mine) and any(len(mine & t) / len(mine | t) >= 0.9 for t in token_sets)


def build(seed: int = 0) -> list[dict]:
    import isa_tables

    reg = json.loads(REGISTRY.read_text())
    tables = isa_tables.load_tables()
    exceptions = isa_tables.load_exceptions()
    rows = vendor_rows(reg)
    for arch, t in tables.items():
        rows += feature_rows(arch, t, exceptions)
    rows += cpuid_rows(tables["x86"].get("cpuid", {}))
    rows += exception_rows(exceptions)
    seen, out = set(), []
    for r in rows:
        if r["text"] not in seen:          # one answer per question, first source wins
            seen.add(r["text"])
            out.append(r)
    random.Random(seed).shuffle(out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", default=str(ROOT / "SLM/datasets/hardware_reference.jsonl"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--profile", choices=["reference", "kernel"], default="reference")
    args = ap.parse_args(argv)
    if args.profile == "kernel" and args.output.endswith("hardware_reference.jsonl"):
        args.output = str(ROOT / "SLM/datasets/hardware_kernel.jsonl")
    rows = build_kernel(args.seed) if args.profile == "kernel" else build(args.seed)
    with open(args.output, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    by = {}
    for r in rows:
        k = r["fact"].split(":")[0]
        by[k] = by.get(k, 0) + 1
    print(f"{args.output}: {len(rows)} rows " + ", ".join(f"{k} {n}" for k, n in sorted(by.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
