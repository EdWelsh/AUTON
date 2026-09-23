# Plan: From-scratch OS with an on-device SLM/LLM chat interface

## Summary
Extends the foundation plan (`finish-codebase-local-os-on-docker.plan.md` — Docker toolchain, seed x86_64 kernel, build system, rule-engine SLM, validators) toward the real end goal: **a from-scratch OS that boots to an interactive chat prompt and answers using a language model running on the hardware it is installed on.** The kernel reads user lines from the console (16550 UART RX in QEMU; PS/2 on real HW), feeds them to the SLM runtime, and prints generated replies. Ships in two stages: **(1) a chat REPL backed by the deterministic rule engine + knowledge base** (already a working chat), then **(2) a freestanding in-kernel neural backend** (LLaMA-style RMSNorm/RoPE/SwiGLU/GQA forward pass, llama2.c-shaped) that loads a tiny quantized model passed as a boot module and generates free-form responses — with automatic fallback to the rule engine.

## User Story
As someone running AUTON on a machine,
I want to boot it and immediately get a chat prompt where I type natural language and the OS replies using a model running locally on that machine,
So that the OS itself is the conversational interface — no cloud, no separate app — for identifying hardware, configuring the system, and answering questions.

## Problem → Solution
**Current state:** The orchestrator is complete but produces nothing; the foundation plan adds a kernel that boots to `[SLM] Ready` and a rule engine, but there is **no console input path and no chat loop**, and the **neural backend is unimplemented** (`slm_neural_*` exist only as a spec contract). The OS cannot be talked to.
**Desired state:** `docker compose run os` boots to an `auton>` prompt over serial. The user types; the SLM runtime classifies/answers. With a model module present (`-initrd auton-slm.bin`, ≥128 MB RAM) the kernel runs a real on-device transformer forward pass and generates text; without it (or on load failure) it answers via the rule engine + knowledge base. The host SLM pipeline trains `tiny_10M` and exports the flat model the kernel loads.

## Metadata
- **Complexity**: XL (new in-kernel input subsystem + freestanding neural inference engine + freestanding libm + host export format; spans C, asm, Python)
- **Source PRD**: N/A — free-form, refining `finish-codebase-local-os-on-docker.plan.md`
- **Depends on**: foundation plan Phases 0–4 (Docker, seed boot, build system, PMM/SLM-pool, rule engine, PCI) **must be complete first**
- **Estimated Files**: ~28 created, ~10 modified
- **MVP boundary**: **Stage 1 (Phases A–B) delivers "a from-scratch OS with a chat interface."** Stage 2 (Phases C–F) makes that chat a real on-device LLM.

---

## UX Design

### Before (end of foundation plan)
```
$ docker compose run os
  AUTON Kernel booting
  [MM] PMM initialized: 65536 pages free
  [SLM] Rule engine initialized
  [SLM] Ready
  [BOOT] OK
  (kernel halts — no interaction possible)
```

### After (this plan)
```
$ docker compose run os                 # rule-engine chat (Stage 1, no model)
  ...
  [SLM] Rule engine initialized
  [SLM] Backend: rule-engine
  [SLM] Ready
  AUTON. Type a request, or 'help'. On-device assistant.
  auton> what is pci device 8086:100e
  Intel 82540EM Gigabit Ethernet (e1000). Recommended driver: e1000.
  auton> set up networking
  Plan: identify NIC -> load e1000 -> dhcp. Say 'go' to proceed.
  auton> _

$ docker compose run os-neural          # on-device model (Stage 2, -initrd auton-slm.bin)
  ...
  [SLM] Loaded model: auton-slm-tiny (10M, int8, 6L/256d) 11 MB
  [SLM] Backend: neural
  [SLM] Ready
  auton> describe the network card you found
  The detected device is an Intel gigabit ethernet controller; it uses the
  e1000 driver and supports DHCP autoconfiguration.            (3.1 tok/s)
  auton> _
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Console | output only | line-edited input + output REPL | serial RX read; backspace handling |
| Answering | none | rule engine or on-device neural | backend chosen at boot by RAM + model presence |
| Model | none | flat `auton-slm.bin` via `-initrd` boot module | kernel owns loader + tokenizer + forward pass |
| Failure mode | n/a | neural load fail → rule-engine fallback, chat still works | never leaves user without a prompt |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/kernel_spec/subsystems/slm.md` | 74–241, 343–481 | **The exact C contract**: `slm_backend_ops`, `neural_model_t`, `inference_config_t`, and every `slm_neural_*` / `slm_process_text` signature the kernel must implement |
| P0 | `agent/kernel_spec/subsystems/slm.md` | 483–639 | Backend selection (RAM≥128MB→neural), SLM main loop, neural inference pipeline, quantized matmul, edge cases (timeout, fallback) |
| P0 | `agent/slm_spec/architecture.md` | 22–162, 165–188 | LLaMA-style block (RMSNorm→Attn→RoPE→SwiGLU), tiny_10M shape — defines the forward pass math |
| P0 | `SLM/configs/tiny_10M.yaml` | all | Concrete dims: hidden 256, 6 layers, 4 heads, 2 KV heads, inter 1024, vocab 32000, rope_theta 10000 — the model the kernel runs |
| P0 | `.claude/PRPs/plans/finish-codebase-local-os-on-docker.plan.md` | all | Foundation: Docker, seed boot/`boot.S`, Makefile, PMM/SLM-pool, rule engine, PCI, acceptance runner — this plan layers on it |
| P0 | `agent/kernel_spec/subsystems/boot.md` | 1–80 | `boot_info_t` + `boot_module_t modules[16]` — how the model module arrives from `-initrd` |
| P1 | `agent/kernel_spec/subsystems/slm.md` | 642–690 | File layout (`kernel/slm/neural/*`) + acceptance criteria (14: coherent output; 15: INT4/8 within 1% of FP32) |
| P1 | `agent/slm_spec/export.md` | 234–268 | Deployment manifest fields to emit alongside the flat model |
| P1 | `agent/orchestrator/agents/base_agent.py` | 444–481 | Host-side `_train_model/_export_gguf` tool wiring the exporter must satisfy |
| P2 | `SLM/scripts/train.py` + `SLM/tools/tokenizer.py` | all | Stubs the host exporter builds on (foundation Phase 5) |
| P2 | `agent/orchestrator/validation/test_validator.py` | 65–141 | QEMU marker harness the new chat acceptance tests extend |

