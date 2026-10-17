# SLM Training Data

What a model must be trained on to ship inside an AUTON kernel. The authoritative text is
[`SLM/DATA.md`](https://github.com/EdWelsh/AUTON/blob/HEAD/SLM/DATA.md); this page is the tour.

## The question is "does it fit", not "how much"

The kernel tokenizes word-level with a 1,024-word vocabulary. A word outside it is `<unk>` at
training time and in the user's prompt. So a corpus can be large and useless.
[`SLM/tools/vocab_budget.py`](https://github.com/EdWelsh/AUTON/blob/HEAD/SLM/tools/vocab_budget.py)
measures it before a training run is spent:

```bash
python SLM/tools/vocab_budget.py --together SLM/datasets/os_chat.jsonl SLM/datasets/hardware_kernel.jsonl
# FITS  os_chat.jsonl + hardware_kernel.jsonl: 1572 rows, 929 words vs vocab 1024; answer <unk> 0.0%
```

## The datasets

| Dataset | Rows | Ground truth | Fits the kernel? |
|---|---|---|---|
| `os_chat.jsonl` | 944 | what the kernel prints: system queries, roles, the device knowledge base, refusals | **yes** |
| `hardware_kernel.jsonl` | 628 | this machine's CPU, as QEMU's default `qemu64` model reports it (parsed from QEMU's source) | **yes** |
| `hardware_reference.jsonl` | 31,181 | every vendor id, processor, CPUID bit and silicon exception | **no**: 13,401 words, 15% answer `<unk>`. Host-side model |
| domain text (cache only) | 2.8M words | Linux docs, man-pages, QEMU docs, licences recorded | **no**: a 1,024-word vocabulary covers 64–70% of it |
| device and errata tables | 21,662 PCI + 20,537 USB devices | `pci.ids`, `usb.ids`, ingested errata | not trained: packed into the model file and looked up |

## Rules

1. **Every answer is generated from a source of truth.** Each row's `fact` names it; a wrong
   answer is fixed in the generator or its source, never by editing the dataset. Tests fail
   if a committed dataset differs from what its generator produces.
2. **Facts come from lookups.** The model learns phrasing; ids come from tables.
3. **The eval prompts are held out** of every kernel corpus by a shared collision filter.
4. **0% answer `<unk>`** for the kernel set. 929 of 1,024 words are used; 95 remain.

## Getting more

| Kind | How |
|---|---|
| More phrasings for the kernel | extend the generators' question templates (`build_corpus.py`, `build_hardware_corpus.py --profile kernel`), answers unchanged; check the budget |
| More hardware facts | the [Vendor Spec Agents](Vendor-Spec-Agents) grow `agent/hardware/`; regenerate the corpora |
| More domain text | add a source with its licence to `SLM/data/sources.yaml`; `python SLM/tools/fetch_domain_text.py` |

## The open decision: word-level or subword

Domain text can only help a kernel model with a **subword** (BPE) tokenizer, where 165,000
distinct words become a few thousand pieces. That is a kernel change: `slm_neural_tokenize`,
the model file and the parity harness all change. Until the owner decides, the kernel stays
word-level and domain text serves the host-side model and vocabulary planning.
