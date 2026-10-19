# Kernel Integration Specification

> **Rewritten 2026-10-19 (w26 C7) to match what ships.** Authoritative companions: [`SLM/DATA.md`](../../SLM/DATA.md) (the data), [`subsystems/slm.md`](../kernel_spec/subsystems/slm.md) (the kernel side). Earlier drafts of this file described GGUF, BPE and web-scale corpora; none of that is the kernel path.

## Loading

The kernel's neural backend (`kernel/slm/neural/neural_backend.c`, `MODEL_FORMAT_AUTON` in
`subsystems/slm.md`) reads the AUTON flat format from a module placed in the ISO. Tokenization
is word-level in the kernel (`slm_neural_tokenize`: split on spaces, exact case-sensitive
match, whole-vocabulary scan), so Python's `split_words` must match it.

## Placing a model

```bash
# copy to <kernel tree>/models/auton-slm.bin, then
make -C <kernel tree> iso-neural MODEL=models/auton-slm.bin
```

The `integrate_slm` tool does the copy, refuses a file without the AUTON magic (a GGUF, say)
and a tree with no Makefile, and replies with the make line. In an `slm_training` run the tree
is `[slm] kernel_tree`; in a `dual` run it is the workspace.

## Proof

`tests/kernel/neural_parity.sh` boots the ISO and compares the kernel's tokens with
PyTorch's. `scripts/eval.sh` then runs the chat eval in the booted kernel. Budget: the model
must fit 128 MiB of the 256 MiB neural boot budget.
