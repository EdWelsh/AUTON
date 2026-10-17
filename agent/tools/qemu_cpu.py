"""What QEMU's built-in x86 CPU models report, read from QEMU's own definition table.

Every gate and acceptance run boots QEMU with no -cpu option, which emulates the
"qemu64" model. So qemu64's definition is ground truth for "this machine" in
tests, and for the SLM corpus rows about "this CPU". Read from
target/i386/cpu.c (`builtin_x86_defs[]`), fetched into .cache/vendor/ by
vendor_fetch.py; group macros such as PPRO_FEATURES are expanded.

What a running guest sees can still differ: TCG and KVM each filter features the
host cannot provide, and the guest adds the hypervisor bit. The kernel's own
`[CPU]` boot line (subsystems/cpu.md) is the final word; this is the model's
nominal definition.

    python agent/tools/qemu_cpu.py qemu64
    python agent/tools/qemu_cpu.py --build      # every built-in model -> agent/hardware/isa/qemu.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".cache" / "vendor" / "qemu" / "qemu-target-i386-cpu-c"
OUT = ROOT / "agent" / "hardware" / "isa" / "qemu.json"
DEFAULT_MODEL = "qemu64"     # what QEMU emulates with no -cpu option

VENDORS = {"CPUID_VENDOR_AMD": "AuthenticAMD", "CPUID_VENDOR_INTEL": "GenuineIntel",
           "CPUID_VENDOR_HYGON": "HygonGenuine", "CPUID_VENDOR_ZHAOXIN1": "CentaurHauls",
           "CPUID_VENDOR_ZHAOXIN2": "  Shanghai  "}
# QEMU spells a few bits differently from the names users and LLVM use.
RENAME = {"fp87": "fpu", "pni": "sse3", "lm": "64bit"}


class QemuCpuError(Exception):
    pass


def _text(path: Path = SOURCE) -> tuple[str, dict]:
    f = path / "cpu.c"
    prov = path / "provenance.json"
    if not f.is_file():
        raise QemuCpuError(f"{f} not fetched. Run: python agent/tools/vendor_fetch.py "
                           f"--vendor qemu --id qemu-target-i386-cpu-c")
    return f.read_text(errors="replace"), json.loads(prov.read_text()) if prov.exists() else {}


def _macros(text: str) -> dict[str, str]:
    out = {}
    # A continuation backslash must be tried before "any other character", or the
    # match stops at the first line end and PPRO_FEATURES loses SSE2.
    for m in re.finditer(r"#define\s+(\w+_FEATURES)\s+\(?((?:\\\n|[^\n])*)", text):
        out[m.group(1)] = m.group(2).replace("\\\n", " ")
    return out


def _bits(expr: str, macros: dict[str, str], depth: int = 0) -> list[str]:
    names = []
    for tok in re.findall(r"\b[A-Z][A-Z0-9_]+\b", expr):
        if tok in macros and depth < 4:
            names += _bits(macros[tok], macros, depth + 1)
        elif tok.startswith("CPUID_") and not tok.startswith("CPUID_VENDOR"):
            raw = re.sub(r"^CPUID_(?:EXT\d?_|7_\d_E[A-D]X_|XSAVE_|SVM_|6_EAX_|D_1_EAX_)?", "", tok)
            n = raw.lower()
            names.append(RENAME.get(n, n))
    return names


def model(name: str, path: Path = SOURCE) -> dict:
    text, prov = _text(path)
    m = re.search(r'\{\s*\.name\s*=\s*"' + re.escape(name) + r'",(.*?)\n    \},', text, re.S)
    if not m:
        raise QemuCpuError(f"no CPU model {name!r} in {path}")
    # The match stops before the closing brace; restore the newline the last
    # field's ",\n" terminator needs, or a model ending in .features loses them.
    body, macros = m.group(1) + "\n", _macros(text)

    def num(field):
        f = re.search(r"\." + field + r"\s*=\s*(0x[0-9a-fA-F]+|\d+)", body)
        return int(f.group(1), 0) if f else None

    vendor = re.search(r"\.vendor\s*=\s*(\w+)", body)
    feats = []
    for fm in re.finditer(r"\.features\[(\w+)\]\s*=\s*(.*?),\n", body, re.S):
        feats += _bits(fm.group(2), macros)
    return {"model": name, "vendor": VENDORS.get(vendor.group(1), vendor.group(1)) if vendor else None,
            "family": num("family"), "model_number": num("model"), "stepping": num("stepping"),
            "features": sorted(set(feats)),
            "source": {"document": "qemu-target-i386-cpu-c", "sha256": prov.get("sha256"),
                       "url": prov.get("source")}}


def build(path: Path = SOURCE) -> dict:
    text, prov = _text(path)
    start = text.index("builtin_x86_defs[]")
    names = re.findall(r'\n    \{\s*\n\s*\.name\s*=\s*"([^"]+)"', text[start:])
    models = {}
    for n in names:
        m = model(n, path)
        models[n] = {k: m[k] for k in ("vendor", "family", "model_number", "stepping", "features")}
    return {"default": DEFAULT_MODEL, "generated_from": [{"document": "qemu-target-i386-cpu-c",
            "sha256": prov.get("sha256"), "source": prov.get("source")}], "models": models}


def load() -> dict:
    return json.loads(OUT.read_text())


if __name__ == "__main__":
    try:
        if sys.argv[1:2] == ["--build"]:
            t = build()
            OUT.write_text(json.dumps(t, indent=1) + "\n")
            print(f"{OUT.relative_to(ROOT)}: {len(t['models'])} QEMU CPU models")
            raise SystemExit(0)
        print(json.dumps(model(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL), indent=1))
    except QemuCpuError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
