# AUTON SLM Specification: Overview

> **Rewritten 2026-10-19 (w26 C7) to match what ships.** Authoritative companions: [`SLM/DATA.md`](../../SLM/DATA.md) (the data), [`subsystems/slm.md`](../kernel_spec/subsystems/slm.md) (the kernel side). Earlier drafts of this file described GGUF, BPE and web-scale corpora; none of that is the kernel path.

## What the SLM is

The kernel's interface is a chat prompt (`auton>`). Deterministic handlers answer what can be
looked up (system queries, roles, PCI ids; `cpu_has()` once `subsystems/cpu.md` exists). A small
decoder-only language model, loaded from the AUTON flat format, phrases the rest. Facts come
from lookups; phrasing comes from the model.

## The pieces

| Piece | Where | Notes |
|---|---|---|
| Model definition | `SLM/model/` | decoder-only transformer: RoPE, grouped-query attention, SwiGLU |
| Configs | `SLM/configs/` | `chat_tiny` (6M, the shipped one), `chat_small` (50M), `tiny_10M` (the rung-3a pipeline proof); `small_50M`, `medium_150M`, `large_500M` are host-side only and do not fit the kernel's vocabulary or boot budget |
| Tokenizer | `SLM/tools/tokenizer.py` | **word-level**, splits on spaces only, 1,024 ids (5 special) |
| Data | `SLM/datasets/`, `SLM/tools/build_*.py` | generated from ground truth; see `SLM/DATA.md` |
| Training | `SLM/scripts/train.py` | AdamW, cosine decay, linear warmup; CPU is enough for `chat_tiny` |
| Quantization | `SLM/scripts/quantize.py` | symmetric per-tensor INT8/INT4 for host evaluation; the kernel's int8 comes from `export_auton.py --quant int8` |
| Export | `SLM/scripts/export_auton.py` | the AUTON flat format (`SLM/tools/auton_format.py`) plus a manifest. GGUF and ONNX exporters exist for host tools only |
| Gates | `tests/kernel/neural_parity.sh`, `scripts/eval.sh` | parity with the kernel's forward pass; the chat eval |

## The bar

A model ships only if (1) **parity**: the kernel generates the same tokens as PyTorch, and (2)
the frozen **65-prompt chat eval** shows at least 70% correct-or-honest and under 10% garbage.
Free-form answers are queued for a person. A model that fails parity does not ship, however
good its scores. The best model so far is 78% correct-or-honest with 22% garbage.

## Budgets

The model is at most 128 MiB of the kernel's 256 MiB neural boot budget; `chat_tiny` is a few
tens of MiB. Context is the config's `max_position_embeddings` (2,048).

## How it is built by agents

The SLM swarm (`scripts/slm_run.py`: data scientist, model architect, two training agents,
integrator) runs seven tasks in order: data, config, train, evaluate, int8 if it holds,
export, integrate. See `wiki/SLM.md` and `wiki/Agents-and-Swarms.md`.
