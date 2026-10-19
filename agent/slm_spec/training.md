# Training Specification

> **Rewritten 2026-10-19 (w26 C7) to match what ships.** Authoritative companions: [`SLM/DATA.md`](../../SLM/DATA.md) (the data), [`subsystems/slm.md`](../kernel_spec/subsystems/slm.md) (the kernel side). Earlier drafts of this file described GGUF, BPE and web-scale corpora; none of that is the kernel path.

## Command

```bash
python SLM/scripts/train.py --config SLM/configs/chat_tiny.yaml \
    --dataset <tokenized.jsonl> --output SLM/work/checkpoints --max-steps 10000 --seq-len 64
```

Options: `--batch-size` overrides the config; `--device cpu|mps|cuda`. The loop is AdamW with
linear warmup and cosine decay, checkpointing periodically (`SLM/model/checkpoint.py`).
`chat_tiny` trains on CPU. A smoke run of 200 steps is a **degenerate** checkpoint: the
kernel's guard refuses it, and parity reports a degenerate reference with a declining kernel
as a WEAK pass, counted and reported (w23 G3).

## Evaluate the checkpoint

`SLM/scripts/evaluate.py --checkpoint <ckpt> --dataset <tokenized test set>` reports mean
cross-entropy and perplexity. Perplexity is a sanity check; **it does not decide a ship**. The
chat eval and parity do (see `evaluation.md`).

## Rules

- Train only on kernel-set data that passes `vocab_budget.py` at 0% `<unk>`.
- Report the numbers as the tools printed them. Retry with a change you can name, at most
  three attempts per step; if a step fails, say which and stop.
- Checkpoints, exports and logs live in the run's workspace or `SLM/work/`, never tracked.