## External Documentation

| Topic | Source | Key Takeaway |
|---|---|---|
| llama2.c freestanding inference | karpathy/llama2.c (`run.c`) | Single-file C forward pass for exactly this arch (RMSNorm, RoPE, SwiGLU, GQA, KV cache, argmax/top-p). Port: replace `fopen`/`mmap` with module memory, `malloc` with SLM-pool bump alloc, `math.h` with kernel libm. The reference implementation for Stage 2. |
| Flat checkpoint format | llama2.c `export.py` (`legacy`/`v1`) | Header (dim, hidden_dim, n_layers, n_heads, n_kv_heads, vocab_size, seq_len) + raw float/int8 weights in fixed tensor order. Trivial to parse in-kernel — **use this, not GGUF**, for the bootable path. |
| QEMU multiboot modules | QEMU `-kernel`/`-initrd` docs | `-initrd file1,file2` passes files as Multiboot modules; the kernel reads them via the mods list → `boot_info.modules[]`. Lets us ship the model without a filesystem. |
| x86_64 SSE/FPU enable | OSDev "SSE" | Kernel float math needs CR0.EM=0, CR0.MP=1, CR4.OSFXSR=1, CR4.OSXMMEXCPT=1 set in `boot.S` **before** any float op, or `#UD`/`#NM`. Critical for neural inference. |
| 16550 UART receive | OSDev "Serial Ports" | RX = poll LSR bit 0 (Data Ready) then read RBR (`0x3F8`). QEMU `-serial stdio` pipes host stdin → guest UART RX. This is the console input path. |
| Freestanding libm | musl/openlibm single-funcs | Need `expf, sqrtf, sinf, cosf, fabsf` (softmax, RMSNorm, RoPE, SiLU). Port minimal polynomial impls; no full libm. |

```
KEY_INSIGHT: tiny_10M is structurally identical to a llama2.c model — a known, ~970-line C forward pass exists to port.
APPLIES_TO: Phase D (in-kernel neural backend).
GOTCHA: Do NOT parse GGUF in-kernel. Own both ends: host exporter writes a llama2.c-style flat `.bin` (add MODEL_FORMAT_AUTON to model_format_t); kernel loader is then a header read + pointer math. GGUF stays a documented roadmap item.

KEY_INSIGHT: QEMU `-serial stdio` makes the UART the keyboard. The chat REPL reads UART RX, not PS/2.
APPLIES_TO: Phase A (console input).
GOTCHA: Foundation `serial_16550.c` only inits TX/putc. Add RX poll+getc. PS/2 keyboard is a separate, secondary path for real-HW/VGA and is NOT required for the Docker chat MVP.

KEY_INSIGHT: Float in kernel is off by default with freestanding flags.
APPLIES_TO: Phase D.
GOTCHA: Enable SSE in boot.S and compile neural .c WITHOUT -mno-sse/-mgeneral-regs-only. Keep -mno-red-zone. Isolate float to kernel/slm/neural so interrupt handlers stay integer-only.
```

---

## Patterns to Mirror

