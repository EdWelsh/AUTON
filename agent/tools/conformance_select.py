"""Which conformance checks belong in THIS image (hardware-truth H10c).

    python agent/tools/conformance_select.py --binary build/kernel.bin
    python agent/tools/conformance_select.py --binary build/kernel.bin --out spec/conformance.json

A suite in one repository tests one researcher's machines; a suite in every
deployment tests every machine. But an image should carry the checks for the
instructions **its own code executes**, not the whole corpus: a kernel that
never divides a double has nothing to learn from a division check, and a suite
full of irrelevant checks is one nobody reads.

So the image's binary is disassembled, its mnemonics are normalised to the
spellings the SDM uses, and the corpus is intersected with that set.

**The normalisation is an explicit table, not a regex.** objdump speaks AT&T:
`fdivl`, `fdivs` and `fdivp` are all `FDIV`; `divsd` is `DIVSD` but `divss` is
single precision and a different entry; `data16` and `nopw` are padding. A
regex that "happens to work" on one build silently selects the wrong checks on
the next one, and a suite that tests the wrong instructions is worse than none.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "agent" / "kernel_spec" / "conformance"

# AT&T mnemonic -> SDM name. Only instructions the corpora can check appear
# here; everything else disassembles to itself and simply matches nothing.
#
# The x87 forms are the ones that matter historically: FDIV is the Pentium
# erratum's instruction, and objdump spells it five different ways depending on
# operand size and whether the stack is popped.
MNEMONICS = {
    "divsd": "DIVSD",
    "vdivsd": "DIVSD",
    "divpd": "DIVPD",
    "divss": "DIVSS",
    "sqrtsd": "SQRTSD",
    "vsqrtsd": "SQRTSD",
    "sqrtss": "SQRTSS",
    "fdiv": "FDIV",
    "fdivl": "FDIV",
    "fdivs": "FDIV",
    "fdivp": "FDIV",
    "fdivr": "FDIVR",
    "fdivrl": "FDIVR",
    "fdivrs": "FDIVR",
    "fdivrp": "FDIVR",
    "fsqrt": "FSQRT",
    "ud0": "UD0",
    "ud1": "UD1",
    "ud2": "UD2",
    "nop": "NOP",
    "nopl": "NOP",
    "nopw": "NOP",
}

# Prefixes and padding objdump prints as if they were instructions.
IGNORED = {"data16", "rex.w", "lock", "rep", "repz", "repnz", "cs", "ds", "es",
           "fs", "gs", "ss", "bad", "(bad)"}

DISASM_LINE = re.compile(r"^\s*[0-9a-f]+:\s+(?:[0-9a-f]{2} )+\s*(\S+)")


class SelectionError(Exception):
    pass


def objdump() -> str:
    for name in ("x86_64-elf-objdump", "objdump", "gobjdump"):
        if shutil.which(name):
            return name
    raise SelectionError("no objdump on PATH: cannot see what the image executes")


def disassemble(binary: Path, tool: str | None = None) -> str:
    tool = tool or objdump()
    r = subprocess.run([tool, "-d", str(binary)], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise SelectionError(f"{tool} failed on {binary}: {r.stderr.strip()[:200]}")
    return r.stdout


def instructions_in(disassembly: str) -> set[str]:
    """The SDM-named instructions this image executes."""
    found: set[str] = set()
    for line in disassembly.splitlines():
        m = DISASM_LINE.match(line)
        if not m:
            continue
        word = m.group(1).lower()
        if word in IGNORED:
            continue
        name = MNEMONICS.get(word)
        if name:
            found.add(name)
    return found


def corpus_entries(directory: Path = CORPUS) -> list[dict]:
    """Every entry, each carrying the instruction(s) it exercises."""
    out = []
    for path in sorted(directory.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        doc_instructions = [str(i) for i in (doc.get("instructions") or [])]
        for raw in doc.get("entries", []):
            ins = [str(raw["instruction"])] if raw.get("instruction") else doc_instructions
            if not ins:
                raise SelectionError(
                    f"{path.name}: {raw.get('id')} names no instruction, so no image can "
                    f"know whether it applies")
            out.append({"id": raw["id"], "clause": raw["clause"], "class": raw["class"],
                        "guarantee": raw["guarantee"], "instructions": ins,
                        "file": path.name})
    return out


def select(binary_instructions: set[str], directory: Path = CORPUS) -> list[dict]:
    return [e for e in corpus_entries(directory)
            if binary_instructions & set(e["instructions"])]


def uncovered(binary_instructions: set[str], directory: Path = CORPUS) -> set[str]:
    """Instructions the image executes that NO entry covers.

    Reported, not hidden: this is how the corpus learns what to grow. The base
    kernel's first run named DIVSS and SQRTSS, which is why the single-precision
    entries exist.
    """
    covered = {i for e in corpus_entries(directory) for i in e["instructions"]}
    return binary_instructions - covered


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    ap.add_argument("--objdump", default=None)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    found = instructions_in(disassemble(args.binary, args.objdump))
    chosen = select(found, args.corpus)
    total = len(corpus_entries(args.corpus))
    print(f"conformance: {len(chosen)} of {total} checks selected for {args.binary.name}")
    print(f"  instructions the image executes: "
          f"{', '.join(sorted(found)) if found else 'none the corpus covers'}")
    gap = uncovered(found, args.corpus)
    if gap:
        print(f"  NOT COVERED by any entry: {', '.join(sorted(gap))} — the image executes "
              f"these and nothing checks them")
    if not chosen:
        print("  nothing to check: this image executes none of the covered instructions, "
              "and a suite of checks it cannot exercise would be noise.")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(
            {"schema": 1, "image": args.binary.name,
             "instructions": sorted(found), "entries": chosen}, indent=1))
        print(f"  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
