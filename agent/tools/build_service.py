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
TEMPLATES = ROOT / "agent" / "kernel_spec" / "templates"


def scaffold(tree: Path, arch: str = "x86_64") -> list[str]:
    """Lay the build scaffolding into a target tree.

    AUTON contains no kernel — agents write the source. But a tree still needs a
    Makefile, a linker script and a toolchain fragment before anything can be
    compiled, and those are identical for every image. Emitting them is the
    factory's job; authoring them is not an agent's.

    Existing files are left alone, so this is safe to run over a tree an agent
    has already written into.
    """
    src = TEMPLATES / arch
    if not src.is_dir():
        raise GateFailure(f"[gate: scaffold] no template for arch {arch!r} in {TEMPLATES}")

    placed: list[str] = []
    for item in sorted(src.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(src)
        # arch/ files belong under the kernel's arch directory; the rest sit at
        # the tree root.
        dest = (tree / "kernel" / "arch" / arch / rel.name if rel.parts[0] == "arch"
                else tree / rel)
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dest)
        placed.append(str(dest.relative_to(tree)))
    return placed

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
    leakage_report: Path | None = None
    # What each driver's own verification said. Kept as an object rather than a
    # boolean: `unverified` is a third state and flattening it would lose the
    # distinction the gate exists for.
    driver_report: object | None = None
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


# Which capabilities name a concrete device. `nvme` and `ahci` are not here,
# and that is the honest state: they are PCI class-coded devices, not single
# ids, and the ingested registry holds device records only. The gate names a
# device when it can and says the capability's name when it cannot — it does
# not invent "NVM Express controller" out of a class code nothing ingested.
CAPABILITY_DEVICES = {
    "e1000": "8086:100e",
    "e1000e": "8086:10d3",
    "virtio-net": "1af4:1000",
    "virtio-blk": "1af4:1001",
}


def _patterns_for(capability: str) -> tuple[str, ...]:
    """What the map claims implements this. Named in the refusal so the reader
    can see the pattern rather than go looking for it."""
    from build_manifest import SourceMap
    return tuple(SourceMap.load().capabilities.get(capability, ()))


def _owner(capability: str) -> str:
    """Which subsystem spec claims to provide this. The refusal names it so the
    reader knows which spec promised something the tree does not deliver."""
    from capability_slice import load_specs
    for name, spec in load_specs().items():
        if capability in spec.provides:
            return name
    return "no subsystem"


def gate_capabilities(spec, report: dict) -> None:
    """Refuse a build whose spec requires a capability this tree cannot implement.

    The failure this prevents is specific and was measured: a manifest requiring
    `nvme` resolves to a closed slice, passes every other gate, and produces an
    image with no storage driver in it. Nothing was broken — `resolve()` computed
    `unmapped_capabilities` correctly and put it in a report field that the
    pipeline never read. So this gate makes existing, correct information
    load-bearing rather than deriving anything new.

    Consumes the report rather than recomputing it. A second copy of
    `resolve()`'s rules — `core_provides`, transitive capabilities — would drift
    from the first, and the two disagreeing is worse than either being wrong.
    """
    unmapped = set(report.get("unmapped_capabilities") or [])
    # Mapped, and nothing behind the mapping. A different problem with a
    # different fix, so a different message — one needs a mapping added, the
    # other has one that lies.
    phantom = set(report.get("phantom_capabilities") or [])
    # Only what the spec asked for directly. A capability pulled in transitively
    # is a weaker case: the spec never named it, and refusing the build would
    # blame the author for a dependency they did not choose.
    offending = sorted(unmapped & set(spec.requires))
    offending_phantom = sorted(phantom & set(spec.requires) - unmapped)

    if offending_phantom:
        lines = []
        for cap in offending_phantom:
            pats = ", ".join(_patterns_for(cap))
            lines.append(f"    {cap}  — ({_owner(cap)})   maps to {pats}, "
                         f"which matches no source in this tree")
        raise GateFailure(
            "[gate: capabilities] the spec requires capabilities whose source "
            "mapping points at nothing:\n" + "\n".join(lines) +
            "\n  A glob matching nothing is not an error, so the build would "
            "succeed and the image would contain no implementation. Remove the "
            "mapping until the source exists — an absent mapping refuses "
            "honestly; one that lies does not.")

    if not offending:
        return

    lines = []
    for cap in offending:
        detail = f"{cap}  — ({_owner(cap)})"
        dev = CAPABILITY_DEVICES.get(cap)
        if dev:
            from device_registry import identify
            ident = identify(dev)
            # An unidentifiable device is not a reason to allow an
            # unimplementable build. The gate fires either way; the name is a
            # courtesy the registry may or may not be able to supply.
            detail += f" {ident.title} ({dev})" if ident else f" {dev}"
        lines.append(f"    {detail}   no source mapping")

    raise GateFailure(
        "[gate: capabilities] the spec requires capabilities this tree cannot "
        "implement:\n" + "\n".join(lines) +
        "\n  A slice containing them resolves and builds; the image would simply "
        "not contain the driver. Add a mapping in source_map.yaml, or remove the "
        "requirement."
    )


