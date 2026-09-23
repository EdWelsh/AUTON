# Pre-registration: the three authorship experiments (F6, V8, H7)

**Written 2026-09-21T17:28:38Z, before any loop run.** The plans require that the subject, the
budget and the goal are fixed before the run, so that a result can't be chosen after seeing it.
Nothing below is edited after a run. Corrections go in the reports.

## Common setup

| | |
|---|---|
| Model | `ollama/gemma4:latest`: gemma4 family, 8.0B parameters, Q4_K_M, Ollama 0.24.0, local |
| Budget | **$0 API** (local). **30 iterations** (`[orchestrator].max_iterations`), **60 min wall clock** (`ORCH_TIMEOUT=3600`) |
| Runs | **one per experiment.** No retries, no best-of-N |
| Base tree | `kernel-reference-v1:kernels/x86_64`, extracted to scratch and git-initialised. The same base F4 and V5 were hand-written on. `kernels/` in the repo stays deleted |
| Spec delivery | spec files copied into the workspace under `spec/`, the layout `package_image.py` ships. **Finding, pre-run:** the agent `read_spec` tool reads only `subsystems/`, `arch/` and `architecture.md`. It cannot read a service spec, a driver record or a mitigation, so without this step no agent could read the document it is asked to implement |
| Guards | w9's workspace guards unchanged. A refusal is recorded, never loosened |
| Referee | the existing gates, run by a person after the loop ends: `build_service.py` for F6, `driver_spec.py` + host tests + injected bugs for V8 |

## F6: service #2, agent-authored

- **Subject: `tftp`**, a read-only TFTP server (RFC 1350 + RFC 1123 §4.2.3.1).
  Spec: `agent/kernel_spec/services/tftp.md`, human-written today, before the run.
- **Why:** same capability set and UDP request/response shape as F4's DHCP, so the comparison
  is fair. It has lock-step block/ACK state, retransmission, an empty final block and error
  replies, none of which DHCP has, so it cannot be copied. SNTP was rejected because the tree
  has no RTC, and the server would have to serve a time it does not know.
- **Capabilities:** all 11 required are mapped in `source_map.yaml` (checked). Excludes `tcp,
  fs, preemptive, ipc`.
- **Goal, verbatim:** see `goal-f6.txt` beside the workspace. It is recorded in the report.
- **Control:** F4's row, as reproduced by `measure_authorship` (see the F6 report for where it
  differs from the recorded figures).

## V8: agent-authored driver

- **Subject: `virtio-console`** (`virtio-mmio:3`, `1af4:1043`). No existing record.
- **Selector, run first, verbatim** after ingesting the VIRTIO 1.2 specification
  (sha256 `42c7d2b9da95b476…`):
  ```
  device:   virtio-mmio:3
  identity: virtio device (MMIO transport)
     reuse       absent     no implemented driver in kernel_spec/drivers/ binds to this device
     port        absent     no driver source is inventoried; …
  -> synthesize  available  Virtual I/O Device (VIRTIO) Specification is inventoried and ingested
                            basis: oasis-virtio/virtio-spec
  ```
  Before ingestion the selector answered `synthesize blocked — inventoried but not ingested`.
  V5 and V6 recorded `synthesize` while the specification was not ingested on this machine.
- **Workspace also carries** `tests/kernel/virtio_reference/` (the shared ring arithmetic, as V6
  had it) and V6's test as the pattern, again as V6 had V5's.
- **Controls:** V5 (virtio-net) and V6 (virtio-blk).

## H7: generated mitigations. Not run, and why

- **Subject would be `f00f-idt-remap`**, the only `implementable` entry. The other,
  `fdiv-reference-check`, is `unmitigatable`.
- **Precondition (plan Task 2) fails:** `requires: [vmm, arch, allocator]`. In the reference tree
  `vmm` is **phantom**: `build_manifest.resolve` reports `phantom_capabilities: [slab, vmm]`,
  because `kernel/mm/vmm.c` does not exist. The tree identity-maps 4 GiB with 2 MiB pages in
  `boot.S` and has no VMM, so no 4 KiB page can be made read-only.
- `mitigation_registry.py --errata intel-pentium-f00f --capabilities arch,allocator` →
  **`declined (image lacks vmm)`**.
- The plan says a mitigation produced into an image that cannot apply it is not an agent
  result, and that `declined` must not be recorded as agent failure. So **no run.** The H7
  report records the blocker: a VMM, which is itself generation work.
