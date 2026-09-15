"""Build a service image from its spec, with the gates wired.

F4 walked this path by hand: resolve the manifest, generate stubs, invoke make
with an explicit CSRC, build the ISO. Five of the seven defects that work found
were **disagreements between steps** — the stub generator compiling without the
build's defines, a source appearing twice because two steps each added it, a
stub list maintained separately from the check that reads it.

A pipeline that derives each thing once cannot reproduce those.

    python agent/tools/build_service.py dhcp --tree kernels/x86_64
    python agent/tools/build_service.py dhcp --tree kernels/x86_64 --iso
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_manifest import ManifestError, resolve  # noqa: E402
from gen_absent import GenerateError, generate  # noqa: E402
from intent_service import STUB_MARKER  # noqa: E402
from service_spec import ServiceSpecError, load as load_service  # noqa: E402

SERVICES = ROOT / "agent" / "kernel_spec" / "services"

# Compiler flags the kernel build needs. Kept here so every step that compiles
# — the stub generator and make — is handed the same list, which is the defect
# class this pipeline exists to remove.
KERNEL_CFLAGS = [
    "-ffreestanding", "-fno-stack-protector", "-fno-pic", "-fno-pie",
    "-mno-red-zone", "-mno-mmx", "-mno-sse", "-mno-sse2", "-mcmodel=kernel",
    "-Wall", "-Wextra", "-O2",
]

# A service that serves needs an address before it can serve. The DHCP server
# is the case that forces this: it cannot DHCP for itself.
STATIC_NET = {
    "NET_STATIC_IP":   "0x0A00020F",   # 10.0.2.15, what QEMU's NAT forwards to
    "NET_STATIC_MASK": "0xFFFFFF00",
    "NET_STATIC_GW":   "0x0A000202",
    "NET_STATIC_DNS":  "0x0A000203",
}


class GateFailure(Exception):
    """A gate refused the build. Always names which gate and why — 'build
    failed' sends someone reading a 200-line log to find out which step."""


@dataclass
class BuildResult:
    service: str
    sources: list[str] = field(default_factory=list)
    stubs: list[str] = field(default_factory=list)
    kernel_bytes: int = 0
    iso_bytes: int = 0
    gates: list[str] = field(default_factory=list)


def _service_sources(tree: Path, name: str) -> list[str]:
    """A service's own sources, which the capability map does not cover — the
    map describes the kernel, and a service is what is being added to it."""
    d = tree / "kernel" / "services" / name
    if not d.is_dir():
        return []
    return sorted(str(p.relative_to(tree)) for p in d.rglob("*.c"))


def gate_spec(name: str) -> "ServiceSpec":   # noqa: F821
    path = SERVICES / f"{name}.md"
    try:
        spec = load_service(path)
        spec.resolve()
    except ServiceSpecError as exc:
        raise GateFailure(f"[gate: spec] {exc}") from exc

    # intent-C emits a valid front-matter over an empty body. It passes every
    # structural check and is not implementable; an agent handed one will
    # implement it confidently and wrongly.
    if STUB_MARKER in path.read_text(encoding="utf-8"):
        raise GateFailure(
            f"[gate: spec] {name}.md still carries the generated-stub marker. "
            f"Its front-matter is real and its body is empty — fill in the "
            f"behaviour and delete the marker block before building from it."
        )
    return spec


def gate_leakage(tree: Path, excludes: list[str], stubs: Path) -> str:
    if not excludes:
        return "no excludes to check"
    script = ROOT / "tests" / "kernel" / "run_leakage_test.sh"
    env = {**os.environ, "KERNEL_TREE": str(tree)}
    r = subprocess.run(
        [str(script), "--excludes", ",".join(excludes), "--stubs", str(stubs)],
        capture_output=True, text=True, env=env, timeout=600)
    if r.returncode == 1:
        raise GateFailure(f"[gate: leakage] excluded capabilities are in the image\n"
                          f"{r.stdout.strip()}")
    if r.returncode == 2:
        return f"skipped ({r.stderr.strip().splitlines()[0] if r.stderr.strip() else 'nothing to check'})"
    return "clean"


