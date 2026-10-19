# Export Specification

> **Rewritten 2026-10-19 (w26 C7) to match what ships.** Authoritative companions: [`SLM/DATA.md`](../../SLM/DATA.md) (the data), [`subsystems/slm.md`](../kernel_spec/subsystems/slm.md) (the kernel side). Earlier drafts of this file described GGUF, BPE and web-scale corpora; none of that is the kernel path.

## The kernel format

`SLM/scripts/export_auton.py --checkpoint <ckpt> --vocab <vocab.json> --output <path> [--quant fp32|int8]`
writes the **AUTON flat format** (`SLM/tools/auton_format.py`): a header, weights in a fixed
tensor order, the word-level vocabulary, and a JSON manifest (dims, sha256) beside it. The
first four bytes are the format's magic; the kernel and `integrate_slm` both check it.

`validate` in `auton_format.py` re-reads a file and checks its structure before it is used.

## Host-side exporters

`export_gguf.py` (a real GGUF container, checked by `tools/gguf_validator.py`) and
`export_onnx.py` exist for host tools and inspection. **The kernel does not load them**, and
`integrate_slm` refuses a GGUF or ONNX file.

## Integration target

`models/auton-slm.bin` inside the kernel tree; see `integration.md`.