### NEURAL_BACKEND_CONTRACT (implement these signatures verbatim — they are the kernel's public ABI)
```c
// SOURCE: agent/kernel_spec/subsystems/slm.md:455-481 (slm.h)
int slm_neural_load_model(const void *model_data, uint64_t model_size, model_format_t format);
uint32_t slm_neural_infer(const uint32_t *input_tokens, uint32_t input_len,
                          uint32_t *output_tokens, uint32_t max_output,
                          const inference_config_t *config);
uint32_t slm_neural_tokenize(const char *text, uint32_t text_len, uint32_t *token_ids, uint32_t max_tokens);
uint32_t slm_neural_detokenize(const uint32_t *ids, uint32_t n, char *buf, uint32_t buf_size);
void slm_neural_reset_cache(void);
```

### BACKEND_OPS_DISPATCH (both backends fill this struct; runtime dispatches through it)
```c
// SOURCE: agent/kernel_spec/subsystems/slm.md:92-114
typedef struct slm_backend_ops {
    int  (*init)(uint64_t available_memory);
    int  (*process_intent)(slm_intent_t, slm_sub_command_t, const char *args, uint32_t, slm_intent_result_t *);
    int  (*process_text)(const char *text, uint32_t len, slm_intent_result_t *);
    void (*shutdown)(void);
    const slm_backend_caps_t *(*get_caps)(void);
} slm_backend_ops_t;
```

### NEURAL_MODEL_STATE (the loader populates this from the flat header)
```c
// SOURCE: agent/kernel_spec/subsystems/slm.md:205-232
typedef struct neural_model {
    uint32_t vocab_size, embedding_dim, n_layers, n_heads, n_kv_heads, context_len, hidden_dim;
    tensor_desc_t tensors[MODEL_MAX_TENSORS]; uint32_t tensor_count;
    char vocab[MODEL_MAX_VOCAB][32]; float *token_scores; uint32_t vocab_loaded;
    void *kv_cache; uint32_t kv_cache_pos; float *logits; int model_loaded;
} neural_model_t;
```

### KERNEL_C_STYLE / LOGGING (Linux style + serial markers — same as foundation)
```c
// SOURCE: agent/kernel_spec/architecture.md:268-277 ; markers per acceptance_tests.py
kprintf("[SLM] Loaded model: %s (%uM, int8) %u MB\n", m->name, m->params_m, m->size_mb);
kprintf("[SLM] Backend: neural\n");
```

### HOST_EXPORT_CLI (mirror existing SLM script CLI shape — argparse + yaml)
```python
# SOURCE: SLM/scripts/train.py:8-26 (existing arg style to match)
parser = argparse.ArgumentParser(description="Export SLM to AUTON flat format")
parser.add_argument("--config", required=True)
parser.add_argument("--checkpoint", required=True)
parser.add_argument("--output", default="SLM/models/exports/auton-slm.bin")
parser.add_argument("--quant", choices=["fp32", "int8", "int4"], default="int8")
```

### ACCEPTANCE_MARKER_TEST (extend the existing serial-marker harness)
```python
# SOURCE: agent/kernel_spec/tests/acceptance_tests.py:243-271 (SLM_TESTS shape)
AcceptanceTest(name="slm_chat_prompt", subsystem="slm",
    description="Chat REPL prints prompt and echoes a classified answer",
    expected_serial_patterns=[r"auton>", r"\[SLM\] Backend: (rule-engine|neural)"],
    requires_subsystems=["boot", "mm", "slm"])
```

---

## Files to Change

### Phase A — Console input + chat REPL (Stage 1 MVP: a chat interface)
| File | Action | Justification |
|---|---|---|
| `kernels/x86_64/kernel/drivers/arch/serial_16550.c` | UPDATE | add `serial_rx_ready()` + `serial_getc()` (poll LSR/RBR) |
| `kernels/x86_64/kernel/include/console.h` | CREATE | `console_readline(char*, size)` line editor contract |
| `kernels/x86_64/kernel/sys/console.c` | CREATE | line editor: getc loop, backspace, echo, CR handling |
| `kernels/x86_64/kernel/slm/chat.c` | CREATE | REPL: prompt `auton> `, read line, `slm_process_text`, print `response`; `help`/`quit` builtins |
| `kernels/x86_64/kernel/boot/kernel_main.c` | UPDATE | after `[SLM] Ready`, print backend line + enter `slm_chat_loop()` instead of halting |

