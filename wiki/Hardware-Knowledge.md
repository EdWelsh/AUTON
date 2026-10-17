# Hardware Knowledge

What AUTON knows about the machines a kernel will run on, and where each fact came from. All
of it is in [`agent/hardware/`](https://github.com/EdWelsh/AUTON/tree/HEAD/agent/hardware).

## The tables

| Table | What | Built from |
|---|---|---|
| `vendors.yaml` (inventory) | per vendor: which documents exist, where, licence, form, the key errata are indexed by | by hand and by the Vendor Scout |
| `registry/vendors.json` | **every vendor that has held a PCI, USB, x86 CPUID or Arm MIDR identity: 5,077** | `pci.ids`, `usb.ids`, Linux's identity tables (`vendor_registry.py`) |
| `isa/<arch>.json` | **284 processor models** (x86, AArch64, RISC-V, POWER, IBM Z), feature lists closed under implication; every x86 feature's CPUID leaf, register and bit | LLVM's target definitions, Linux's `cpufeatures.h` (`isa_tables.py`) |
| `isa/qemu.json` | QEMU's 46 built-in x86 CPU models, including `qemu64`, the CPU every gate boots on | QEMU's `target/i386/cpu.c` (`qemu_cpu.py`) |
| `isa/exceptions.yaml` | where silicon disagrees with documents | by hand and by the Spec Reader; every row cited |
| errata, lineage, mitigations | Intel specification updates per generation, erratum classes, OS mitigations | ingested documents |

```bash
python agent/tools/vendor_registry.py --lookup 1d17         # Zhaoxin; no documents yet
python agent/tools/isa_tables.py --has haswell fma4         # absent: never-shipped
python agent/tools/isa_tables.py --has alderlake avx512f    # check at runtime: fused-off
python agent/tools/isa_tables.py --arch systemz --has z16 vector
python agent/tools/isa_tables.py --cpuid avx512f            # leaf 0x7 subleaf 0, EBX bit 16
```

## A document never proves an instruction is present

| Case | Kind |
|---|---|
| Intel specified four-operand FMA (FMA4), then shipped FMA3; no Intel part has FMA4 | never shipped |
| AMD shipped FMA4, XOP, TBM and 3DNow! in older families; Zen does not report them | removed |
| First-generation Zen reportedly executes FMA4 with the CPUID bit clear | undocumented (treated as absent) |
| Alder Lake P-cores contain AVX-512; microcode, then fuses in later production, disabled it | fused off |
| TSX shipped in Haswell and Skylake-era parts, then microcode disabled it (HSW136, TAA) | microcode disabled |

The tables say what *may* be there. The running CPU says what *is*. So the kernel's `cpu`
spec allows only the architecture baseline outside `cpu_has()`, and a vendor string never
implies a feature. All 9 exception rows are written from cited public sources and marked
`verified: false` until the Spec Reader checks them against the vendor's own document.

## Licences

**Ingest and derive; never vendor the source.** Most specifications are downloadable and not
redistributable. Fetched documents live in `.cache/vendor/` (gitignored), each with a
provenance record whose sha256 is its identity; `vendor_fetch.py` refuses to fetch a
non-redistributable document into a tracked path. What is committed is what is derived: a
record citing document, revision and page. Intel's CDN refuses scripts, so Intel documents
come in with `--from-file`.

## Coverage

Inventoried is not ingested. 36 vendors and 74 documents are inventoried; the device
registries, LLVM's and Linux's tables, QEMU's definitions and one Intel specification update
(Alder Lake, 94 errata) are derived. 5,060 registry vendors have no inventory record: the
[Vendor Spec Agents](Vendor-Spec-Agents)' queue.
