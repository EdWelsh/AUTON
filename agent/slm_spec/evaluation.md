# Evaluation Specification

> **Rewritten 2026-10-19 (w26 C7) to match what ships.** Authoritative companions: [`SLM/DATA.md`](../../SLM/DATA.md) (the data), [`subsystems/slm.md`](../kernel_spec/subsystems/slm.md) (the kernel side). Earlier drafts of this file described GGUF, BPE and web-scale corpora; none of that is the kernel path.

## Three gates, in this order

1. **Perplexity** (`SLM/scripts/evaluate.py`): a sanity check on held-out tokenized text.
2. **Parity** (`tests/kernel/neural_parity.sh`, the `run_parity` tool): the kernel's C
   forward pass must generate the same tokens as PyTorch for fixed prompts. A model that fails
   parity does not ship. A degenerate reference with a declining kernel is a WEAK pass.
3. **Chat eval** (`scripts/eval.sh`, the `run_chat_eval` tool): the frozen **65-prompt** eval
   held out of every kernel corpus, run in the booted kernel. The bar is **at least 70%
   correct-or-honest and under 10% garbage**. Free-form answers are queued for a person; never
   claim a pass the auto-graded part alone does not show.

## Baselines

Baselines recorded on the earlier 50-prompt set are labelled as such. The best kernel model:
78% correct-or-honest, 22% garbage (`.claude/PRPs/reports/e2e-rung3b-training-attempts.md`).
The next lever is more grounded phrasings of the intents the eval fails, within the 90 free
vocabulary words (`SLM/DATA.md`).

## Phantom citations

A model that memorises ids cites ids that are not on the bus (measured: 5 per 50 novel turns).
This is why facts are looked up and the model only phrases. Any eval change must keep a
phantom-citation count.
