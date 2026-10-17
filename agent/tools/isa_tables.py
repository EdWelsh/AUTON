"""Which processors implement which instructions, derived from open machine-readable sources.

A vendor manual says what an instruction set extension IS. It rarely says, in one
place, which parts shipped it, and it never says which parts later lost it.
Three sources, three kinds of fact:

1. **Nominal availability per processor model** — LLVM's target definitions
   (X86.td, AArch64Processors.td, RISCVProcessors.td, PPC.td, SystemZProcessors.td).
   Every processor LLVM can target, with its feature list closed under
   implication (FMA4 implies AVX implies SSE4.2 ...).
2. **How software detects it** — the Linux kernel's cpufeatures.h: each x86
   feature's CPUID leaf, subleaf, register and bit.
3. **Where silicon or microcode disagrees with the nominal list** —
   agent/hardware/isa/exceptions.yaml, written by hand (or by a spec-reader
   agent), every row citing its source: an extension announced and never
   shipped, shipped and later removed, present in silicon but fused off, or
   disabled by a microcode update.

The kernel's rule follows from 3: **a document never proves an instruction is
there.** It says what may be there. CPUID (x86), ID_AA64*_EL1 (Arm), misa /
the ISA string (RISC-V) or the facility list (IBM Z) on the running machine is
the only proof, and the kernel uses an optional instruction only after asking.

    python agent/tools/isa_tables.py --build                 # write agent/hardware/isa/*.json
    python agent/tools/isa_tables.py --has znver1 fma4       # nominal + exceptions
    python agent/tools/isa_tables.py --cpuid fma4            # how to detect it
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "vendor"
OUT = ROOT / "agent" / "hardware" / "isa"
EXCEPTIONS = OUT / "exceptions.yaml"

# arch -> the cached documents that describe it, in include order.
ARCH_SOURCES = {
    "x86": ["llvm-x86-td"],
    "aarch64": ["llvm-aarch64-features-td", "llvm-aarch64-processors-td"],
    "riscv": ["llvm-riscv-features-td", "llvm-riscv-processors-td"],
    "powerpc": ["llvm-ppc-td"],
    "systemz": ["llvm-systemz-features-td", "llvm-systemz-processors-td"],
}
FEATURE_CLASSES = {"SubtargetFeature", "ExtensionWithMArch", "Extension", "Architecture64",
                   "SystemZFeature", "SystemZMissingFeature", "RISCVExtension",
                   "RISCVExperimentalExtension"}
PROCESSOR_CLASSES = {"Proc", "ProcModel", "ProcessorModel", "Processor",
                     "RISCVProcessorModel"}

EXCEPTION_KINDS = {
    "never-shipped": "announced or documented, never implemented in any shipped part",
    "removed": "shipped in earlier parts of the line, absent from later ones",
    "fused-off": "present in the silicon, disabled by fuse or firmware in shipped parts",
    "microcode-disabled": "shipped, then turned off by a microcode update",
    "undocumented": "implemented and works, but not reported by the feature flag",
}


class IsaError(Exception):
    pass


# --- a small TableGen reader ------------------------------------------------ #
# Not TableGen: enough of it to read processor and feature lists. Anything it
# cannot resolve is reported in "unresolved" rather than dropped.

def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _close(text: str, i: int) -> int:
    """Index just past the bracket that matches text[i] (one of < [ ( {)."""
    pairs = {"<": ">", "[": "]", "(": ")", "{": "}"}
    stack, j, in_str = [], i, False
    while j < len(text):
        c = text[j]
        if c == '"' and text[j - 1] != "\\":
            in_str = not in_str
        elif not in_str:
            if c in pairs:
                stack.append(pairs[c])
            elif stack and c == stack[-1]:
                stack.pop()
                if not stack:
                    return j + 1
        j += 1
    raise IsaError(f"unbalanced {text[i]!r} at offset {i}")


def split_args(s: str) -> list[str]:
    out, depth, cur, in_str = [], 0, [], False
    for c in s:
        if c == '"':
            in_str = not in_str
        if not in_str:
            if c in "<[({":
                depth += 1
            elif c in ">])}":
                depth -= 1
            elif c == "," and depth == 0:
                out.append("".join(cur).strip())
                cur = []
                continue
        cur.append(c)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


class TableGen:
    def __init__(self, texts: list[str]):
        self.defs: dict[str, tuple[str, list[str]]] = {}
        self.anon: list[tuple[str, list[str]]] = []
        self.lists: dict[str, str] = {}
        self.unresolved: set[str] = set()
        for t in texts:
            self._read(strip_comments(t))

    def _read(self, text: str) -> None:
        for m in re.finditer(r"\b(?:list<\w+>|defvar)\s+(\w+)\s*=\s*", text):
            end = text.index(";", m.end())
            # a list value may itself contain ';' only inside brackets; widen if so
            expr = text[m.end():end]
            while expr.count("[") != expr.count("]") or expr.count("(") != expr.count(")"):
                end = text.index(";", end + 1)
                expr = text[m.end():end]
            self.lists[m.group(1)] = expr.strip()
        for m in re.finditer(r"\bdef\s+(\w*)\s*:\s*(\w+)\s*<", text):
            name, cls = m.group(1), m.group(2)
            lt = m.end() - 1
            args = split_args(text[lt + 1:_close(text, lt) - 1])
            if name:
                self.defs[name] = (cls, args)
            else:
                self.anon.append((cls, args))

    def evaluate(self, expr: str) -> list[str]:
        """A list expression -> the def names it denotes."""
        expr = expr.strip()
        if not expr:
            return []
        if expr.startswith("["):
            out = []
            for item in split_args(expr[1:_close(expr, 0) - 1]):
                out.extend(self.evaluate(item))
            return out
        m = re.match(r"!(listconcat|listremove)\s*\(", expr)
        if m:
            p = m.end() - 1
            parts = [self.evaluate(a) for a in split_args(expr[p + 1:_close(expr, p) - 1])]
            if m.group(1) == "listconcat":
                return [x for part in parts for x in part]
            return [x for x in parts[0] if x not in set(parts[1])]
        if expr.endswith(".List"):
            cls, args = self.defs.get(expr[:-5], ("", []))
            if cls == "SystemZFeatureList":
                return self.evaluate(args[0])
            if cls == "SystemZFeatureAdd":
                return self.evaluate(args[0]) + self.evaluate(args[1])
        ident = expr.split(".")[-1]
        if ident in self.lists:
            return self.evaluate(self.lists[ident])
        if ident in self.defs and self.defs[ident][0] in FEATURE_CLASSES:
            return [ident]
        # Tuning* and PowerPC Directive* are scheduling hints, not instructions.
        if re.fullmatch(r"\w+", ident) and not ident.startswith(("Tuning", "Directive")):
            self.unresolved.add(ident)
        return []

    @staticmethod
    def _is_list(a: str) -> bool:
        return a.startswith("[") or a.startswith("!list")

    def feature(self, ident: str) -> dict:
        cls, args = self.defs[ident]
        strings = [a.strip('"') for a in args if a.startswith('"')]
        if cls == "Architecture64":
            name = args[3].strip('"')
        elif cls.startswith("RISCV"):       # RISCVExtension<major, minor, desc, ...>
            name = re.sub(r"^Feature(StdExt|Vendor)?", "", ident).lower()
        elif strings and strings[0]:
            name = strings[0]
        else:
            name = re.sub(r"^(Feature(StdExt|Vendor)?|Has)", "", ident).lower()
        implies = next((self.evaluate(a) for a in args if self._is_list(a)), [])
        desc = next((s for s in (strings if cls.startswith("RISCV") else strings[1:])
                     if " " in s), "")
        return {"name": name, "implies": implies, "description": desc}

    def processors(self) -> tuple[dict[str, list[str]], dict[str, str]]:
        procs, aliases = {}, {}
        for cls, args in self.anon + [v for v in self.defs.values()]:
            if cls == "ProcessorAlias":
                aliases[args[0].strip('"')] = args[1].strip('"')
            elif cls in PROCESSOR_CLASSES and args and args[0].startswith('"'):
                feat_arg = next((a for a in args[1:] if self._is_list(a) or "Features" in a
                                 or a.endswith(".List") or a.split(".")[-1] in self.lists),
                                "[]")
                procs[args[0].strip('"')] = self.evaluate(feat_arg)
        return procs, aliases


def closure(ident: str, feats: dict[str, dict], seen: set[str] | None = None) -> set[str]:
    seen = set() if seen is None else seen
    if ident in seen or ident not in feats:
        return seen
    seen.add(ident)
    for imp in feats[ident]["implies"]:
        closure(imp, feats, seen)
    return seen


def _cached_text(doc_id: str, cache: Path) -> tuple[str, dict]:
    vendor = "linux-kernel" if doc_id.startswith("linux-") else "llvm-project"
    d = cache / vendor / doc_id
    prov = d / "provenance.json"
    files = [p for p in d.iterdir() if p.is_file() and p.name != "provenance.json"] \
        if d.is_dir() else []
    if not prov.is_file() or not files:
        raise IsaError(f"{doc_id} not fetched. Run: python agent/tools/vendor_fetch.py "
                       f"--vendor {vendor} --id {doc_id}")
    return files[0].read_text(encoding="utf-8", errors="replace"), json.loads(prov.read_text())


def build_arch(arch: str, cache: Path = CACHE) -> dict:
    texts, sources = [], []
    for doc in ARCH_SOURCES[arch]:
        t, prov = _cached_text(doc, cache)
        texts.append(t)
        sources.append({"document": doc, "sha256": prov["sha256"], "source": prov["source"]})
    tg = TableGen(texts)
    feats = {k: tg.feature(k) for k, (cls, _) in tg.defs.items() if cls in FEATURE_CLASSES}
    procs, aliases = tg.processors()
    by_proc = {}
    for p, direct in sorted(procs.items()):
        ids: set[str] = set()
        for f in direct:
            closure(f, feats, ids)
        by_proc[p] = sorted({feats[i]["name"] for i in ids})
    return {
        "arch": arch, "generated_from": sources,
        "features": {feats[k]["name"]: {"def": k, "description": feats[k]["description"],
                                       "implies": sorted({feats[i]["name"] for i in
                                                          feats[k]["implies"] if i in feats})}
                     for k in sorted(feats)},
        "processors": by_proc, "aliases": dict(sorted(aliases.items())),
        "unresolved": sorted(tg.unresolved),
    }


# --- x86 detection: cpufeatures.h ------------------------------------------ #

def parse_cpufeatures(text: str) -> dict[str, dict]:
    """X86_FEATURE_* -> word, bit and, where the header says, the CPUID leaf."""
    words: dict[int, dict] = {}
    for m in re.finditer(r"/\*\s*(.*?),?\s*word\s+(\d+)\s*\*/", text):
        desc, w = m.group(1), int(m.group(2))
        lm = re.search(r"CPUID level (0x[0-9a-fA-F]+)(?::(\d+))?\s*(?:\((E[A-D]X)\)|,\s*(E[A-D]X))?",
                       desc)
        words[w] = {"leaf": lm.group(1).lower() if lm else None,
                    "subleaf": int(lm.group(2)) if lm and lm.group(2) else None,
                    "register": (lm.group(3) or lm.group(4)) if lm else None,
                    "linux_defined": lm is None}
        if lm and not words[w]["register"] and lm.group(1).lower() == "0x80000001" and w == 1:
            words[w]["register"] = "EDX"
    out = {}
    for m in re.finditer(r"#define\s+X86_FEATURE_(\w+)\s*\(\s*(\d+)\s*\*\s*32\s*\+\s*(\d+)\s*\)"
                         r"\s*(?:/\*\s*(.*?)\s*\*/)?", text):
        name, w, bit, comment = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4) or ""
        flag = re.match(r'"([^"]*)"', comment)
        rec = {"word": w, "bit": bit, **words.get(w, {"linux_defined": True}),
               "cpuinfo": flag.group(1) if flag else None,
               "description": re.sub(r'^"[^"]*"\s*', "", comment)}
        out[name.lower()] = rec
    return out


def load_exceptions(path: Path = EXCEPTIONS) -> list[dict]:
    if not path.exists():
        return []
    rows = yaml.safe_load(path.read_text()) or {}
    rows = rows.get("exceptions", [])
    for r in rows:
        for f in ("arch", "feature", "kind", "source"):
            if not r.get(f):
                raise IsaError(f"exception {r.get('feature', '?')}: missing {f!r}. An "
                               f"exception without a source is a rumour")
        if not isinstance(r.get("applies_to"), list):
            raise IsaError(f"exception {r['feature']}: applies_to must be a list "
                           f"([] means every part from {r.get('vendor', 'its vendor')})")
        if r["kind"] not in EXCEPTION_KINDS:
            raise IsaError(f"exception {r['feature']}: kind {r['kind']!r} not one of "
                           f"{', '.join(EXCEPTION_KINDS)}")
    return rows


# LLVM names processors, not their makers. x86 is the one architecture where two
# vendors share a feature namespace, so an exception for "every Intel part" needs it.
_X86_AMD = ("k6", "k8", "athlon", "opteron", "amdfam10", "barcelona", "btver", "bdver",
            "znver", "geode")
_X86_OTHER = {"c3": "centaur", "c3-2": "centaur", "winchip-c6": "centaur",
              "winchip2": "centaur", "lujiazui": "zhaoxin", "yongfeng": "zhaoxin"}


def vendor_of(arch: str, processor: str) -> str | None:
    if arch != "x86" or processor in ("generic", "x86-64", "x86-64-v2", "x86-64-v3",
                                      "x86-64-v4", "i386", "i486", "i586", "i686"):
        return None
    if processor in _X86_OTHER:
        return _X86_OTHER[processor]
    return "amd" if processor.startswith(_X86_AMD) else "intel"


def _applies(e: dict, arch: str, proc: str, asked: str) -> bool:
    if e["applies_to"]:
        return proc in e["applies_to"] or asked in e["applies_to"]
    return vendor_of(arch, proc) == e.get("vendor")


def has(tables: dict, arch: str, processor: str, feature: str,
        exceptions: list[dict] | None = None) -> dict:
    """What the sources say about one feature on one processor, and what to trust."""
    t = tables[arch]
    proc = t["aliases"].get(processor, processor)
    if proc not in t["processors"]:
        raise IsaError(f"{arch}: unknown processor {processor!r}")
    nominal = feature in t["processors"][proc]
    notes = [e for e in (exceptions or []) if e["arch"] == arch and e["feature"] == feature
             and _applies(e, arch, proc, processor)]
    return {"processor": proc, "feature": feature, "nominal": nominal, "exceptions": notes,
            # Undocumented behaviour is not a feature: the bit is clear, so it is absent.
            "verdict": (("absent: " if not nominal and all(
                n["kind"] in ("never-shipped", "removed", "undocumented") for n in notes)
                else "check at runtime: ")
                        + "; ".join(n["kind"] for n in notes)) if notes
            else ("listed: still check at runtime" if nominal else "not listed for this part")}


def build(cache: Path = CACHE) -> dict[str, dict]:
    tables = {arch: build_arch(arch, cache) for arch in ARCH_SOURCES}
    text, prov = _cached_text("linux-x86-cpufeatures-h", cache)
    tables["x86"]["cpuid"] = parse_cpufeatures(text)
    tables["x86"]["generated_from"].append({"document": "linux-x86-cpufeatures-h",
                                            "sha256": prov["sha256"], "source": prov["source"]})
    return tables


def write(tables: dict[str, dict]) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = []
    for arch, t in tables.items():
        p = OUT / f"{arch}.json"
        procs = ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in t["processors"].items())
        rest = {k: v for k, v in t.items() if k != "processors"}
        body = json.dumps(rest, indent=1, ensure_ascii=False)
        p.write_text(body[:-2] + ',\n "processors": {\n' + procs + "\n }\n}\n")
        paths.append(p)
    return paths


def load_tables() -> dict[str, dict]:
    return {a: json.loads((OUT / f"{a}.json").read_text()) for a in ARCH_SOURCES
            if (OUT / f"{a}.json").exists()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--arch", default="x86", choices=sorted(ARCH_SOURCES))
    ap.add_argument("--has", nargs=2, metavar=("PROCESSOR", "FEATURE"))
    ap.add_argument("--cpuid", metavar="FEATURE")
    args = ap.parse_args(argv)
    try:
        if args.build:
            tables = build()
            for p in write(tables):
                t = tables[p.stem]
                print(f"{p.relative_to(ROOT)}: {len(t['processors'])} processors, "
                      f"{len(t['features'])} features, {len(t['unresolved'])} unresolved")
            print(f"exceptions: {len(load_exceptions())} rows in {EXCEPTIONS.relative_to(ROOT)}")
            return 0
        tables = load_tables()
        if args.has:
            r = has(tables, args.arch, *args.has, load_exceptions())
            print(f"{r['processor']} {r['feature']}: nominal={r['nominal']} -> {r['verdict']}")
            for e in r["exceptions"]:
                print(f"  {e['kind']}: {e.get('note', '').strip()}  [{e['source']}]")
            return 0
        if args.cpuid:
            rec = tables["x86"].get("cpuid", {}).get(args.cpuid.lower())
            if not rec:
                print(f"no X86_FEATURE_{args.cpuid.upper()} in cpufeatures.h")
                return 1
            print(json.dumps(rec, indent=1))
            return 0
    except IsaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