def build(name: str, tree: Path, make_iso: bool = False, cc: str | None = None,
          jobs: int = 4) -> BuildResult:
    cc = cc or os.environ.get("CC") or "x86_64-elf-gcc"
    result = BuildResult(service=name)

    spec = gate_spec(name)
    result.gates.append("spec: valid, resolves, not a stub")

    extra = _service_sources(tree, name)
    try:
        included, _, _ = resolve(list(spec.requires), list(spec.excludes), tree)
    except ManifestError as exc:
        raise GateFailure(f"[gate: manifest] {exc}") from exc

    # Derived once, shared by every step below. The stub generator compiling
    # with different defines than the build is a defect that already happened.
    defines = [f"-D{k}={v}" for k, v in STATIC_NET.items()]

    absent = tree / "kernel" / "boot" / "absent.c"
    try:
        text, stubs = generate(tree, list(spec.requires), list(spec.excludes),
                               extra, cc, defines, output=absent, entry=spec.entry)
    except (GenerateError, ManifestError) as exc:
        raise GateFailure(f"[gate: link closure] {exc}") from exc
    absent.parent.mkdir(parents=True, exist_ok=True)
    absent.write_text(text, encoding="utf-8")
    stub_list = absent.with_suffix(".stubs")
    stub_list.write_text("\n".join(stubs) + "\n", encoding="utf-8")
    result.stubs = stubs
    result.gates.append(f"link closure: {len(stubs)} absence stub(s)")

    # One de-duplicated list. Two steps each appending the same file is how a
    # "multiple definition" error appears in a file nobody edited.
    rel = sorted({str(p.relative_to(tree)) for p in included} | set(extra)
                 | {str(absent.relative_to(tree))})
    csrc = [p for p in rel if p.endswith(".c")]
    asrc = [p for p in rel if p.endswith(".S")]
    result.sources = csrc + asrc

    cflags = " ".join(KERNEL_CFLAGS + ["-Ikernel/include"] + defines)
    target = ["iso"] if make_iso else []
    r = subprocess.run(
        ["make", "-C", str(tree), f"CC={cc}", f"CSRC={' '.join(csrc)}",
         f"ASRC={' '.join(asrc)}", f"CFLAGS={cflags}",
         f"GRUB_MKRESCUE={os.environ.get('GRUB_MKRESCUE', 'grub-mkrescue')}",
         f"-j{jobs}", *target],
        capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        undef = sorted({ln.split("`")[1].rstrip("'")
                        for ln in r.stderr.splitlines() + r.stdout.splitlines()
                        if "undefined reference to" in ln})
        detail = f"\n  undefined: {', '.join(undef)}" if undef else \
                 "\n" + "\n".join((r.stderr or r.stdout).strip().splitlines()[-6:])
        raise GateFailure(f"[gate: build] make failed{detail}")
    result.gates.append("build: linked")

    kernel = tree / "build" / "kernel.bin"
    if kernel.exists():
        result.kernel_bytes = kernel.stat().st_size
    iso = tree / "build" / "auton.iso"
    if make_iso and iso.exists():
        result.iso_bytes = iso.stat().st_size

    result.gates.append(f"leakage: {gate_leakage(tree, list(spec.excludes), stub_list)}")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("service")
    ap.add_argument("--tree", default="kernels/x86_64")
    ap.add_argument("--iso", action="store_true")
    ap.add_argument("--cc")
    ap.add_argument("--output", help="copy the ISO here")
    args = ap.parse_args(argv)

    tree = Path(args.tree)
    if not tree.is_absolute():
        tree = ROOT / tree

    try:
        r = build(args.service, tree, args.iso, args.cc)
    except GateFailure as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    print(f"built {r.service}: {len(r.sources)} sources, {r.kernel_bytes:,} bytes")
    for g in r.gates:
        print(f"  [ok] {g}")
    if r.iso_bytes:
        print(f"  iso: {r.iso_bytes:,} bytes")
    if args.output and r.iso_bytes:
        dest = Path(args.output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tree / "build" / "auton.iso", dest)
        print(f"  -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
