# Plan: Conformance in Every Image, Verified at First Boot (H10c, H10d)

## Summary
The PRD's scaling argument: *"A suite in one repository tests one researcher's machines. A suite
in every deployment tests every machine"* (Decisions Log). This plan makes the factory emit an
**intent-scoped** conformance suite into each image. The suite covers the instructions *that
image's own code executes*, found by disassembling it and intersecting with the clause-cited
corpus from `w14-hardware-conformance-harness`. The image runs it at first boot on whatever
silicon it lands on, and answers "is this machine safe?" with both the errata verdict (H8) and
its own conformance result.

## User Story
As someone who installed an AUTON image on real hardware, I want it to check that this CPU
computes and faults as documented for the instructions my image uses, and to tell me in chat,
so that "safe" includes "verified here", not just "no known errata".

## Problem → Solution
Conformance runs in CI only; images know nothing about their silicon beyond CPUID →
`build_service.py` gains a conformance step (disassemble the image, select the corpus, embed an
oracle table), the kernel runs it at boot and prints `[CONF] <n> checks, <d> divergences`, and
the chat's safety answer includes it.

## Metadata
- **Complexity**: Large
- **Source PRD**: `auton-hardware-truth.prd.md`
- **PRD Phase**: H10c (generated self-tests), H10d (install-time verification)
- **Estimated Files**: ~9
- **Depends on**: `w14-hardware-conformance-harness` (corpus, oracle, in-kernel harness spec), F5 (landed), H8 (landed), `w13-generate-mm`-style generation of the harness into a tree

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `w14-hardware-conformance-harness.plan.md` | all | corpus format, oracle, `arch_expect_fault` |
| P0 | `agent/tools/build_service.py` | 256-340 | gate order; where a generated step joins (after link closure, before ISO) |
| P0 | `agent/tools/machine_safety.py` | 39-135 | `SafetyReport.summary`: "not examined is not safe", which is extended here |
| P0 | `agent/tools/package_image.py` | 215-250 | `spec/errata.json`: conformance results join `PROVENANCE.json` the same way |
| P1 | base `kernel/slm/sysinfo.c`, `slm.c` | safety/"is this machine safe" handling | the chat surface to extend |
| P1 | base `kernel/arch/x86_64/toolchain.mk` | CFLAGS | `-mno-sse -mno-mmx`: in-kernel FP needs a separately compiled TU and CR4.OSFXSR |

## Patterns to Mirror
### GENERATED_INTO_BUILD_DIR
// SOURCE: agent/tools/build_service.py:305-312: generated C lives in `build-<svc>/generated/`, never under `kernel/`.
### HONEST_SUMMARY
// SOURCE: agent/tools/machine_safety.py:52-58: `"This machine has not been examined — that is not the same as safe."`

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/tools/conformance_select.py` | CREATE | `objdump -d` the linked kernel → the mnemonic set → corpus entries whose instruction is in the set → `conf_table.c` (operands + SoftFloat results + fault encodings) |
| `agent/tools/build_service.py` | UPDATE | a `[gate: conformance]` step emitting `build-<svc>/generated/conf_table.c` and linking `conf_run.c`; records N checks in `BuildResult.gates` |
| `agent/kernel_spec/conformance/runtime.md` | CREATE | REQUIRED: run once at first boot after `idt_init`; SSE enabled only inside the runner; markers `[CONF] <n> checks`, `[CONF] <d> divergences`, `[CONF] diverged <clause-id> expected <hex> got <hex>` |
| `tests/kernel/conf_run_test.c` + reference | CREATE | host proof of the runner over a table |
| `agent/tools/machine_safety.py` | UPDATE | `summary()` includes conformance: "verified here: N checks, 0 divergences", "not verified here", or divergences with clause ids |
| `agent/kernel_spec/subsystems/slm.md` | UPDATE | the chat answer template for "is this machine safe?" gains the conformance line |
| `agent/tools/package_image.py` | UPDATE | `spec/conformance.json` (the selected checks) in the package, recorded in PROVENANCE |
| `agent/tests/unit/test_conformance_select.py` | CREATE | a synthetic disassembly with `divsd` selects the div corpus and not sqrt; an image with no FP selects only fault checks |

## NOT Building
- Uploading results anywhere (H10e).
- Checks for instructions the image never executes. That is the scoping claim; keep it honest.

## Step-by-Step Tasks
### Task 1: Selection (RED → GREEN)
- **GOTCHA**: `objdump` mnemonics differ in spelling from SDM names (`divsd` vs `DIVSD`, AT&T suffixes like `fdivl`). Normalise with an explicit table, tested, not regexes that happen to work.
- **VALIDATE**: the unit tests above.

### Task 2: Runtime spec + host proof
- **GOTCHA**: Enabling SSE for the runner and disabling it afterwards must save and restore CR0/CR4 exactly. A kernel compiled `-mno-sse` that leaves OSFXSR set is fine; one that leaves `CR0.EM` wrong faults on the next FP use.
- **VALIDATE**: `conf_run_test.sh --self-test`.

### Task 3: Factory step
- **VALIDATE**: `build_service.py dhcp --tree <ws>` lists `conformance: N checks selected`; the ISO boots and prints the `[CONF]` markers under QEMU (0 divergences expected: QEMU is the idealised CPU, which is why QEMU passing proves the plumbing only).

### Task 4: Chat + safety report
- **ACTION**: "is this machine safe?" → errata verdict (H8) + conformance line. On QEMU, the answer must say "emulated CPU: conformance proves the harness, not the silicon". H5's identity already knows the hypervisor bit.
- **VALIDATE**: a serial transcript in the acceptance markers.

### Task 5: Package record
- **VALIDATE**: `PROVENANCE.json` lists `spec/conformance.json` with its selection source.

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/test_conformance_select.py -q
tests/kernel/run_conf_run_test.sh --self-test
.venv/bin/python agent/tools/build_service.py dhcp --tree <ws> --iso && scripts/e2e.sh --target <ws> --skip-train
```

## Acceptance Criteria
- [ ] Each image's suite is derived from its own disassembly
- [ ] First boot prints `[CONF]` markers; chat reports them
- [ ] Under emulation the answer says what it cannot prove
- [ ] Divergences cite clause ids

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Boot time grows | M | L | a check budget per image (stated), and the count printed |
| The FP state corrupts the kernel | M | H | Task 2's gotcha; a host proof; restore verified in QEMU |


---

## Progress: Task 1 (2026-09-22)

`conformance_select.py`: per-image selection by disassembly, with an explicit mnemonic table. It found and closed a real gap (DIVSS/SQRTSS uncovered). **Remaining**: Tasks 2-5, all of which need a generated tree (the in-kernel runner, the factory step, the chat answer, the package record).


---

## Closed 2026-09-23

Selection by disassembly is done and found a real gap (DIVSS/SQRTSS). The in-kernel runner, the factory step and the chat answer need a generated tree.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
