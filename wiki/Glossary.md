# Glossary

| Term | Meaning |
|---|---|
| **AUTON format** | the flat model file every kernel must load: header, weights in fixed order, vocabulary, device table (`SLM/tools/auton_format.py`) |
| **base tree** | a tagged starting kernel (`kernel-base-v5`) a run is seeded from, so a gate refusal means something |
| **baseline ISA** | the instructions a kernel may use without asking: x86-64 v1, Armv8.0-A, RV64IMAC |
| **campaign** | the ordered set of generation runs R1–R12 (`docs/campaign/runs.yaml`) |
| **`cpu_has()`** | the only way kernel code may ask whether the CPU implements an optional feature |
| **exception (ISA)** | a cited case where silicon disagrees with documents: never shipped, removed, fused off, microcode disabled, undocumented |
| **frozen suite** | a gate written and committed before the run it judges, never shown to the agents |
| **Frankenstein effect** | subsystems that pass alone and fail together |
| **gate** | a check that decides a run: exit 0 pass, 1 generated wrong, 2 not generated |
| **ground truth** | the source an answer is generated from: what the kernel prints, a table, a document |
| **injected bugs** | defects planted in a reference to score a suite: one it misses is a gap |
| **inventory / registry** | `vendors.yaml` (what documents a vendor publishes) / `registry/vendors.json` (every vendor that ever held an id) |
| **parity** | the kernel's forward pass generating exactly the tokens PyTorch does on the same model |
| **phantom citation** | a model naming a device id that is not on the bus |
| **pre-registration** | a run's goal, gates and stop rule committed before it starts |
| **rule engine** | the SLM's non-neural backend, for small machines or no model |
| **SLM** | the small language model inside the kernel |
| **specialist** | a developer agent with one area's specs, knowledge and review checklist |
| **testing area** | a gitignored directory where generated trees live (`.artifacts/…/ws`) |
| **vocabulary budget** | the kernel tokenizer's 1,024 words; a kernel corpus must fit it with 0% `<unk>` |
| **workflow mode** | `kernel_build`, `slm_training` or `dual` |