### Phase B — Boot module plumbing + backend selection (model arrives, RAM gate)
| File | Action | Justification |
|---|---|---|
| `kernels/x86_64/kernel/arch/x86_64/boot/boot.S` | UPDATE | request multiboot modules; pass mods ptr to C; enable SSE (CR0/CR4) |
| `kernels/x86_64/kernel/boot/boot_info.c` | UPDATE | parse multiboot mods → `boot_info.modules[]`, `hw_summary.total_ram_bytes` |
| `kernels/x86_64/kernel/slm/slm.c` | UPDATE | `slm_init` selects backend by RAM≥128MB & module presence; prints `[SLM] Backend: ...` |

### Phase C — Host: train tiny_10M + export flat model (the on-device weights)
| File | Action | Justification |
|---|---|---|
| `SLM/scripts/train.py` | UPDATE | real tiny LLaMA training loop (foundation Phase 5) producing a checkpoint |
| `SLM/scripts/export_auton.py` | CREATE | export checkpoint → flat `auton-slm.bin` (llama2.c-style header + weights) + manifest |
| `SLM/tools/auton_format.py` | CREATE | shared writer/validator for the flat format (single source of truth) |
| `SLM/datasets/os_tasks.jsonl` | CREATE | tiny seed dataset (HARDWARE_IDENTIFY/DRIVER_SELECT samples from README schema) |

### Phase D — In-kernel neural backend (the on-device LLM)
| File | Action | Justification |
|---|---|---|
| `kernels/x86_64/kernel/slm/neural/loader.c` | CREATE | parse flat header → `neural_model_t`, map tensors into SLM pool |
| `kernels/x86_64/kernel/slm/neural/tokenizer.c` | CREATE | BPE encode/decode from embedded vocab (`slm_neural_tokenize/detokenize`) |
| `kernels/x86_64/kernel/slm/neural/inference.c` | CREATE | forward pass: RMSNorm, QKV, RoPE, GQA attention+KV cache, SwiGLU FFN, logits, sampling |
| `kernels/x86_64/kernel/slm/neural/quantize.c` | CREATE | INT8/INT4 dequant + quantized matmul (per-group scale) |
| `kernels/x86_64/kernel/slm/neural/neural_backend.c` | CREATE | implements `slm_backend_ops` for neural; prompt templating; 5s timeout guard |
| `kernels/x86_64/kernel/lib/kmath.c` | CREATE | freestanding `expf/sqrtf/sinf/cosf/fabsf` (polynomial) |
| `kernels/x86_64/kernel/arch/x86_64/toolchain.mk` | UPDATE | per-file flags: enable SSE for `slm/neural/*`, keep integer-only elsewhere |

### Phase E — Wire chat→backend with fallback; Phase F — acceptance/docs
| File | Action | Justification |
|---|---|---|
| `kernels/x86_64/kernel/slm/slm.c` | UPDATE | `slm_process_text` dispatches to active backend; neural→rule fallback on error/timeout |
| `kernels/x86_64/Makefile` | UPDATE | compile `slm/neural/*`, `lib/kmath.c`; `make model` runs host export; `make run-neural` adds `-initrd` |
| `docker-compose.yml` | UPDATE | add `os-neural` service (`-initrd auton-slm.bin -m 256M`) and `model` build service |
| `agent/kernel_spec/tests/acceptance_tests.py` | UPDATE | add `slm_chat_prompt`, `slm_neural_generate` acceptance tests |
| `scripts/auton-boot.sh` | UPDATE | optional `--neural` flag → build model + boot with `-initrd` |
| `README.md` | UPDATE | document the chat quickstart (rule-engine and on-device-model) |

## NOT Building
- **GGUF/ONNX parsing in-kernel.** Use the flat AUTON format (we own host export + kernel load). GGUF stays roadmap.
- **Training the model inside the OS.** Training/quantization/export run on the host (Python); the kernel only does inference.
- **GPU/SIMD-optimized inference.** Pure scalar C with optional SSE autovectorization. Target is correctness + a few tok/s on `tiny_10M`, not throughput.
- **Multi-turn KV persistence across reboots, full conversation context UI.** Single in-RAM session; `slm_context` multi-step stays minimal (foundation rule-engine level).
- **PS/2 keyboard / VGA TUI as the primary interface.** Serial REPL is the MVP; PS/2+VGA is a documented secondary path, not required for Docker chat.
- **AArch64 / RISC-V neural backend.** x86_64 only is brought to working chat; float-enable and tokenizer are arch-portable but unproven elsewhere here.
- **Larger models (50M+).** `tiny_10M` int8 (~11 MB) is the bootable target; bigger models are config-swappable later.

---

## Step-by-Step Tasks

### Phase A — Console input + chat REPL (Stage 1: a from-scratch OS you can chat with)

