# Agents and Swarms

Four swarms share one engine. Each role is **constructed, registered and advertised**
together: a role the manager is told about but nobody registered sends its tasks to an empty
pool, which happened once (w12) and is now tested for every role.

## Kernel build swarm

| Role | Count | Does | Tools (highlights) |
|---|---|---|---|
| Manager | 1 | decomposes the goal into a task graph; assigns each task to a role | `read_spec`, `create_task` (read-only otherwise) |
| Architect | 1 | writes interface headers | read/write files, `read_spec` |
| Developer | `developer_count` (4) | implements tasks on branches | files, `build_kernel`, `run_test`, `git_commit`, `shell` (allowlist) |
| **Specialists** | 24 | developers with one area's specs, knowledge and checklist; pool `<id>_specialist` | as Developer. See [[Specialists]] |
| Reviewer | `reviewer_count` (1) | reviews the full diff, with each matching specialist checklist | `run_gate`, read files, `git_diff`, `read_spec` |
| Tester | `tester_count` (1) | runs gates and QEMU validation | `run_gate`, `run_ablation`, `build_kernel`, `run_test` |
| Integrator | 1 | merges approved branches; places an SLM model | `integrate_slm`, build and test |

Launched by `scripts/campaign.py` (the pre-registered campaign, see
[Generation Campaign](Generation-Campaign)) or `auton run "<goal>"`.

## SLM swarm

Created in `slm_training` and `dual` modes. Follows [`SLM/DATA.md`](https://github.com/EdWelsh/AUTON/blob/HEAD/SLM/DATA.md).

| Role | Does | Tools |
|---|---|---|
| Data Scientist | generates the kernel training set from ground truth; proves it fits the 1,024-word tokenizer | `build_corpus`, `check_vocab_budget`, `tokenize_data`, `analyze_dataset` |
| Model Architect | chooses the config, starting from `chat_tiny` (6M); checks vocabulary and boot-memory budgets | `validate_architecture`, `estimate_flops` |
| Training ×2 | trains; exports the AUTON format; proves parity with the kernel's forward pass; scores the chat eval; tries int8 | `train_model`, `evaluate_model`, `export_auton`, `run_parity`, `run_chat_eval`, `quantize_model` |
| Integrator | places `models/auton-slm.bin` where `make iso-neural` boots it | `integrate_slm` (refuses GGUF/ONNX) |

Seven tasks, each naming what it produces: data → config → train → evaluate (parity + eval)
→ int8 if it holds → export → integrate. Launched by `scripts/slm_run.py`. See [The SLM](SLM).

## Hardware research swarm

Opt-in per run (`[hardware] research = true`), launched by `scripts/vendor_research.py`.

| Role | Does |
|---|---|
| Vendor Scout | for a registry vendor with no coverage, finds what it publishes and proposes `vendors.yaml` entries, or a gap |
| Spec Reader | reads a fetched document and derives records that quote the page they cite |

See [Vendor Spec Agents](Vendor-Spec-Agents).

## Application-to-environment swarm

| Role | Does |
|---|---|
| Analyst | reads a staged application (read-only, no shell) and writes an evidence record, every fact quoted from a file and line |
| Packager | writes a Dockerfile and provenance for a validated manifest; the gate, not the Packager, builds it |

See [Application to Environment](Application-to-Environment).

## Rules every role obeys

- **Only its own tools.** Any other name is refused, with the list it does have. (On the
  first live Analyst run the read-only manager called `write_file` and wrote the Analyst's
  record itself; dispatch is now checked per role.)
- **Fixed plans are not a model's to make.** The engine seeds the Analyst's and Packager's
  single task rather than hoping the manager plans it.
- **Untrusted input stays data.** A staged application, a fetched vendor PDF: quoted, never
  obeyed.
- **Branches, not shared files.** Work merges or it does not.