def gate_leakage(tree: Path, excludes: list[str], stubs: Path, image: Path,
                 report: Path | None = None) -> str:
    if not excludes:
        # excludes is mandatory in every manifest: without it "minimal" is
        # unfalsifiable, so an empty one is a finding rather than a clean pass.
        raise GateFailure(
            "[gate: leakage] the spec declares no excludes. Without them there "
            "is nothing to verify absent, and 'minimal' is an opinion."
        )
    if not image.exists():
        raise GateFailure(f"[gate: leakage] no image at {image} to inspect")
    script = ROOT / "tests" / "kernel" / "run_leakage_test.sh"
    env = {**os.environ, "KERNEL_TREE": str(tree)}
    args = [str(script), "--excludes", ",".join(excludes), "--stubs", str(stubs),
            "--image", str(image)]
    if report:
        args += ["--report", str(report)]
    r = subprocess.run(args, capture_output=True, text=True, env=env, timeout=600)
    if r.returncode == 1:
        raise GateFailure(f"[gate: leakage] excluded capabilities are in the image\n"
                          f"{r.stdout.strip()}")
    if r.returncode == 2:
        return f"skipped ({r.stderr.strip().splitlines()[0] if r.stderr.strip() else 'nothing to check'})"
    return "clean"


def build(name: str, tree: Path, make_iso: bool = False, cc: str | None = None,
          jobs: int = 4, target=None, verify_drivers: bool = False) -> BuildResult:
    cc = cc or os.environ.get("CC") or "x86_64-elf-gcc"
    result = BuildResult(service=name)

    spec = gate_spec(name)
    result.gates.append("spec: valid, resolves, not a stub")

    placed = scaffold(tree)
    if placed:
        result.gates.append(f"scaffold: laid {len(placed)} build file(s)")
    if not (tree / "kernel").is_dir() or not any((tree / "kernel").rglob("*.c")):
        raise GateFailure(
            f"[gate: sources] {tree} has build scaffolding but no kernel source. "
            f"AUTON contains no kernel — agents write it against "
            f"kernel_spec/subsystems/. Point --tree at a tree they have written."
        )

    extra = _service_sources(tree, name)
    try:
        included, _, manifest_report = resolve(
            list(spec.requires), list(spec.excludes), tree)
    except ManifestError as exc:
        raise GateFailure(f"[gate: manifest] {exc}") from exc

    # Before the stub generator: an unimplementable capability would otherwise
    # be papered over by an absence stub and linked into a working image.
    gate_capabilities(spec, manifest_report)
    result.gates.append(
        f"capabilities: {len(manifest_report['capabilities'])} required, all mapped")

    # Before the stub generator, for the same reason the capabilities gate is:
    # a driver whose own stated check fails would otherwise be papered over by
    # an absence stub and linked into an image that builds cleanly.
    if target is not None:
        from driver_verify import gate as gate_drivers

        driver_report = gate_drivers(target, slow=verify_drivers)
        counts = driver_report.counts()
        result.driver_report = driver_report
        result.gates.append(
            f"drivers: {counts['verified']} verified, "
            f"{counts['unverified']} unverified")

    # Derived once, shared by every step below. The stub generator compiling
    # with different defines than the build is a defect that already happened.
    defines = [f"-D{k}={v}" for k, v in STATIC_NET.items()]

    # Generated into build/, not kernel/. The Makefile globs `kernel` for
    # sources, so a generated file left under it is compiled into every
    # subsequent build — a service build poisoned the general one with
    # "multiple definition of slm_neural_available", permanently, until someone
    # deleted a file they did not know existed.
    absent = tree / f"build-{name}" / "generated" / "absent.c"
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
    # A per-service build directory, for a reason that already bit once.
    # CFLAGS is not a prerequisite of any object rule, so make happily reuses
    # an object compiled with different defines — a service build after a
    # general one silently linked a setup.c.o that still called dhcp_run,
    # because the DHCP-client path had been compiled in before the static
    # define existed. Separate directories mean no object is ever shared
    # between two configurations, and both stay incremental.
    build_dir = f"build-{name}"
    r = subprocess.run(
        ["make", "-C", str(tree), f"CC={cc}", f"BUILD={build_dir}",
         f"CSRC={' '.join(csrc)}",
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

    kernel = tree / build_dir / "kernel.bin"
    if kernel.exists():
        result.kernel_bytes = kernel.stat().st_size
    iso = tree / build_dir / "auton.iso"
    if make_iso and iso.exists():
        result.iso_bytes = iso.stat().st_size

    report = tree / build_dir / "leakage.json"
    verdict = gate_leakage(tree, list(spec.excludes), stub_list, kernel, report)
    result.gates.append(f"leakage: {verdict}")
    result.leakage_report = report
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("service")
    ap.add_argument("--tree", default="kernels/x86_64")
    ap.add_argument("--iso", action="store_true")
    ap.add_argument("--scaffold-only", action="store_true",
                    help="lay the build files into --tree and stop")
    ap.add_argument("--cc")
    ap.add_argument("--output", help="copy the ISO here")
    args = ap.parse_args(argv)

    tree = Path(args.tree)
    if not tree.is_absolute():
        tree = ROOT / tree

    if args.scaffold_only:
        try:
            placed = scaffold(tree)
        except GateFailure as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 1
        print(f"scaffolded {tree}: {len(placed)} file(s)")
        for p in placed:
            print(f"  {p}")
        return 0

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
        shutil.copy2(tree / f"build-{args.service}" / "auton.iso", dest)
        print(f"  -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
