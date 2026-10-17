# The SLM

The kernel's interface is a chat, and the SLM is the small language model inside it. The
design rule: **facts come from lookups; phrasing comes from the model.**

## How the chat answers

```
auton> line
   │
   ├─ system query? (ip, hostname, memory, devices, uptime, status) → live kernel state
   ├─ server role?  (what can you do, be a web server)               → the roles table
   ├─ PCI id?       (what is pci 8086:100e)                          → the device knowledge base
   └─ otherwise                                                     → the SLM
                                                                       (neural if loaded,
                                                                        else the rule engine)
```

A model that memorises device ids cites ids that are not on the bus: measured at 5 phantom
citations per 50 novel turns against 0 from a lookup. So ids, devices and errata are looked
up (tables packed into the model file), and once a kernel implements `subsystems/cpu.md`,
CPU features come from `cpu_has()`.

## The model the kernel runs

| | |
|---|---|
| Backend | neural when ≥128 MB RAM and a model boot module are present; otherwise the rule engine. The boot log says which (`[SLM] Backend: neural`) |
| Architecture | decoder-only transformer, RMSNorm, SwiGLU, RoPE, grouped-query attention, tied embeddings |
| Shipped size | `chat_tiny`: 6M parameters, hidden 256, 6 layers, 4 heads (2 KV) |
| Tokenizer | **word-level**: split on spaces, exact case-sensitive match, **1,024-word** vocabulary |
| Prompt format | `<bos> question <sep>`; the model generates the answer to `<eos>` |
| File format | the **AUTON flat format** (`SLM/tools/auton_format.py`): header, weights in fixed order, vocabulary, then the device table. Every kernel must load it; GGUF/ONNX are not loaded |
| Precision | fp32, or int8 (`export_auton.py --quant int8`) |

## How a model is proved

1. **Parity.** `tests/kernel/neural_parity.sh` builds the kernel's forward pass on the host
   and checks it generates exactly the tokens PyTorch does on the same checkpoint.
2. **The chat eval.** `scripts/eval.sh` boots the kernel with the model and asks 50 frozen
   prompts. The bar: **≥70% correct-or-honest and <10% garbage**. Deterministic prompts are
   graded automatically; free-form answers are queued for a person, and the verdict cached by
   model fingerprint.

| Model | Correct-or-honest | Garbage |
|---|---|---|
| Rule engine | 66% | 34% |
| `chat_tiny`, 495 rows | **78%** | **22%** |
| `chat_small` (48M) | 74% | 26% |

The bar is half met. An 8× larger model did not help: the gap is data and phrasing coverage,
not capacity. See [SLM Training Data](SLM-Training-Data).

## Training it

`scripts/slm_run.py start <name> --goal "..."` runs the SLM swarm in a testing area: corpora
from ground truth → vocabulary check → train → export → parity → eval → int8 if it holds →
integrate. Or by hand, see [`SLM/README.md`](https://github.com/EdWelsh/AUTON/blob/HEAD/SLM/README.md).