#### Task A.1: Serial RX
- **ACTION**: Add receive to the 16550 driver.
- **IMPLEMENT**: `int serial_rx_ready(void)` → `inb(0x3F8+5) & 1`; `char serial_getc(void)` → busy-wait on rx_ready then `inb(0x3F8)`.
- **MIRROR**: existing `serial_putc`/`inb`/`outb` (foundation `serial_16550.c`, `io.h`).
- **GOTCHA**: don't block interrupts; pure polling is fine for a REPL. QEMU maps host stdin → RBR only with `-serial stdio` (already used).
- **VALIDATE**: temporary echo loop prints typed chars back over serial in QEMU.

#### Task A.2: Line editor
- **ACTION**: `console_readline(buf, size)`.
- **IMPLEMENT**: loop `serial_getc`; echo printable chars; handle `\b`/`0x7F` (erase: emit `"\b \b"`); terminate on `\r`/`\n`; NUL-terminate; cap at `size-1`.
- **MIRROR**: `KERNEL_C_STYLE`; `kprintf` for echo.
- **GOTCHA**: serial sends `\r` (CR) on Enter, not `\n` — accept both; strip trailing CR.
- **VALIDATE**: typing `hello`+Enter yields `buf=="hello"`.

#### Task A.3: Chat REPL
- **ACTION**: `slm_chat_loop()`.
- **IMPLEMENT**: print banner + `auton> `; `console_readline`; builtins `help`/`quit`; else `slm_process_text(line, len, &result)` and print `result.response`. Loop forever (or until `quit` → halt).
- **MIRROR**: `slm.md:374-378` (`slm_process_text` contract); `BACKEND_OPS_DISPATCH`.
- **GOTCHA**: `slm_process_text` already routes to the active backend (rule engine in Stage 1) — no neural dependency yet.
- **VALIDATE**: `docker compose run os` → `auton>`; `what is pci 8086:100e` returns the KB device string.

#### Task A.4: Enter REPL from kernel_main
- **ACTION**: Replace the post-`[BOOT] OK` halt with the chat loop.
- **IMPLEMENT**: after `slm_init`, `kprintf("[SLM] Backend: %s\n", slm_backend_name())`, print `[SLM] Ready`, `[BOOT] OK`, then `slm_chat_loop()`.
- **GOTCHA**: keep `[BOOT] OK` BEFORE entering the loop so acceptance boot tests still pass (the harness reads it then sends input).
- **VALIDATE**: boot acceptance still green; REPL reachable.

### Phase B — Model module plumbing + backend selection

#### Task B.1: SSE enable + module passthrough in boot.S
- **ACTION**: Enable SSE and forward the multiboot module list.
- **IMPLEMENT**: in long-mode setup, `mov cr0` clear EM(bit2) set MP(bit1); `mov cr4` set OSFXSR(bit9)+OSXMMEXCPT(bit10). Preserve `ebx` (multiboot info ptr) into the `kernel_main` arg.
- **MIRROR**: foundation `boot.S` long-mode sequence.
- **GOTCHA**: do SSE-enable AFTER paging/long mode, BEFORE any C that touches float. Triple-fault if CR4 set on a CPU without SSE — QEMU default CPU has SSE2, fine.
- **VALIDATE**: a probe `float f=1.5f; kprintf("%d\n",(int)(f*2))` prints `3` without `#UD`.

#### Task B.2: Parse modules + RAM into boot_info
- **ACTION**: Fill `boot_info.modules[]` and `hw_summary.total_ram_bytes`.
- **IMPLEMENT**: read multiboot mods_count/mods_addr → populate `boot_module_t{start,end,cmdline}`; sum mmap available regions for total RAM.
- **MIRROR**: `boot.md:1-80` structs.
- **VALIDATE**: with `-initrd dummy.bin`, `module_count==1` and start/end span the file.

#### Task B.3: Backend selection in slm_init
- **ACTION**: Choose backend by policy.
- **IMPLEMENT**: per `slm.md:487-502` — RAM<128MB → rule; else if a model module exists try `slm_neural_load_model`, on success neural else rule. Print `[SLM] Backend: rule-engine|neural`. Add `slm_backend_name()`.
- **GOTCHA**: Stage 1 has no neural impl yet — guard behind `#ifdef SLM_NEURAL` or a weak stub returning -1 so selection always falls back cleanly until Phase D lands.
- **VALIDATE**: no `-initrd` → `rule-engine`; (after Phase D) `-initrd auton-slm.bin -m 256M` → `neural`.

### Phase C — Host model pipeline (produces auton-slm.bin)

