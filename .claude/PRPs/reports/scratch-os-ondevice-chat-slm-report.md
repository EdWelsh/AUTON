# Implementation Report: On-device chat SLM (Stage 1 Phase B + Stage 2)

## Summary
Executed the `scratch-os-ondevice-chat-slm.plan.md` plan via `/prp-implement`.
Stage 1 Phase A (chat REPL) was already complete from prior work. This run
delivered **Phase B** (SSE enable, boot-module parsing, RAM/module backend
selection) and **Stage 2** (host flat-model pipeline + a freestanding in-kernel
fp32 transformer forward pass), then verified the on-device neural backend boots
and is selected in QEMU.

The OS now boots to `auton>`, and with a model module present (`-m 256M`,
`module2 /boot/auton-slm.bin`) it loads the model in-kernel, prints
`[SLM] Backend: neural`, and runs a real transformer forward pass on the
hardware it is installed on, with automatic fallback to the rule engine.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | XL | XL (as expected; forward-pass debugging dominated) |
| Files created | ~28 | 11 created, 9 modified |
| MVP boundary | Stage 1 (A–B) | Stage 1 complete + Stage 2 neural booting |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| B.1 | SSE enable in boot.S | ✅ | CR0.EM=0/MP=1, CR4.OSFXSR\|OSXMMEXCPT; boot non-fatal |
| B.2 | Parse Multiboot2 modules + RAM | ✅ | hw_summary.modules[]; tag type 3 |
| B.3 | Backend selection in slm_init | ✅ | RAM≥128MB + loadable module → neural, else rule |
| C.1 | Seed dataset | ✅ | SLM/datasets/os_tasks.jsonl |
| C.2 | Flat format + exporter | ✅ | auton_format.py (contract) + export_auton.py + 7 tests |
| D.2 | Freestanding libm | ✅ | kmath.c; host-tested <1e-3 vs libm |
| D.1/4/5 | Loader + forward + tokenizer | ✅ | Consolidated in neural_backend.c (impl latitude) |
| E.1 | Neural→rule fallback wiring | ✅ | slm_process_text tries neural, falls back |
| F.1 | Module boot targets | ✅ | grub-neural.cfg, make iso-neural/run-neural |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static (compile) | ✅ Pass | 26 C + 3 ASM clean (-Wall -Wextra); gcc links -nostdlib |
| Unit / Host tests | ✅ Pass | 79 SLM tests; kmath <1e-3; **neural parity ALL PASS** |
| Build (gcc, Docker) | ✅ Pass | kernel.bin + neural ISO build |
| Integration (QEMU) | ✅ Pass | Boots, loads model, `[SLM] Backend: neural`, IP up, `auton>` |
| Edge cases | ✅ Pass | <128MB or no module → rule engine; SSE probe non-fatal |

### Key validation: forward-pass parity
The in-kernel fp32 forward pass was compiled natively and diffed against the
PyTorch reference on the same checkpoint. Greedy generation matches
**token-for-token** ([2 4 5]→5…, [2 29 30]→30…, [2 4]→4…). Single-step logits
match to 4 decimals. This proves correctness independent of QEMU.

## Files Changed

Created: `kernel/include/{neural,kmath}.h`, `kernel/lib/kmath.c`,
`kernel/slm/neural/neural_backend.c`, `kernel/tests/neural_forward_host.c`,
`kernel/tests/neural_parity.sh`, `grub/grub-neural.cfg`,
`SLM/datasets/os_tasks.jsonl`, `SLM/tools/auton_format.py`,
`SLM/scripts/export_auton.py`, `SLM/tests/test_auton_format.py`.

Modified: `boot.S`, `boot_info.{c,h}`, `slm.c`, `lib/string.c`, `lib/phys.c`,
`arch/x86_64/toolchain.mk`, `Makefile`.

## Deviations from Plan
- **fp32 instead of int8 (Phase D.3 quantized matmul).** A correct, simple fp32
  forward pass was prioritized for the first cut; int8 group-quant matmul
  (acceptance crit #15, ~11 MB vs 56 MB) is a documented extension. The flat
  format reserves a `quant` field for it.
- **Loader/tokenizer/inference consolidated into neural_backend.c** rather than
  separate files — the plan permits impl latitude beyond the hard contracts
  (ABI, marker strings, flat byte layout), all of which are honored.
- **Word-level tokenizer** (matches the existing host `tools/tokenizer.py`)
  instead of BPE — simpler and exact host↔kernel parity.

## Issues Encountered
- **gcc vs clang builtins.** Host clang inlined `__builtin_sqrtf`/`memcpy`;
  Docker gcc emitted libcalls that don't exist freestanding. Fixed: provide
  `memcpy`/`memset` in string.c, add `-fno-math-errno` +
  `-fno-tree-loop-distribute-patterns` to the SSE profile.
- **Stale-binary debugging.** Much forward-pass "nondeterminism" was stale test
  binaries; a strict rebuild discipline + a committed parity harness resolved it.

## Tests Written

| Test | Tests | Coverage |
|---|---|---|
| `SLM/tests/test_auton_format.py` | 7 | flat-format byte layout (host↔kernel contract) |
| `kernel/tests/neural_parity.sh` + harness | 3 prompts | kernel forward pass vs torch |
| kmath host harness | exp/sin/cos/sqrt | <1e-3 vs libm |

## Next Steps
- [ ] int8 quantized matmul (size + speed; acceptance crit #15)
- [ ] 5s wall-clock inference guard + tok/s reporting
- [ ] Acceptance tests `slm_chat_prompt` / `slm_neural_generate` in the harness
- [ ] Train a better model (more data/steps) for coherent output
