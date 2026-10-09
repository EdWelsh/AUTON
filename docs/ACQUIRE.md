# Things to acquire

Four rows of [`auton-completion.prd.md`](../.claude/PRPs/prds/auton-completion.prd.md) (X1–X4)
wait on something this project does not have: a document behind a download page that refuses
scripts, or a machine. Each row below is **what to get, where a person gets it, the one command
that brings it in, and the gate that proves it landed.** The code on the other side of each is
already built and tested; see [`OPEN-WORK.md`](OPEN-WORK.md).

Nothing here is fetched by a script. Intel's CDN (and Mouser's mirror) return 403 to scripted
downloads, and most vendor specifications are downloadable but **not redistributable**:
documents land in `.cache/vendor/`, which is gitignored, and only the records derived from them
(with page citations) are committed.

## X1 — Driver ↔ erratum join (was V10)

| | |
|---|---|
| **Get** | The Intel **82574 GbE Controller Specification Update** (the 82574L, PCI `8086:10d3`, is what `e1000e` binds, and is the nearest real device/erratum pair) |
| **Where** | intel.com, search "82574 specification update"; download the PDF by hand |
| **Before ingesting** | add its record to `agent/hardware/vendors.yaml` under Intel: `kind: errata`, `key: pci-id+revision` (the w13 plan specifies the shape; a record is added only because a real document needs it) |
| **Bring it in** | `.venv/bin/python agent/tools/vendor_fetch.py --vendor intel --id <new id> --from-file ~/Downloads/<file>.pdf` then `.venv/bin/python agent/tools/vendor_ingest.py --vendor intel --id <new id> --write` |
| **Proves it landed** | `.venv/bin/python agent/tools/errata_join.py --target <a target with 8086:10d3>` names at least one erratum for `e1000e` |
| **If the document does not cover the device** | the gap stands and is recorded; no field is invented |

## X2 — Errata lineage (was H9)

| | |
|---|---|
| **Get** | Six more **Intel Core processor Specification Updates**, one per generation, listed in `agent/hardware/lineage.yaml` (ids `intel-spec-update-6` … `-13`; document numbers there are hints, to be checked against each PDF's own cover) |
| **Where** | intel.com, by document number; by hand |
| **Bring it in** | for each: `.venv/bin/python agent/tools/vendor_fetch.py --vendor intel --id intel-spec-update-<gen> --from-file <pdf>` then `vendor_ingest.py --vendor intel --id intel-spec-update-<gen> --write` |
| **Proves it landed** | `.venv/bin/python agent/tools/lineage.py --config agent/hardware/lineage.yaml --out lineage.json` stops refusing (it refuses below two documents), and `.venv/bin/python agent/tools/retrodict.py --cutoff <gen>` scores a real cutoff against the baseline |

## X3 — Real-silicon conformance (was J / I6)

| | |
|---|---|
| **Get** | An **x86-64 machine** the owner can run a binary on. QEMU implements an idealised CPU and will not reproduce silicon divergence, so an emulator or an Apple Silicon Mac cannot answer this ([`CONFORMANCE-HARDWARE.md`](../agent/hardware/CONFORMANCE-HARDWARE.md)) |
| **Bring it in** | on that machine: `tests/conformance/run_conformance.sh` |
| **Proves it landed** | the native venues print a verdict instead of `SKIP`. Exit 0 pass, 1 **divergence** (a finding: see the disclosure pipeline), 2 harness broken |
| **Step 3 of R10 (F00F)** | needs a family-5 Pentium specifically; any other x86 machine closes X3 but not that step |

> Until a real machine exists, `scripts/host-run.sh` runs the Linux procedures in a container (see
> [`HOST-MATRIX.md`](HOST-MATRIX.md)); that rehearses the steps and proves the toolchain, not silicon.

## X4 — Proxmox, WSL2, bare metal (was 0, A3, B1, B4, B5, C2)

Each host's row in [`HOST-MATRIX.md`](HOST-MATRIX.md) says what it would newly prove. The
procedures are the gated tasks of plans already written; nothing new needs designing.

| Host | Get | Then | Proves it landed |
|---|---|---|---|
| Proxmox | reachability and a **scoped API token, in the environment only, never committed**, plus the name of the physical machine | the gated tasks of [`w15-portability-proxmox`](../.claude/PRPs/plans/completed/w15-portability-proxmox.plan.md) | the Proxmox row in `HOST-MATRIX.md` records a KVM boot with the probed target |
| Windows 11 (WSL2) | a Windows 11 machine with WSL2 | [`w15-portability-wsl2`](../.claude/PRPs/plans/completed/w15-portability-wsl2.plan.md) | the WSL2 row stops saying **No** |
| Bare metal | physical access and a serial console | [`w16-portability-metal`](../.claude/PRPs/plans/completed/w16-portability-metal.plan.md) | the bare-metal row records a boot to the chat prompt |

## Decisions, for completeness

The owner's *decisions* are separate from acquisitions and live in
[`agent/kernel_spec/decisions/`](../agent/kernel_spec/decisions/): the Doom engine licence, the
fleet endpoint, and for application-to-environment the first substrate, syscall scope and
subject trust. Each is written as a question with an empty verdict.
