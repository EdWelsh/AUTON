# Model Architecture Specification

> **Rewritten 2026-10-19 (w26 C7) to match what ships.** Authoritative companions: [`SLM/DATA.md`](../../SLM/DATA.md) (the data), [`subsystems/slm.md`](../kernel_spec/subsystems/slm.md) (the kernel side). Earlier drafts of this file described GGUF, BPE and web-scale corpora; none of that is the kernel path.

## Shape

Decoder-only transformer (`SLM/model/transformer.py`): RMSNorm pre-norm blocks, rotary
position embeddings (`rope_theta` 10000), grouped-query attention, SwiGLU feed-forward, tied
input/output embeddings. No dropout in the shipped configs.

## Configs

| Config | Params | Hidden | Layers | Heads (KV) | Vocab | Role |
|---|---|---|---|---|---|---|
| `chat_tiny` | 6M | 256 | 6 | 4 (2) | 1,024 | **ships** |
| `chat_small` | 50M (config) | 512 | 12 | 8 (4) | 1,024 | candidate if `chat_tiny` cannot reach the bar |
| `tiny_10M` | 10M (config; about 14M with its 32,000-row embedding) | 256 | 6 | 4 (2) | 32,000 | rung-3a pipeline proof; 98.8% of its embedding rows are unreachable |
| `small_50M`, `medium_150M`, `large_500M` | | | | | | host-side; not for the kernel |

## Constraints that decide a config

- `vocab_size` is the kernel tokenizer's 1,024. Sizing it to the real vocabulary shrinks the
  exported model about 4x versus a 32,000 default.
- The kernel runs the forward pass in C on the CPU with no libm: the architecture must be one
  `neural_backend.c` implements. A new layer type is a kernel change plus a parity proof.
- Model file at most 128 MiB (`KERNEL_MODEL_BUDGET`); check with `validate_architecture` and
  `estimate_flops` before training.
- Sequence length for training is short (`--seq-len 64` by default); prompts are one line.

Pick the smallest config that passes the eval. The Model Architect starts from `chat_tiny`.
