# Data Preparation Specification

> **Rewritten 2026-10-19 (w26 C7) to match what ships.** Authoritative companions: [`SLM/DATA.md`](../../SLM/DATA.md) (the data), [`subsystems/slm.md`](../kernel_spec/subsystems/slm.md) (the kernel side). Earlier drafts of this file described GGUF, BPE and web-scale corpora; none of that is the kernel path.

## Principle

Everything the kernel model learns fits the kernel's tokenizer. The question for any data is
not how much but **does it fit**: `SLM/tools/vocab_budget.py` answers it before a run is spent.

## Corpora

| Corpus | Source of truth | Builder | Use |
|---|---|---|---|
| `os_chat.jsonl` (944 rows) | the kernel's own device table, roles and commands | `SLM/tools/build_corpus.py` | kernel chat |
| `hardware_kernel.jsonl` (628 rows) | the hardware tables, kernel profile | `SLM/tools/build_hardware_corpus.py --profile kernel` | kernel CPU answers |
| `hardware_reference.jsonl` (30,848 rows) | all vendors, processors, CPUID bits, exceptions | `build_hardware_corpus.py` | a host-side model only: 13,718 words do not fit |
| domain text | fetched documentation | `SLM/tools/fetch_domain_text.py` into `.cache/slm/` (never committed) | vocabulary evidence; useful to a kernel model only with a subword tokenizer |

## Rules

1. Every answer is generated from a source of truth; each row's `fact` names it.
2. The eval prompts are held out of every kernel corpus (one shared collision filter).
3. The kernel set fits 1,024 ids with **0% answer `<unk>`** (929 words used, 90 free).
4. Datasets are generated; change a generator or its source, never a row. A test asserts each
   dataset equals its generator's output.
5. Questions are asked only about features a table lists.

## Tokenizing

`SLM/tools/tokenizer.py` builds the vocabulary from questions and answers, splits on spaces
only (as the kernel does: `split_words`), reserves `<pad> <unk> <bos> <eos> <sep>`, and writes
the tokenized JSONL (`{"ids": [...]}`) that `train.py` reads.

```bash
python SLM/tools/vocab_budget.py --together SLM/datasets/os_chat.jsonl SLM/datasets/hardware_kernel.jsonl
```
