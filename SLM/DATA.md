# The data an in-kernel SLM needs

What a model must be trained on to ship inside an AUTON kernel, decided by what the kernel
actually runs, with every number measured (2026-10-17).

## The constraint: the kernel's tokenizer

`kernel/slm/neural/neural_backend.c: slm_neural_tokenize` (kernel-base-v5) is **word-level**:
it splits on spaces, matches each word exactly and case-sensitively, and scans the whole
vocabulary per word. The shipped configs (`chat_tiny`, 6M parameters; `chat_small`, 48M) have
a **1,024-word vocabulary**. Anything outside it is `<unk>`, in training and in the user's
prompt. The model file is the AUTON flat format (`tools/auton_format.py`), not GGUF.

So the question for any data is not "how much" but "does it fit". `tools/vocab_budget.py`
answers it before a training run is spent:

```bash
python SLM/tools/vocab_budget.py --together SLM/datasets/os_chat.jsonl SLM/datasets/hardware_kernel.jsonl
```

## Three kinds of data, three jobs

| Kind | What | Where | Fits the kernel model? |
|---|---|---|---|
| **1. Supervised pairs** | question → answer, every answer generated from ground truth | `datasets/os_chat.jsonl` (944 rows), `datasets/hardware_kernel.jsonl` (628 rows) | **Yes.** 929 distinct words together, 0% `<unk>` |
| **2. Lookup tables** | facts the kernel looks up instead of the model memorising them | device table and errata table, packed into the model file (`tools/build_device_table.py`, `tools/build_errata_table.py`) | Not trained: looked up. 21,662 PCI and 20,537 USB device records |
| **3. Domain text** | documentation prose for language modelling | `.cache/slm/domain/` (fetched by `tools/fetch_domain_text.py`, never committed; statistics in `datasets/domain_text.stats.json`) | **No.** 2.8M words, 165,228 distinct in the Linux docs alone; a 1,024-word vocabulary covers 64–70% of tokens |

And one corpus for a different model:

| | | | |
|---|---|---|---|
| **Reference pairs** | every vendor id, processor, CPUID bit and silicon exception | `datasets/hardware_reference.jsonl` (30,848 rows) | **No.** 13,718 distinct words; 15% of answer tokens, exactly the ids and names that carry the facts, would be `<unk>`. Mixing it into the kernel set pushes the chat corpus to 15% `<unk>` too. For a host-side model |

## Rules

1. **Facts come from lookups, phrasing from the model.** The chat routes deterministic
   handlers first (system queries, roles, PCI ids, and `cpu_has()` once `subsystems/cpu.md`
   is implemented); the model is the fallback. A model that memorises ids cites ids that are
   not on the bus: measured at 5 phantom citations per 50 novel turns.
2. **Every answer is generated from a source of truth**, and each row's `fact` names it.
3. **The eval prompts are held out** of every kernel corpus (`build_corpus.py` and
   `build_hardware_corpus.py --profile kernel` share the collision filter).
4. **The kernel set must fit the vocabulary with 0% answer `<unk>`.** Today 929 of the 1,019
   word slots are used (5 of the 1,024 ids are the special tokens `<pad> <unk> <bos> <eos>
   <sep>`, which `vocab_budget.py` and `tokenizer.py` both reserve); 90 remain. Growth beyond that is a decision (below), not an accident.

## What a full kernel SLM still needs

| Gap | Why it matters | Next step |
|---|---|---|
| Garbage rate | The chat eval's best model is 78% correct-or-honest, **22% garbage**; the bar is under 10% (`.claude/PRPs/reports/e2e-rung3b-training-attempts.md`) | More grounded phrasings of the intents the eval fails, within the vocabulary budget |
| Vocabulary headroom | 90 words left (1,024 − 5 special tokens − 929 in use) | Choose: keep word-level and spend words deliberately, or move the kernel to a subword tokenizer (below) |
| CPU answers | `hardware_kernel.jsonl` assumes a kernel that implements `subsystems/cpu.md` | Generate and gate the `cpu` subsystem; then the deterministic handler and the model agree |
| e2e spine | `scripts/e2e.sh` still trains on the 12-row `os_tasks.jsonl` with `tiny_10M` (rung 3a, pipeline proof only) | Point it at the kernel set with `chat_tiny` once parity passes on it |

### The decision: word-level or subword

Domain text (kind 3) can only help a kernel model with a **subword** tokenizer (BPE), where
165,000 distinct words become a few thousand pieces. That is a kernel change, not a data
change: `slm_neural_tokenize` must implement the merge, the model file must carry merges,
and `neural_parity.sh` must prove the kernel tokenizes exactly as Python does. Until the
owner decides, the kernel stays word-level and kind 3 is fetched for the host-side model and
for vocabulary evidence only.

## Regenerating

```bash
python agent/tools/qemu_cpu.py --build                       # agent/hardware/isa/qemu.json
python SLM/tools/build_corpus.py --output SLM/datasets/os_chat.jsonl
python SLM/tools/build_hardware_corpus.py --profile kernel
python SLM/tools/build_hardware_corpus.py                    # reference (host-side)
python SLM/tools/fetch_domain_text.py                        # domain text into .cache/slm/
```
