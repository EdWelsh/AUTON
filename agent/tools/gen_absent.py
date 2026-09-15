"""Generate honest stubs for capabilities a slice leaves out.

A reduced image does not link. `kernel_main` calls `net_bringup`, `roles.c`
registers `http_server_run` by direct function pointer, `slm.c` calls the
neural backend unconditionally, `ipv4.c` dispatches to `tcp_input`. Omitting a
source does not omit its caller — measured at 10 undefined references in
`.claude/PRPs/reports/w2-factory-dependency-audit.md`.

`boot.md`'s Generated Init Sequence section specifies the eventual fix:
generate the init table and the role table from the slice. This is the smaller
step that unblocks a bootable service image now — generate a stub for each
symbol the slice references but does not define, and make the stub **say** the
capability is absent rather than pretending it worked.

That distinction is the whole point. A stub that silently returns success turns
a missing capability into wrong behaviour at runtime; one that reports absence
turns it into a legible message.

    python agent/tools/gen_absent.py --tree kernels/x86_64 --service dhcp \
        --output kernels/x86_64/kernel/boot/absent.c
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_manifest import ManifestError, SourceMap, resolve  # noqa: E402

UNDEF = re.compile(r"^\s*U\s+(\S+)$", re.M)
DEFINED = re.compile(r"^\s*[0-9a-fA-F]*\s*[TtDdBbRr]\s+(\S+)$", re.M)

# Symbols a freestanding image gets from the linker or the compiler, not from a
# subsystem. Stubbing one of these would shadow the real thing.
NEVER_STUB = {
    "memset", "memcpy", "memmove", "strlen", "__stack_chk_fail",
    "_start", "kernel_main",
}

# How to stub a symbol, by shape. A void function can be a no-op; one returning
# a status must return failure, because "absent" is not "succeeded".
SIGNATURES = {
    # symbol: (return type, parameter list, body)
    "tcp_input": ("void", "ipv4_t src, const uint8_t *seg, uint16_t len",
                  "(void)src; (void)seg; (void)len;"),
    "http_server_run": ("void", "void", None),
    "dns_server_run": ("void", "void", None),
    "slm_neural_available": ("int", "void", "return 0;"),
    "slm_neural_load_model": ("int", "const void *m, uint32_t n",
                              "(void)m; (void)n; return -1;"),
    "slm_neural_infer": ("uint32_t",
                         "const uint32_t *in, uint32_t nin, uint32_t *out, "
                         "uint32_t cap, const void *cfg",
                         "(void)in; (void)nin; (void)out; (void)cap; (void)cfg; return 0;"),
    "slm_neural_tokenize": ("uint32_t", "const char *t, uint32_t n, uint32_t *out, uint32_t cap",
                            "(void)t; (void)n; (void)out; (void)cap; return 0;"),
    "slm_neural_detokenize": ("uint32_t", "const uint32_t *ids, uint32_t n, char *buf, uint32_t cap",
                              "(void)ids; (void)n; (void)buf; if (cap) buf[0] = 0; return 0;"),
    "slm_neural_model_info": ("void", "char *buf, uint32_t cap",
                              'const char *s = "none (not in this image)"; '
                              "uint32_t i = 0; for (; s[i] && i + 1 < cap; i++) buf[i] = s[i]; "
                              "if (cap) buf[i] = 0;"),
    "slm_neural_error_text": ("const char *", "void",
                              'return "the neural backend is not in this image";'),
}


class GenerateError(Exception):
    pass


def _symbols(sources: list[Path], tree: Path, cc: str,
             defines: list[str] | None = None) -> tuple[set[str], set[str]]:
    """(defined, undefined) across a set of sources, by compiling each.

    Assembly sources are compiled too. `isr.S` defines `isr_default` and the
    IRQ stubs; scanning only `.c` reported them as missing and the generator
    offered to stub over real interrupt handlers.

    `defines` must match the build's. Compiling `setup.c` without the build's
    `-DNET_STATIC_IP` left the DHCP client path live and `dhcp_run` looking
    absent — a stub generated from a different configuration than the one that
    ships is worse than none.
    """
    import os

    nm = os.environ.get("NM", "x86_64-elf-nm")
    defined: set[str] = set()
    undefined: set[str] = set()
    with tempfile.TemporaryDirectory() as tmp:
        for src in sources:
            obj = Path(tmp) / (src.name + ".o")
            r = subprocess.run(
                [cc, "-c", str(src), "-o", str(obj), f"-I{tree}/kernel/include",
                 "-ffreestanding", "-fno-stack-protector", "-mno-red-zone",
                 "-mno-mmx", "-mno-sse", "-mno-sse2", "-mcmodel=kernel", "-w",
                 *(defines or [])],
                capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                continue
            out = subprocess.run([nm, str(obj)], capture_output=True,
                                 text=True, timeout=60).stdout
            defined |= set(DEFINED.findall(out))
            undefined |= set(UNDEF.findall(out))
    return defined, undefined


def generate(tree: Path, requires: list[str], excludes: list[str],
             extra: list[str] | None = None, cc: str = "x86_64-elf-gcc",
             defines: list[str] | None = None,
             output: Path | None = None,
             entry: str | None = None) -> tuple[str, list[str]]:
    included, _, _ = resolve(requires, excludes, tree)
    included = list(included) + [tree / e for e in (extra or [])]
    sources = [p for p in included if p.suffix in (".c", ".S")]
    # Never scan our own previous output. It lands in kernel/boot/, which the
    # mandatory core matches, so a second run saw its own stubs as definitions,
    # found nothing missing, and emitted an empty file over a working one.
    if output is not None:
        resolved = output.resolve()
        sources = [p for p in sources if p.resolve() != resolved]

    defined, undefined = _symbols(sources, tree, cc, defines)
    missing = sorted(s for s in (undefined - defined) if s not in NEVER_STUB)

    unknown = [s for s in missing if s not in SIGNATURES]
    if unknown:
        raise GenerateError(
            f"no stub signature for: {', '.join(unknown)}.\n"
            f"  Add one to SIGNATURES, or include the capability that defines "
            f"it. Guessing a signature would produce a link that succeeds and a "
            f"call that corrupts the stack."
        )

    lines = [
        "/* GENERATED by agent/tools/gen_absent.py — do not edit.",
        " *",
        " * Stubs for capabilities this image's manifest leaves out. Each one",
        " * reports absence rather than pretending to succeed: a stub that",
        " * silently returns success turns a missing capability into wrong",
        " * behaviour at runtime, where reporting it turns the same thing into a",
        " * legible message.",
        " *",
        " * The eventual fix is a generated init sequence and role table",
        " * (subsystems/boot.md, Generated Init Sequence). This is the smaller",
        " * step that makes a scoped image link.",
        " */",
        '#include <stdint.h>',
        '#include "net.h"',
        '#include "kernel.h"',
        "",
    ]
    for sym in missing:
        ret, params, body = SIGNATURES[sym]
        lines.append(f"{ret} {sym}({params});")
        lines.append(f"{ret} {sym}({params})")
        lines.append("{")
        if body is None:
            lines.append(f'\tkprintf("[ABSENT] {sym}: not in this image\\n");')
        else:
            lines.append(f"\t{body}")
        lines.append("}")
        lines.append("")

    if entry:
        # The service spec's `entry` is the one serve loop this image runs.
        # kernel_main calls a weak service_main(); this is the strong
        # definition that replaces it, so the entry point is data from the
        # spec rather than a hand edit to kernel_main.
        lines += [
            f"void {entry}(void);",
            "",
            "void service_main(void)",
            "{",
            f"\t{entry}();",
            "}",
            "",
        ]
    return "\n".join(lines), missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--service")
    ap.add_argument("--requires", default="")
    ap.add_argument("--excludes", default="")
    ap.add_argument("--extra", default="", help="comma-separated extra sources")
    ap.add_argument("--output", required=True)
    ap.add_argument("--cc", default="x86_64-elf-gcc")
    ap.add_argument("--entry", help="the serve loop; taken from --service if given")
    ap.add_argument("--define", action="append", default=[],
                    help="-D passed to the build; must match, or the stubs are "
                         "generated for a different configuration")
    args = ap.parse_args(argv)

    tree = Path(args.tree)
    if not tree.is_absolute():
        tree = ROOT / tree
    split = lambda s: [t.strip() for t in s.split(",") if t.strip()]  # noqa: E731

    try:
        entry = args.entry
        if args.service:
            from service_spec import load as load_service
            spec = load_service(ROOT / "agent" / "kernel_spec" / "services" / f"{args.service}.md")
            requires, excludes = list(spec.requires), list(spec.excludes)
            entry = entry or spec.entry
        else:
            requires, excludes = split(args.requires), split(args.excludes)
        text, missing = generate(tree, requires, excludes, split(args.extra),
                                 args.cc, [f"-D{d}" for d in args.define],
                                 output=Path(args.output), entry=entry)
    except (GenerateError, ManifestError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    # A sidecar list so the leakage check knows which names are stubs rather
    # than being told by hand — a hand-maintained exemption list drifts, and a
    # drifted one forgives a real leak.
    sidecar = out.with_suffix(".stubs")
    sidecar.write_text("\n".join(missing) + "\n", encoding="utf-8")
    print(f"wrote {out} — {len(missing)} absent capability stub(s)")
    print(f"      {sidecar.name} lists them for tests/kernel/leakage_check.py")
    for m in missing:
        print(f"    {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