#### Task C.1: Tiny dataset + training
- **ACTION**: Seed dataset; implement training for `tiny_10M`.
- **IMPLEMENT**: `os_tasks.jsonl` with the README schema (`text`/`intent`/`context`/`next_action`); `train.py` builds a LLaMA-style model from `tiny_10M.yaml` (RMSNorm/RoPE/SwiGLU/GQA), trains a few hundred steps, checkpoints.
- **MIRROR**: `HOST_EXPORT_CLI`; existing `SLM/tests/test_train.py` contract.
- **GOTCHA**: keep it tiny/CPU — quality is irrelevant for the pipeline proof; the kernel just needs a loadable, coherent-enough model. Set seeds for determinism.
- **VALIDATE**: `python SLM/scripts/train.py --config SLM/configs/tiny_10M.yaml --dataset SLM/datasets/os_tasks.jsonl --max-steps 50` → checkpoint written; `pytest SLM/tests/test_train.py` green.

#### Task C.2: Flat exporter + format module
- **ACTION**: Define the flat format and export to it.
- **IMPLEMENT**: `auton_format.py` writes header `{magic 'AUTN', version, dim, hidden_dim, n_layers, n_heads, n_kv_heads, vocab_size, seq_len, quant}` then tensors in fixed order (token_emb, per-layer: rms_attn, wq, wk, wv, wo, rms_ffn, w1(gate), w2(down), w3(up), final rms, optional separate lm_head), then vocab strings + scores. `export_auton.py` reads checkpoint, optional int8 per-group quant, writes `.bin` + JSON manifest (`export.md:234-268` fields + sha256).
- **MIRROR**: llama2.c export tensor order (External Docs); `HOST_EXPORT_CLI`.
- **GOTCHA**: **fix the tensor order and dtype layout now** — the kernel loader (Task D.1) must match byte-for-byte. Document the layout in a header comment shared conceptually with `loader.c`.
- **VALIDATE**: `export_auton.py ... --quant int8` → `auton-slm.bin` (~11 MB); `auton_format.py --validate auton-slm.bin` re-reads header and confirms tensor sizes sum to file size.

### Phase D — In-kernel neural backend (the on-device LLM)

#### Task D.1: Loader
- **ACTION**: `slm_neural_load_model(data, size, MODEL_FORMAT_AUTON)`.
- **IMPLEMENT**: validate magic/version; fill `neural_model_t` dims; set each `tensor_desc_t.data` to `model_data + offset` (no copy — run in place from module memory); allocate `logits[vocab]` and `kv_cache` (n_layers × seq × n_kv_heads × head_dim × 2) from SLM pool; load vocab.
- **MIRROR**: `NEURAL_MODEL_STATE`; `slm.md:455-460`. Add `MODEL_FORMAT_AUTON` to `model_format_t`.
- **GOTCHA**: SLM-pool sizing (foundation) must cover logits + KV cache + activation scratch (~a few MB for tiny). Bound `MODEL_MAX_VOCAB`=32000 matches config.
- **VALIDATE**: loads exported `.bin`; prints `[SLM] Loaded model: auton-slm-tiny (10M, int8) 11 MB`; dims equal the YAML.

#### Task D.2: Freestanding libm
- **ACTION**: `kmath.c` with `expf/sqrtf/sinf/cosf/fabsf`.
- **IMPLEMENT**: range-reduced polynomial approximations (sufficient precision for softmax/RoPE/RMSNorm/SiLU).
- **GOTCHA**: no `errno`, no denormals handling needed; compile with SSE.
- **VALIDATE**: host unit harness (compile `kmath.c` natively) asserts max abs error <1e-3 vs libm on [-10,10].

