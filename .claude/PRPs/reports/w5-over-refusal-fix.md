# Report: Over-Refusal Fix — 23.1% → 12.3% garbage

**Addresses**: `auton-real-world-deployments-and-silicon.prd.md` A3 (22% garbage rate)

## The measurement

| | correct | honest-roadmap | garbage | |
|---|---|---|---|---|
| Before | 29 | 21 | **15** | 76.9% good / **23.1% garbage** |
| After | 39 | 18 | **8** | 87.7% good / **12.3% garbage** |

Same 65-prompt eval, same closed-loop harness, same grading criteria, all 65 delivered. The
bar (<10% garbage) still **fails**, but the rate is nearly halved.

## What actually fixed it — and what did not

The work split cleanly into two attempts, and the difference between them is the result.

**Attempt 1: grow the corpus.** 561 → 944 records covering shell idioms, role listing,
software-by-product-name, and network configuration. Result: **23.1% → 21.5%.**

Almost nothing — and the composition moved against itself:

| class | garbage before | after corpus growth |
|---|---|---|
| ses- (shell idioms) | 8/15 | 3 — improved |
| drv- (drivers) | 1/7 | **4 — worse** |
| tsh- (troubleshoot) | 3/7 | **6 — worse** |

The model began answering `recommend a driver for 8086:100e` with **`e1000e`** — a device the
table knows as `e1000` — and refused troubleshooting questions it had previously answered
correctly. At 6M parameters, 383 extra records bought one class by spending another.

That is a second independent line of evidence for the capacity ceiling the scoped-corpus report
named as its alternative hypothesis.

**Attempt 2: move retrieval ahead of generation.** Result: **21.5% → 12.3%.**

The kernel tried the model first and fell through to the rule engine only when the model
produced *nothing*. But the model's generic refusal is a non-empty answer, so the deterministic
path was unreachable for every question the model chose to decline. The rule engine had the
answers and was never asked.

Three deterministic paths now run **before** the model:

1. **Shell idioms** — `lsmod`, `meminfo`, `netstat`, `uname`, `df`, `ps`, `dmesg`, `uptime`,
   `ip a`, `ip route`, answered from the same tables the chat already uses.
2. **PCI-id questions** — a `vvvv:dddd` in the text means the knowledge base can answer exactly.
3. **Network state** — `why is the network down` is answered from `net_is_up()` and the address,
   not guessed.

## Why the model could never have learned the idioms

This is the part worth keeping.

The eval holds its prompts out of the training corpus, correctly — otherwise it measures
memorisation. The tokenizer builds its vocabulary **from that corpus**. Therefore every
eval-only word arrives as `<unk>`, and a word-level model cannot act on a token it has no
representation for.

Measured: **22 of 65 prompts contain a word the model cannot represent**, and they fail at
**36% against 16%** for in-vocabulary prompts — more than double. `lsmod`, `meminfo`, `netstat`,
`hw`, `info` are simply not in the 759-token vocabulary.

No amount of corpus work fixes this, because the fix is forbidden by the contamination guard.
Substring matching has no vocabulary and is immune to the problem entirely — which is why the
deterministic path worked where 383 records did not.

## Two implementation bugs, both mine, both found by measuring

**The idiom path ran after the model**, contradicting the spec I had just written
(*"Deterministic, Before the Model"*). The generic refusal won every race it was allowed to
enter. Moving it fixed 6 prompts at a stroke.

**Moving it ahead made `is_ip_query` unreachable**, so `ip a` regressed from the correct address
to a DHCP-server roadmap. Adding the address idioms to the deterministic path recovered it.

Both are the same error: a dispatch order that lets a guess pre-empt a fact.

## What remains: 8 prompts

All are model mis-routes with a deterministic answer available, and each would yield to the same
treatment:

| prompt | answered with | should be |
|---|---|---|
| `which driver should I use for my nic` | device list | the bound driver |
| `do you have a driver for the intel gigabit card` | containers roadmap | the e1000 entry |
| `did you get an address from dhcp` | DHCP **server** roadmap | the lease state |
| `check whether dhcp succeeded` | DHCP **server** roadmap | the lease state |
| `my web server is not responding` | starts the server | what to check |
| `the nic is not working, help` | device list | the link state |
| `can i run nginx` | SSH server | web server |
| `what driver does it need?` | generic refusal | ask which device |

Two of these — the DHCP client/server confusion — are one fix. Reaching <10% needs three or
four more deterministic paths, not a better model.

## The conclusion this points at

**Stop growing the corpus; grow the rule engine.** The corpus is bounded by 6M parameters and
by a tokenizer that cannot represent held-out words. The rule engine has neither limit, is
deterministic, and is the only path that can answer a question containing a word the model has
never seen.

The model's job is what the tables cannot answer. That is a narrower job than the PRD assumed,
and the measurement supports it twice over.

## Artifacts

- `SLM/tools/build_corpus.py` — the four new coverage classes (kept: they help, they are simply
  not sufficient)
- `agent/kernel_spec/subsystems/slm.md` — **Shell Idioms — Deterministic, Before the Model
  (REQUIRED)**, with the vocabulary argument and the 12-row idiom table
- `tests/eval/baseline-deterministic-dispatch.json` — the graded 65-prompt run
- The kernel implementation was a reference; its structure is in
  `kernel_spec/reference/x86_64/graph.json`, and the tree is deleted again
