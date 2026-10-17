# Gates and Testing

A result means something only if the test that judged it could have failed, was written
before the result existed, and was never shown to the agents being judged.

## Exit codes

| Exit | Meaning |
|---|---|
| 0 | pass |
| 1 | generated wrong: the code exists and fails a check |
| 2 | not generated: there is nothing to check. Never a pass |

A campaign run that ends "not generated" on every gate in under 30 minutes is treated as a
**harness failure**, not a result: the campaign stops and says so.

## Host gate suites (`tests/kernel/`)

22 suites (`run_*_test.sh`) compile the generated subsystem on the host against a frozen
interface header and run behavioural checks, without booting a kernel: memory manager, VMM,
VirtIO block, net and console (29 checks), FAT32, file server, KV store, SMTP, SSH (28), DHCP,
TFTP (31), host-repo, the DTB parser, play-Doom, boot info, display, errata lookup, the fault
harness, CPU identity, capability leakage, and the degenerate-model guard.

- `KERNEL_TREE=<tree> tests/kernel/run_<x>_test.sh` judges a tree; the tree is a parameter,
  never the script's parent, because verification must not live inside the artifact it
  verifies.
- `--self-test` runs the suite against its hand-written reference: a suite that has never
  passed anything has proved nothing.
- `--inject` scores the suite against defects planted in the reference
  (`run_mm_test.sh --inject` → 9/9; `run_play_doom_test.sh` → 10/10). A suite that misses a
  planted bug has a gap.
- Every run is seeded with the suite's interface (`tests/kernel/<x>_reference/include`), and
  a unit test fails if a suite uses a name neither its spec nor that header declares. Eleven
  campaign failures were exactly that.

## Boot and end-to-end gates

| Gate | Checks |
|---|---|
| `scripts/boot-marker.sh <tree> <regex>` | builds the ISO, boots QEMU, waits for a serial line (e.g. `^\[MM\] PMM initialized`) |
| `scripts/run-acceptance.sh` | 14 boot markers, a real DHCP lease, a real HTTP 200 |
| `scripts/e2e.sh` | train → export → parity → ISO → boot → transcript |
| `tests/kernel/neural_parity.sh` | the kernel's forward pass generates the same tokens as PyTorch |
| `scripts/eval.sh` | the chat eval: 65 frozen prompts (the published baselines scored the original 50), bar ≥70% correct-or-honest and <10% garbage |
| `scripts/run-intent-probe.sh` | a scenario probe outside the image (Doom frame changes on Escape; `git clone` of the served repo) |

## Agent-output gates

| Gate | Judges |
|---|---|
| syntax gate | code compiles before any reviewer sees it |
| `check_record` | an Analyst's evidence: closed index, provenance, every quote on its line |
| `package_gate.py` | a Packager's Dockerfile builds, inventories and starts |
| `check_hardware_record` | a Scout's proposal loads as inventory; a Reader's quotes are on their pages |
| `vocab_budget.py` | a training set fits the kernel tokenizer with 0% answer `<unk>` |

## Unit and integration tests

About 2,200 Python tests (`agent/tests/unit`, `agent/tests/integration`), 166 SLM tests
(`SLM/tests`), the control plane's own suite, and Rust tests in `agent/tools/`. Tests that
need a live model or Docker skip, and say so, when it is unreachable.

## Pre-registration

A generation run's goal, base, seeds, gates and stop rule are committed before it starts
(`docs/campaign/runs.yaml`, `reports/*-preregistration.md`) and changed only by a dated
amendment. A changed harness, model, host or prompt is a different experiment. See
[Generation Campaign](Generation-Campaign).