#### Task D.3: Quantized matmul
- **ACTION**: `quantize.c` — INT8/INT4 dequant + matvec.
- **IMPLEMENT**: per `slm.md:592-606`: INT8 `val=q*scale` per-group; INT4 unpack 2/byte, zero-point −8; accumulate in float32. `qmatmul(out, x, W_q, scales, n, d)`.
- **GOTCHA**: group size must match the exporter (Task C.2) — pick 64, document on both ends.
- **VALIDATE**: host harness: quantized matmul within 1% of FP32 reference (acceptance crit #15).

#### Task D.4: Forward pass
- **ACTION**: `inference.c` — one decoder step + generation loop.
- **IMPLEMENT**: embed token; per layer: RMSNorm→Wq/Wk/Wv (qmatmul)→RoPE(q,k,pos)→write KV cache→GQA attention (scores/√d, softmax, ×V)→Wo→residual; RMSNorm→SwiGLU(SiLU(x·W1)*(x·W3))·W2→residual. Final RMSNorm→lm_head→`logits`. `slm_neural_infer` loops: sample (greedy if temp=0 else top-p), append, until `max_tokens`/EOS, with a 5 s wall-clock guard.
- **MIRROR**: `architecture.md:22-162` block; `slm.md:570-590`; llama2.c `forward()`.
- **GOTCHA**: GQA — map each query head to `kv_head = q_head / (n_heads/n_kv_heads)`. RoPE θ=10000 from config. KV cache indexed by absolute position; call `slm_neural_reset_cache` per new prompt.
- **VALIDATE**: greedy-decode a fixed prompt in QEMU prints deterministic, non-garbage tokens; `[SLM] Backend: neural`.

#### Task D.5: Tokenizer
- **ACTION**: `tokenizer.c` — `slm_neural_tokenize/detokenize`.
- **IMPLEMENT**: BPE merge using embedded `vocab[]`+`token_scores` (llama2.c byte-fallback tokenizer); detokenize = concat token strings, handle the leading-space sentinel.
- **GOTCHA**: must match the host tokenizer (Task C.1) vocab exactly — exporter writes the same vocab the kernel reads.
- **VALIDATE**: round-trip `tokenize→detokenize` of `"hello"` reproduces input; ids match host tokenizer on 5 sample strings.

### Phase E — Chat ↔ backend wiring + fallback

#### Task E.1: Neural backend ops + fallback
- **ACTION**: `neural_backend.c` implements `slm_backend_ops`; `slm.c` falls back on failure.
- **IMPLEMENT**: `process_text`: build prompt (`slm.md:574`), `tokenize→infer→detokenize`, fill `slm_intent_result_t.response`. In `slm_process_text`, if active=neural and infer returns error/timeout → retry via rule engine (`slm.md:639`).
- **MIRROR**: `BACKEND_OPS_DISPATCH`; rule-engine fallback edge cases.
- **VALIDATE**: corrupt the model module → boot still reaches `auton>` on rule engine; valid module → neural answers; killing inference (simulated timeout) yields a rule-engine answer, never a hang.

### Phase F — Acceptance, run targets, docs

#### Task F.1: Acceptance tests + compose targets
- **ACTION**: Add chat acceptance tests and `os-neural`/`model` services.
- **IMPLEMENT**: `slm_chat_prompt` (rule path: feed `what is pci 8086:100e\n` to QEMU stdin, expect KB answer + `auton>`); `slm_neural_generate` (neural path: expect `[SLM] Backend: neural` and ≥1 generated line). `docker-compose.yml`: `model` (runs host export) and `os-neural` (`-initrd ... -m 256M`). Extend `auton-boot.sh --neural`.
- **MIRROR**: `ACCEPTANCE_MARKER_TEST`; foundation acceptance runner.
- **GOTCHA**: the acceptance runner must write to QEMU stdin (pipe) to drive the REPL — extend `TestValidator` to accept an optional `stdin_script`.
- **VALIDATE**: `docker compose run acceptance` passes `slm_chat_prompt`; `docker compose run os-neural` then acceptance passes `slm_neural_generate`.

#### Task F.2: Docs
- **ACTION**: README chat quickstart (rule + on-device model), note flat-format/roadmap-GGUF, RAM requirement.
- **VALIDATE**: documented commands run as written in the image.

---

## Testing Strategy

### Unit / Host Tests
| Test | Input | Expected | Edge Case? |
|---|---|---|---|
| `kmath` host harness | x∈[-10,10] | err <1e-3 vs libm | extreme x |
| `quantize` host harness | random W | INT8/4 within 1% of FP32 | all-zero group |
| `auton_format` round-trip | tiny checkpoint | header+tensors re-read equal | truncated file |
| host tokenizer parity | 5 strings | kernel ids == host ids | unicode/space |
| `SLM/tests/*` (exist) | tiny cfg | train/export pass | empty dataset |

### Kernel/QEMU Acceptance
| Test | Driver | Expected |
|---|---|---|
| `slm_chat_prompt` | stdin `what is pci 8086:100e` | KB device string + `auton>` |
| `slm_neural_generate` | `-initrd auton-slm.bin -m 256M` + prompt | `[SLM] Backend: neural` + generated line |
| fallback | corrupted module | reaches `auton>` on rule-engine |

### Edge Cases Checklist
- [ ] No model module → rule-engine chat works
- [ ] RAM <128 MB (`-m 64M`) → rule-engine selected regardless of module
- [ ] Corrupt/short model → load fails → fallback, no triple-fault
- [ ] Inference exceeds 5 s → aborted → rule-engine answer
- [ ] Empty line at prompt → re-prompt, no crash
- [ ] Backspace past start of line → no buffer underrun
- [ ] SSE not enabled (regression) → caught by Task B.1 float probe

---

## Validation Commands

### Static Analysis
```bash
cd agent && ruff check . && cd tools && cargo clippy -- -D warnings
```
EXPECT: clean (host Python/Rust unchanged-quality)

### Host SLM tests
```bash
docker compose run test            # includes pytest SLM/tests + kmath/quantize host harnesses
```
EXPECT: green

### Build model
```bash
docker compose run model           # train tiny + export auton-slm.bin + manifest
```
EXPECT: `SLM/models/exports/auton-slm.bin` (~11 MB) + manifest JSON

### Chat — rule engine
```bash
docker compose run os
```
EXPECT: `auton>` prompt; KB answers to hardware queries

### Chat — on-device model
```bash
docker compose run os-neural
```
EXPECT: `[SLM] Loaded model ...` / `[SLM] Backend: neural`; generated replies at the prompt

### Acceptance
```bash
docker compose run acceptance
```
EXPECT: boot+drivers+slm+`slm_chat_prompt`(+`slm_neural_generate` when model present) ALL PASS

### Manual Validation
- [ ] Boot, type `help` → builtins listed
- [ ] `what is pci 8086:100e` → e1000 identification (KB)
- [ ] With model: `describe the network card` → coherent generated sentence
- [ ] Remove `-initrd` → still chats (rule engine), no error
- [ ] `-m 64M` with model → `[SLM] Backend: rule-engine`

---

## Acceptance Criteria
- [ ] OS boots to an interactive `auton>` chat prompt over serial (**Stage 1 MVP**)
- [ ] Rule-engine backend answers hardware/driver/system queries from the knowledge base
- [ ] Host pipeline trains `tiny_10M` and exports a loadable flat `auton-slm.bin` + manifest
- [ ] Kernel loads the model from a `-initrd` boot module and prints model/backend lines
- [ ] In-kernel forward pass generates coherent free-form text on device (acceptance crit #14)
- [ ] INT8/INT4 quantized matmul within 1% of FP32 (acceptance crit #15)
- [ ] Neural→rule-engine fallback on load failure/timeout; chat never hangs (crit #16)
- [ ] `slm_chat_prompt` (+`slm_neural_generate`) acceptance tests pass under Docker

## Completion Checklist
- [ ] Implements the `slm.h` neural ABI signatures exactly (no contract drift)
- [ ] Float math isolated to `kernel/slm/neural/*`; interrupt paths stay integer-only
- [ ] Flat format byte layout identical between `export_auton.py` and `loader.c`
- [ ] Kernel tokenizer parity with host tokenizer
- [ ] Markers (`auton>`, `[SLM] Backend: ...`, `[SLM] Loaded model ...`) match acceptance tests
- [ ] No model weights committed to git (build artifact); manifest + checksum only
- [ ] Docs updated; both chat paths verified in-image
- [ ] Stage 1 (A–B) shippable without Stage 2

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Freestanding float (SSE/libm) bugs → garbage or faults | High | Neural path unusable | Enable SSE early (B.1) + float probe; host-test `kmath`/`quantize` before kernel use; isolate float to `slm/neural` |
| Flat-format layout mismatch host↔kernel | High | Silent garbage output | One shared documented layout; `auton_format --validate`; round-trip + tokenizer-parity tests |
| In-kernel forward pass too slow (<1 tok/s) | Med | Poor UX | tiny_10M int8; greedy decode; cap `max_tokens`; report tok/s; acceptable for proof |
| SLM-pool too small for weights+KV+scratch | Med | Load/infer OOM | size pool from manifest at load; fail → rule-engine fallback |
| QEMU stdin driving REPL flaky in CI | Med | Acceptance flakiness | deterministic stdin script + generous timeout; assert markers not timing |
| Model quality poor (tiny, few steps) | Low | Replies incoherent | acceptance only requires *coherent-ish*/non-garbage; quality is roadmap, pipeline is the deliverable |
| Scope creep into GGUF/PS2/VGA | Med | Slips MVP | explicitly OUT; flat format + serial REPL only |

## Notes
- **This is the product's reason for being:** the OS *is* the chat interface, and the model runs on the installed hardware. The plan deliberately ships a **deterministic rule-engine chat first (Stage 1)** so "a from-scratch OS you can talk to" exists before the harder neural work, then drops in the **on-device transformer (Stage 2)** behind the same `slm_process_text` entry point with guaranteed fallback.
- **Why flat format over GGUF:** we control host export and kernel load, so a llama2.c-style flat `.bin` removes an entire class of in-kernel parser risk and matches the known-good reference forward pass. The `slm.md` GGUF contract is preserved as `model_format_t` (add `MODEL_FORMAT_AUTON`); GGUF/ONNX loaders remain a roadmap extension.
- **Hard contracts** (non-negotiable): the `slm.h` neural signatures (`slm.md:455-481`), the marker strings the acceptance harness greps, and the flat-format byte layout shared between `export_auton.py` and `loader.c`. Everything else is implementation latitude.
- **Sequencing:** complete the foundation plan's Phases 0–4 first (this plan assumes a booting kernel with PMM, an SLM pool, a rule engine, and PCI). Then A→B (chat MVP) → C→D→E (on-device LLM) → F (verify).
```
