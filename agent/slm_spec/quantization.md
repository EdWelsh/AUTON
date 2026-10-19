# Quantization Specification

> **Rewritten 2026-10-19 (w26 C7) to match what ships.** Authoritative companions: [`SLM/DATA.md`](../../SLM/DATA.md) (the data), [`subsystems/slm.md`](../kernel_spec/subsystems/slm.md) (the kernel side). Earlier drafts of this file described GGUF, BPE and web-scale corpora; none of that is the kernel path.

## What exists

- `SLM/scripts/quantize.py --checkpoint <ckpt> --bits 8|4 --output <path>`: **symmetric
  per-tensor** quantization of 2D weight matrices (`round(W / scale)` plus one scale per
  tensor). Portable, CPU-only. It is for host-side evaluation of what int8 or int4 costs. It is
  not GPTQ or AWQ, and there is no calibration set.
- `SLM/scripts/export_auton.py --quant int8`: the int8 form the **kernel** loads, in the AUTON
  flat format. The kernel dequantizes at load or per layer as `neural_backend.c` implements.

## Rule

int8 ships only if it holds the fp32 model's eval and parity: run `run_parity` and
`run_chat_eval` on the int8 export and compare. The training agents try int8 after the fp32
model passes (task 5 of 7) and keep fp32 if it does not hold. int4 is not a kernel format.
