# Plan: Finish the AUTON codebase & boot a local OS in Docker

## Summary
The AUTON orchestrator (Python agent framework) is real and well-tested, but every *output* it is meant to produce is missing or stubbed: there is **no kernel source** (`kernels/` is empty), **no build system** (no Makefile/linker/boot asm), **no Docker toolchain/QEMU environment**, the **Rust tools are stubs** (`kernel-builder`, `test-runner`, `diff-validator` all print "not yet implemented"), the validators are **never wired into the engine loop**, and the **SLM training scripts are all `TODO`**. This plan finishes the codebase end-to-end and delivers a reproducible **`docker compose run`-able local OS that boots in QEMU** and emits the acceptance-test serial markers, then layers in the SLM rule-engine and the full orchestration/validation/training pipeline.

## User Story
As an AUTON developer,
I want a single Docker-based command that builds the kernel and boots it in QEMU (plus a working orchestrator/validation/SLM pipeline),
So that I can run a local SLM-driven OS reproducibly and let the agents extend a known-good, buildable scaffold instead of a blank directory.

## Problem → Solution
**Current state:** Orchestrator runs, but agents are pointed at an empty `kernels/x86_64`, there is no toolchain/QEMU available, no build system to invoke, the build/test/composition validators are dead code (never instantiated by `engine.py`), the Rust helpers are stubs, and nothing has ever booted.
**Desired state:** A multi-stage Docker image carries the x86_64 cross-toolchain + QEMU + Python + Rust. A committed **seed kernel + build system** boots in QEMU under Docker and prints the `boot` acceptance markers. The Rust `kernel-builder`/`test-runner` are implemented and the Python validators are wired into the engine loop. A minimal in-kernel **rule-engine SLM** brings the system to `[SLM] Ready`, satisfying the `full_boot_to_slm` integration test. The SLM training scripts run end-to-end on a tiny config. `docker compose run os` boots the OS; `docker compose run orchestrate` runs the agents against the seeded tree.

## Metadata
- **Complexity**: XL (multi-subsystem; spans Python, Rust, C, asm, Docker — should be executed phase-by-phase, each phase independently shippable)
- **Source PRD**: N/A (free-form request: "Look over e2e and create a comprehensive plan to finish the repo code base and get a local os on docker running")
- **PRD Phase**: N/A
- **Estimated Files**: ~45–60 created, ~8 modified
- **MVP boundary**: **Phases 0–2 deliver "a local OS booting on Docker."** Phases 3–6 finish the rest of the codebase.

---

## UX Design

### Before
```
$ cd agent && auton run "Build a bootable kernel ..."
  → agents spawn, point at empty kernels/x86_64
  → developer agent runs `make` → "No Makefile found in workspace"
  → no toolchain installed, nothing ever builds or boots
  → kernels/ stays empty; no OS exists
```

### After
```
$ docker compose run os            # build seed kernel + boot in QEMU
  AUTON Kernel booting
  [BOOT] Multiboot magic valid
  [BOOT] Long mode enabled
  [BOOT] 64-bit GDT loaded
  [BOOT] Interrupts initialized
  [DRV] Serial 16550 initialized
  [SLM] Rule engine initialized
  [SLM] Ready
  [BOOT] OK

$ docker compose run acceptance    # build + QEMU + parse markers → pass/fail
  boot: 5/5  drivers: 2/2  slm: 2/2  integration: 1/1   ALL PASS

$ docker compose run orchestrate "Add a PCI bus scanner"   # agents extend the seed tree
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Build a kernel | impossible (no Makefile/toolchain) | `make` inside Docker image | toolchain baked into image |
| Boot the OS | impossible | `docker compose run os` | QEMU `-kernel` + `-serial stdio` |
| Acceptance tests | defined but un-runnable | `docker compose run acceptance` | runs `acceptance_tests.py` markers |
| Orchestrator workspace | `repo root` (CLI) vs `../kernels/x86_64` (config) mismatch | resolves to `kernels/{arch}` consistently | bug fix, see Task 0.2 |
| Validators | imported nowhere in `engine.py` | instantiated and called each iteration | wiring fix, Phase 3 |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/orchestrator/core/engine.py` | 40–360 | The live loop; where validators must be wired; workspace path logic |
| P0 | `agent/orchestrator/validation/build_validator.py` | all | Expects `Makefile` at workspace root; parses GCC diagnostics; target contract |
| P0 | `agent/orchestrator/validation/test_validator.py` | 65–141 | Hardcodes `qemu ... -kernel <ws>/build/kernel.bin -serial stdio`; parses `[TEST]`/`[BOOT] OK` markers — **defines the boot artifact contract** |
| P0 | `agent/kernel_spec/tests/acceptance_tests.py` | all | The exact serial-marker strings the seed kernel must print (`AUTON Kernel booting`, `[BOOT] ...`, `[SLM] Ready`, etc.) |
| P0 | `agent/kernel_spec/architecture.md` | 182–266 | Canonical kernel directory layout + Makefile shape the seed must match |
| P0 | `agent/orchestrator/arch_registry.py` | 52–116 | Toolchain/QEMU/boot-protocol per arch — Dockerfile + Makefile must match `x86_64` profile (`x86_64-elf-gcc`, `nasm`, multiboot2) |
| P1 | `agent/kernel_spec/subsystems/boot.md` | 1–80 | `boot_info_t`, `hw_summary` structs the seed `kernel_main` consumes |
| P1 | `agent/kernel_spec/subsystems/slm.md` | all | Rule-engine intent API the in-kernel SLM must expose |
| P1 | `agent/orchestrator/agents/base_agent.py` | 304–318 | `_run_build` runs `make -C <workspace> <target>` — Makefile must support `all` |
| P1 | `agent/tools/kernel-builder/src/main.rs` | all | Stub to implement; clap CLI contract already defined (`--workspace --arch --output --clean`) |
| P1 | `agent/tools/test-runner/src/main.rs` | all | Stub to implement; wraps QEMU + serial capture |
| P2 | `agent/orchestrator/validation/composition_validator.py` | all | Frankenstein check to wire in |
| P2 | `SLM/scripts/train.py` + `SLM/tools/*.py` | all | Training stubs to implement (Phase 5) |
| P2 | `agent/config/auton.toml.example` | 49–64 | `[workspace].path = "../kernels/x86_64"`, `[kernel].arch` |

## External Documentation

| Topic | Source | Key Takeaway |
|---|---|---|
| Multiboot + long mode boot | OSDev Wiki "Setting Up Long Mode", "Multiboot" | 32-bit multiboot entry → set up 64-bit GDT + PML4 identity map → `lret` into long mode → call `kernel_main`. Well-documented, copyable. |
| QEMU `-kernel` boot protocol | QEMU docs / OSDev | **`qemu-system-x86_64 -kernel` understands Multiboot v1 ELF, not Multiboot2.** The seed must carry a Multiboot v1 header (or both) to boot via the existing `TestValidator` `-kernel` path. See GOTCHA in Task 1.2 / 2.1. |
| x86_64-elf cross toolchain | OSDev "GCC Cross-Compiler" | Build `binutils` + `gcc` for `x86_64-elf`, or `apt-get install gcc-x86-64-linux-gnu` + `-ffreestanding -nostdlib`. Bake into Docker layer; cache it. |
| 16550 UART serial | OSDev "Serial Ports" | COM1 = port `0x3F8`; init LCR/IER/FCR; write byte when THR empty. The only output device the acceptance harness reads (`-serial stdio`). |
| grub-mkrescue ISO (release) | GNU GRUB manual | For Phase 6 ISO artifacts (`auton-x86_64-*.iso`); needs `grub-pc-bin`, `xorriso`, `mtools`. |

```
KEY_INSIGHT: The acceptance harness boots with `qemu-system-x86_64 -kernel <build/kernel.bin> -serial stdio` and only reads serial output.
APPLIES_TO: Phases 1–2 (seed kernel + Dockerfile).
GOTCHA: `-kernel` = Multiboot **v1**. The arch profile/spec say "multiboot2". Use a Multiboot v1 header for the `-kernel` boot path (and optionally a multiboot2 header for the GRUB/ISO path in Phase 6). Adjust the x86 boot marker in acceptance_tests.py from "Multiboot2 magic valid" to "Multiboot magic valid" (Task 2.4).
```

---

## Patterns to Mirror

Follow these exactly — new code must be indistinguishable from existing code.

### RESULT_DATACLASS (validators return frozen-ish dataclasses)
```python
# SOURCE: agent/orchestrator/validation/build_validator.py:14-21
@dataclass
class BuildResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    duration_secs: float = 0.0
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
```

### ASYNC_SUBPROCESS (how the codebase shells out — reuse verbatim)
```python
# SOURCE: agent/orchestrator/validation/build_validator.py:56-98
proc = await asyncio.create_subprocess_exec(
    "make", "-C", str(self.workspace_path), target,
    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
# ... decode("utf-8", errors="replace"); handle asyncio.TimeoutError + FileNotFoundError
```

### ARCH_PROFILE (single source of truth for toolchain/QEMU)
```python
# SOURCE: agent/orchestrator/arch_registry.py:53-73
"x86_64": ArchProfile(
    name="x86_64", display_name="x86_64 (AMD64)",
    cc="x86_64-elf-gcc", asm="nasm", ld="x86_64-elf-ld",
    asm_format="-f elf64", boot_protocol="multiboot2",
    qemu="qemu-system-x86_64", core_drivers=["serial_16550", "vga_text", ...],
)
```

### LOGGING_PATTERN (module logger, %-style args, no f-strings in log calls)
```python
# SOURCE: agent/orchestrator/validation/build_validator.py:11,82-84
logger = logging.getLogger(__name__)
logger.info("Build succeeded in %.1fs", duration)
logger.warning("Build failed with %d errors", len(errors))
```

### PYTEST_FIXTURE (tmp_path + patched GitWorkspace; arch-aware asserts)
```python
# SOURCE: agent/tests/integration/test_kernel_workflow.py:33-44
@pytest.fixture
def kernel_engine(kernel_config, tmp_path):
    spec_path = tmp_path / "kernel_spec"; spec_path.mkdir()
    with patch("orchestrator.core.engine.GitWorkspace"):
        engine = OrchestrationEngine(workspace_path=tmp_path,
            kernel_spec_path=spec_path, config=kernel_config)
    return engine
```

### RUST_CLI (clap + anyhow + tracing — already scaffolded)
```rust
// SOURCE: agent/tools/kernel-builder/src/main.rs:5-34
#[derive(Parser)]
#[command(name = "kernel-builder", about = "Build orchestration for AUTON kernel")]
struct Cli { #[arg(short, long, default_value = "workspace")] workspace: PathBuf, /* ... */ }

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    tracing::info!(workspace = %cli.workspace.display(), arch = %cli.arch, "Starting kernel build");
    Ok(())
}
```

### KERNEL_C_STYLE (Linux style: tabs, K&R, HAL calls, header prototypes)
```c
// SOURCE: agent/kernel_spec/architecture.md:268-277 (coding standards) + boot.md structs
/* tabs for indent, K&R braces, every exported fn prototyped in a header,
   portable code calls arch_*() HAL — never raw instructions */
void kernel_main(boot_info_t *boot)
{
	serial_init();
	kprintf("AUTON Kernel booting\n");
}
```

---

## Files to Change

### Phase 0 — Hygiene & wiring fixes
| File | Action | Justification |
|---|---|---|
| `.gitignore` | UPDATE | ignore `build/`, `*.o`, `*.bin`, `*.iso`, `.auton/`, `**/.DS_Store` |
| `**/.DS_Store` | DELETE | committed macOS cruft (root, SLM, agent, kernels) |
| `agent/orchestrator/cli.py` | UPDATE | resolve workspace to `kernels/{arch}` from config, not repo root (Task 0.2) |

### Phase 1 — Docker toolchain/QEMU environment
| File | Action | Justification |
|---|---|---|
| `Dockerfile` | CREATE | multi-stage: toolchain+QEMU base, python deps, rust build |
| `docker-compose.yml` | CREATE | services: `os`, `acceptance`, `orchestrate`, `test` |
| `.dockerignore` | CREATE | keep build context lean |
| `scripts/auton-boot.sh` | CREATE | build seed + `qemu -kernel ... -serial stdio` |
| `scripts/run-acceptance.sh` | CREATE | invoke `acceptance_tests.py` runner |

### Phase 2 — Seed x86_64 kernel + build system (the bootable OS)
| File | Action | Justification |
|---|---|---|
| `kernels/x86_64/Makefile` | CREATE | top-level; `all` → `build/kernel.bin`; matches architecture.md shape |
| `kernels/x86_64/kernel/arch/x86_64/toolchain.mk` | CREATE | CC/AS/LD/flags from arch profile |
| `kernels/x86_64/kernel/arch/x86_64/linker.ld` | CREATE | multiboot section first, 1M load, ELF64 |
| `kernels/x86_64/kernel/arch/x86_64/boot/multiboot_header.S` | CREATE | Multiboot v1 (+optional v2) header for QEMU `-kernel` |
| `kernels/x86_64/kernel/arch/x86_64/boot/boot.S` | CREATE | 32-bit entry → GDT64 + PML4 identity map → long mode → `kernel_main` |
| `kernels/x86_64/kernel/arch/x86_64/io/io.h` | CREATE | `inb/outb` port I/O (HAL impl) |
| `kernels/x86_64/kernel/drivers/arch/serial_16550.c` | CREATE | COM1 init + putchar → `[DRV] Serial 16550 initialized` |
| `kernels/x86_64/kernel/lib/kprintf.c` + `string.c` | CREATE | freestanding printf/strlen/memcpy |
| `kernels/x86_64/kernel/include/boot_info.h` | CREATE | `boot_info_t`, `hw_summary` from boot.md |
| `kernels/x86_64/kernel/boot/kernel_main.c` | CREATE | prints boot markers, inits subsystems, calls SLM, prints `[BOOT] OK` |
| `kernels/x86_64/kernel/include/*.h` | CREATE | HAL + subsystem prototypes used by seed |

### Phase 3 — Rust tools + validator wiring
| File | Action | Justification |
|---|---|---|
| `agent/tools/kernel-builder/src/main.rs` | UPDATE | implement: run `make` per arch, copy artifact to `--output`, structured result |
| `agent/tools/test-runner/src/main.rs` | UPDATE | implement: launch QEMU, capture serial, parse `[TEST]`/`[BOOT]`, timeout |
| `agent/tools/diff-validator/src/main.rs` | UPDATE | implement: parse unified diff, apply validation rules (existing tests define contract) |
| `agent/orchestrator/core/engine.py` | UPDATE | instantiate BuildValidator/TestValidator/CompositionValidator; call after integrate |
| `agent/orchestrator/validation/__init__.py` | UPDATE | export validators for engine import |

### Phase 4 — In-kernel rule-engine SLM + device framework (minimal)
| File | Action | Justification |
|---|---|---|
| `kernels/x86_64/kernel/dev/pci.c` | CREATE | PCI enumeration via `0xCF8/0xCFC` → `[DEV] PCI scan: N devices found` |
| `kernels/x86_64/kernel/slm/engine/slm.c` | CREATE | intent dispatch + `slm_init` → `[SLM] Rule engine initialized` / `[SLM] Ready` |
| `kernels/x86_64/kernel/slm/rules/rules.c` | CREATE | keyword/PCI-id → driver mapping; `slm_driver_select` |
| `kernels/x86_64/kernel/slm/knowledge/pci_ids.c` | CREATE | tiny embedded PCI-id→driver table (e.g. 8086:100e → e1000) |

### Phase 5 — SLM training pipeline (host-side, optional for boot)
| File | Action | Justification |
|---|---|---|
| `SLM/tools/dataset_builder.py` | UPDATE | implement collect/analyze/split (currently TODO) |
| `SLM/tools/tokenizer.py` | UPDATE | implement BPE train + encode |
| `SLM/scripts/train.py` | UPDATE | implement tiny-config training loop w/ checkpointing |
| `SLM/scripts/evaluate.py` + `quantize.py` + `export_gguf.py` + `export_onnx.py` | UPDATE | implement minimal real paths |
| `SLM/tools/metrics.py` + `gguf_validator.py` | UPDATE | implement |

### Phase 6 — Release artifacts + docs
| File | Action | Justification |
|---|---|---|
| `scripts/build-iso.sh` | CREATE | grub-mkrescue → `auton-x86_64-*.iso` (README claims releases) |
| `README.md` | UPDATE | replace aspirational claims with verified `docker compose run os` quickstart |
| `agent/kernel_spec/tests/acceptance_tests.py` | UPDATE | x86 boot marker multiboot2→multiboot (Task 2.4); add runner entrypoint |

## NOT Building
- A *neural* SLM running inside the kernel (GGUF/ONNX CPU inference in-kernel). Out of scope; the **rule engine** backend is the bootable default. Neural backend stays a documented stretch goal.
- Full filesystem (ext2/VFS), TCP/IP stack, package manager, multi-process scheduler beyond what the **listed acceptance markers** require. Seed targets `boot`, `drivers`, `slm`, and the `full_boot_to_slm` integration test only.
- AArch64 / RISC-V seed kernels. Build system and Docker are parameterized by arch, but only **x86_64** is brought to "boots + passes" in this plan. Other arches remain agent-extendable.
- GPU/accelerated SLM training. Phase 5 uses a tiny CPU config purely to prove the pipeline runs end-to-end.
- Replacing the agent-driven generation model. The seed is a *scaffold the agents extend*, not a hand-finished OS.

---

## Step-by-Step Tasks

### Phase 0 — Hygiene & wiring

#### Task 0.1: Remove committed cruft, fix .gitignore
- **ACTION**: Delete all `.DS_Store`; add build artifacts to `.gitignore`.
- **IMPLEMENT**: `git rm --cached **/.DS_Store`; append `build/`, `*.o`, `*.bin`, `*.elf`, `*.iso`, `.auton/`, `.DS_Store` to `.gitignore`.
- **MIRROR**: existing `.gitignore` style.
- **VALIDATE**: `git status` clean of `.DS_Store`; `find . -name .DS_Store -not -path './.git/*'` → empty.

#### Task 0.2: Fix orchestrator workspace resolution
- **ACTION**: Make `cli.py run` resolve the workspace from `[workspace].path` / `[kernel].arch` (→ `kernels/{arch}`), not the repo root, so agents and validators target the same tree the seed lives in.
- **IMPLEMENT**: In `cli.py:110-116`, when `--workspace` is not passed, read `config["workspace"]["path"]` (default `kernels/{arch}`) resolved relative to repo root; create it if missing.
- **MIRROR**: existing `Path(...).resolve()` usage in `cli.py`.
- **GOTCHA**: `build_validator`/`test_validator` expect `Makefile` and `build/kernel.bin` **at the workspace root** — so the workspace MUST be `kernels/x86_64` where Phase 2 puts the Makefile.
- **VALIDATE**: `auton run "noop" --help` works; manual: workspace path printed = `.../kernels/x86_64`.

### Phase 1 — Docker environment (delivers reproducible build/run)

#### Task 1.1: Multi-stage Dockerfile
- **ACTION**: Create `Dockerfile` with the x86_64 cross-toolchain, NASM, QEMU, Python 3.11, Rust.
- **IMPLEMENT**: Base `debian:bookworm-slim`; install `build-essential nasm qemu-system-x86 grub-pc-bin xorriso mtools python3.11 python3-pip cargo rustc`. For the cross-compiler, either install `gcc-x86-64-linux-gnu` (use with `-ffreestanding -nostdlib`) **or** build `x86_64-elf-gcc` in a cached stage. `pip install -e agent[dev]`. Build Rust tools (`cargo build --release` in `agent/tools`).
- **MIRROR**: toolchain names from `arch_registry.py:53-73` (`x86_64-elf-gcc`, `nasm`). If using `gcc-x86-64-linux-gnu`, set `CC` override in `toolchain.mk` accordingly (Task 2.2).
- **GOTCHA**: Building a full `x86_64-elf` GCC is slow (~20 min); cache that layer. The simpler `gcc-x86-64-linux-gnu` + freestanding flags boots fine for a flat kernel and keeps the image small — prefer it unless red-zone/PIC issues arise.
- **VALIDATE**: `docker build -t auton .` succeeds; `docker run auton x86_64-elf-gcc --version || gcc-x86-64-linux-gnu-gcc --version`; `qemu-system-x86_64 --version`; `auton --help`.

#### Task 1.2: docker-compose services
- **ACTION**: Create `docker-compose.yml` with `os`, `acceptance`, `orchestrate`, `test` services over the same image, mounting the repo.
- **IMPLEMENT**:
  - `os`: `command: bash scripts/auton-boot.sh x86_64`
  - `acceptance`: `command: bash scripts/run-acceptance.sh x86_64`
  - `test`: `command: bash -c "cd agent && pytest -q && cd tools && cargo test"`
  - `orchestrate`: `command: bash -c "cd agent && auton run \"$$GOAL\""`, passes `ANTHROPIC_API_KEY` from env.
- **MIRROR**: arch parameterization (env `ARCH=x86_64`).
- **GOTCHA**: QEMU needs `-display none -no-reboot` (already in `test_validator.py:82-83`); no KVM inside CI containers — use TCG (default). Keep `-serial stdio`.
- **VALIDATE**: `docker compose run test` green (after Phase 2 builds exist for acceptance).

#### Task 1.3: boot + acceptance shell scripts
- **ACTION**: `scripts/auton-boot.sh` builds the seed and boots; `scripts/run-acceptance.sh` runs the marker checker.
- **IMPLEMENT**: `auton-boot.sh`: `make -C kernels/$1` then `qemu-system-x86_64 -kernel kernels/$1/build/kernel.bin -serial stdio -display none -no-reboot -m 128M`. `run-acceptance.sh`: `python agent/kernel_spec/tests/acceptance_tests.py --arch $1` (runner added in Task 2.4).
- **MIRROR**: exact QEMU flags from `test_validator.py:80-84`.
- **VALIDATE**: after Phase 2, `docker compose run os` prints `AUTON Kernel booting` … `[BOOT] OK`.

### Phase 2 — Seed kernel (THE BOOTABLE OS — MVP target)

#### Task 2.1: Multiboot header + linker script
- **ACTION**: Create `multiboot_header.S` (Multiboot v1; magic `0x1BADB002`) and `linker.ld` placing it in the first 8 KiB, load at 1 MiB.
- **IMPLEMENT**: standard multiboot1 header (magic, flags, checksum). Linker: `.multiboot` first, `.text/.rodata/.data/.bss`, ENTRY(`_start`), kernel at `0x100000`.
- **MIRROR**: build shape in `architecture.md:182-208`.
- **GOTCHA**: QEMU `-kernel` requires the Multiboot v1 header in the first 8 KiB of the ELF or it refuses to boot ("multiboot header not found"). Keep it section-first.
- **VALIDATE**: `make` produces `build/kernel.bin`; `grub-file --is-x86-multiboot build/kernel.bin && echo MB-OK` (if grub-file present) or QEMU boots without "no multiboot header".

#### Task 2.2: Makefile + toolchain.mk
- **ACTION**: Top-level `kernels/x86_64/Makefile` and `kernel/arch/x86_64/toolchain.mk`.
- **IMPLEMENT**: `toolchain.mk` sets `CC ?= x86_64-elf-gcc` (overridable to `x86_64-linux-gnu-gcc`), `AS=nasm`, `LD ?= $(CC)`, `CFLAGS=-ffreestanding -mno-red-zone -fno-exceptions -mcmodel=kernel -Wall -Wextra -std=c11 -Ikernel/include`. Makefile: `all: build/kernel.bin`; compile C + assemble `.S` (use `cc -c` for `.S`, `nasm -f elf64` only if a `.asm` exists); link with `linker.ld -nostdlib`. Output to `build/`.
- **MIRROR**: flags from `arch_registry.py:61` and `architecture.md:191-207`.
- **GOTCHA**: `build_validator` runs `make -C <ws> all`; the default target/`all` must produce `build/kernel.bin` exactly (path hardcoded in `test_validator.py:67`).
- **VALIDATE**: `make -C kernels/x86_64` exits 0; `build/kernel.bin` exists.

#### Task 2.3: Boot trampoline, serial, libk, kernel_main
- **ACTION**: 32→64-bit `boot.S`, `serial_16550.c`, `kprintf.c`/`string.c`, `io.h`, `boot_info.h`, `kernel_main.c`.
- **IMPLEMENT**: `boot.S` sets up a 64-bit GDT + identity-mapped PML4, enables PAE+LME+paging, far-jumps to long mode, calls `kernel_main`. `serial_16550.c` inits COM1 (`0x3F8`) and exposes `serial_putc`. `kprintf` formats to serial. `kernel_main` prints the markers in order:
  `AUTON Kernel booting` → `[BOOT] Multiboot magic valid` → `[BOOT] Long mode enabled` → `[BOOT] 64-bit GDT loaded` → `[BOOT] Interrupts initialized` → `[DRV] Serial 16550 initialized` → (Phase 4 SLM markers) → `[BOOT] OK`.
- **MIRROR**: `KERNEL_C_STYLE`; struct defs from `boot.md`; HAL call convention from `architecture.md:47-54`.
- **GOTCHA**: red-zone must be disabled (`-mno-red-zone`) for kernel code; `_start` must be 32-bit until long mode is on. Keep `.code32`/`.code64` sections correct.
- **VALIDATE**: `qemu-system-x86_64 -kernel build/kernel.bin -serial stdio -display none -no-reboot -m 128M` prints all expected markers and `[BOOT] OK` without triple-faulting.

#### Task 2.4: Acceptance runner + marker alignment
- **ACTION**: Add a `__main__` runner to `acceptance_tests.py` and align the x86 boot marker to Multiboot v1.
- **IMPLEMENT**: `argparse --arch`; build via `make`, boot via QEMU (reuse `TestValidator`), match each `AcceptanceTest.expected_serial_patterns` against captured serial, print `subsystem: pass/total`. Change `BOOT_TESTS_X86_64` marker `r"\[BOOT\] Multiboot2 magic valid"` → `r"\[BOOT\] Multiboot magic valid"` (matches QEMU `-kernel` path).
- **MIRROR**: `TestValidator.run_tests` + `_parse_test_output` (`test_validator.py:65-141`).
- **GOTCHA**: don't break the existing acceptance-test unit tests — update any test asserting the old marker string.
- **VALIDATE**: `docker compose run acceptance` → `boot: 5/5 drivers: 2/2 ... ALL PASS` (slm/integration pass after Phase 4).

### Phase 3 — Rust tools + validator wiring

#### Task 3.1: Implement kernel-builder
- **ACTION**: Replace the stub to run the real build.
- **IMPLEMENT**: spawn `make -C <workspace> [clean] all` with `ARCH=<arch>`, stream output via `tracing`, copy `<workspace>/build/kernel.bin` to `--output`, exit non-zero on failure.
- **MIRROR**: `RUST_CLI` pattern (`kernel-builder/src/main.rs:5-34`); rust error handling rules (anyhow `.context`).
- **VALIDATE**: `cargo test -p kernel-builder` (existing `tests/test_build_commands.rs` etc.) passes; `kernel-builder -w kernels/x86_64` builds.

#### Task 3.2: Implement test-runner
- **ACTION**: QEMU launch + serial capture + marker parse, mirroring the Python `TestValidator`.
- **IMPLEMENT**: build QEMU args from arch, `-kernel <img> -serial stdio -display none -no-reboot`, timeout via tokio, parse `[TEST] name: PASS/FAIL` and `[BOOT] OK`, emit JSON summary.
- **MIRROR**: `test_validator.py:77-141` logic; `RUST_CLI` pattern.
- **VALIDATE**: `cargo test -p test-runner` (existing `test_qemu_launch.rs`, `test_serial_capture.rs`, `test_timeout_handling.rs`) passes.

#### Task 3.3: Implement diff-validator
- **ACTION**: Parse unified diffs and apply validation rules (the existing `tests/test_diff_parsing.rs`, `test_validation_rules.rs` define the contract).
- **IMPLEMENT**: read existing tests first; implement to satisfy them (parse hunks, enforce rules they assert).
- **MIRROR**: `RUST_CLI`.
- **VALIDATE**: `cargo test -p diff-validator` passes.

#### Task 3.4: Wire validators into the engine loop
- **ACTION**: Instantiate `BuildValidator`, `TestValidator`, `CompositionValidator` in `OrchestrationEngine.__init__`; call them in Phase 4 final integration (and optionally after each merge) instead of relying solely on agent shell calls.
- **IMPLEMENT**: import from `orchestrator.validation`; construct with `workspace_path=self.workspace.path` and `arch_profile=self.arch_profile`; in `run()` after `full_integration_check`, run `await build_validator.build("all")` then `await test_validator.run_tests()`; gate the returned `success` on real build+test results; run composition check when `config[validation][composition_checks]`.
- **MIRROR**: `ASYNC_SUBPROCESS`; existing `engine.run` structure (`engine.py:327-345`).
- **GOTCHA**: don't double-build under agents if cost matters — guard with the `[validation]` config; keep timeouts from `auton.toml` (`build_timeout`, `test_timeout`).
- **VALIDATE**: add `agent/tests/integration/test_engine_validation_wiring.py` (mirror `test_kernel_workflow.py` fixture) asserting validators are constructed and invoked (patch subprocess). `pytest -q` green.

### Phase 4 — In-kernel rule-engine SLM (reaches `[SLM] Ready` + integration test)

#### Task 4.1: PCI enumeration
- **ACTION**: `dev/pci.c` scans bus 0 via config ports.
- **IMPLEMENT**: `inl/outl` to `0xCF8/0xCFC`, enumerate device/vendor IDs, print `[DEV] PCI scan: N devices found`.
- **MIRROR**: `architecture.md:78-87`; `io.h` from Task 2.3.
- **VALIDATE**: under QEMU default machine, prints ≥1 device (e1000/virtio present).

#### Task 4.2: Rule-engine SLM + knowledge table
- **ACTION**: `slm/engine/slm.c`, `slm/rules/rules.c`, `slm/knowledge/pci_ids.c`.
- **IMPLEMENT**: `slm_init()` → `[SLM] Rule engine initialized`; intent classifier (keyword match for `HARDWARE_IDENTIFY`/`DRIVER_SELECT`); `slm_driver_select(vendor,device)` looks up `pci_ids` table (e.g. `8086:100e → "e1000"`); `kernel_main` calls a discovery pass → `[SLM] Hardware scan complete: N devices`, `[SLM] Loaded driver: e1000`, then `[SLM] Ready`.
- **MIRROR**: intent API in `subsystems/slm.md`; `KERNEL_C_STYLE`.
- **GOTCHA**: the `full_boot_to_slm` integration test also expects `[MM] PMM initialized`, `[SCHED] Scheduler initialized`, `[SLM] ... engine initialized`. Either emit minimal stub markers for PMM/SCHED in `kernel_main` (honest: a trivial bump allocator + a no-op scheduler init that genuinely runs) or scope the integration test to the seed's real markers. Prefer emitting real-but-minimal PMM/sched init so the marker reflects actual code.
- **VALIDATE**: `docker compose run acceptance` → `slm: 2/2`, `integration: full_boot_to_slm PASS`.

### Phase 5 — SLM training pipeline (host-side; not required to boot)

#### Task 5.1–5.3: Implement dataset/tokenizer/train/eval/quantize/export
- **ACTION**: Replace the 9 `TODO` SLM files with working minimal implementations.
- **IMPLEMENT**: `dataset_builder.py` collect/analyze/split over the JSON schema in README (`text`/`intent`/`context`); `tokenizer.py` train a small BPE (use `tokenizers`); `train.py` train `SLM/configs/tiny_10M.yaml` for a few steps on a tiny synthetic set with checkpointing; `evaluate.py` perplexity/accuracy; `quantize.py` INT8 via bitsandbytes; `export_gguf.py`/`export_onnx.py` real exports; implement `metrics.py`/`gguf_validator.py`.
- **MIRROR**: existing `SLM/tests/*` define the function contracts — read them first and implement to pass.
- **GOTCHA**: keep configs tiny so CI runs in minutes on CPU; gate heavy deps so the image stays usable. These do **not** block the bootable OS (rule engine is in-kernel).
- **VALIDATE**: `docker compose run test` includes `pytest SLM/tests -q` green; `python SLM/scripts/train.py --config SLM/configs/tiny_10M.yaml --dataset <tiny> --max-steps 5` produces a checkpoint.

### Phase 6 — Release + docs

#### Task 6.1: ISO builder
- **ACTION**: `scripts/build-iso.sh` wraps `grub-mkrescue` to emit `auton-x86_64-<version>.iso`.
- **IMPLEMENT**: stage `kernel.bin` + `grub.cfg` (multiboot), `grub-mkrescue -o dist/auton-x86_64-$VER.iso iso_root`.
- **GOTCHA**: this path uses GRUB (multiboot/multiboot2) — distinct from the QEMU `-kernel` test path. Add a multiboot2 header here if booting the ISO via GRUB2.
- **VALIDATE**: `qemu-system-x86_64 -cdrom dist/auton-x86_64-*.iso -serial stdio -display none` boots to `[BOOT] OK`.

#### Task 6.2: Docs truth-up
- **ACTION**: Update `README.md` to document the verified `docker compose run os` / `acceptance` / `orchestrate` quickstart and mark neural-SLM/other-arches as roadmap, not shipped.
- **VALIDATE**: README commands copy-paste run successfully in the Docker image.

---

## Testing Strategy

### Unit / Integration Tests
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `test_engine_validation_wiring` (new) | engine in kernel mode, patched subprocess | BuildValidator+TestValidator constructed & awaited | wiring regression |
| `kernel-builder` cargo tests (exist) | seeded workspace | build commands correct, artifact copied | missing Makefile |
| `test-runner` cargo tests (exist) | fake serial stream | parses PASS/FAIL, honors timeout | QEMU hang |
| `diff-validator` cargo tests (exist) | unified diff samples | validation verdicts | malformed diff |
| acceptance runner | built `kernel.bin` | all marker groups PASS | kernel triple-fault → timeout |
| SLM `pytest SLM/tests` (exist) | tiny config/dataset | train/eval/export succeed | empty dataset |

### Edge Cases Checklist
- [ ] No Makefile in workspace → `BuildResult(success=False, "No Makefile found")` (already handled — keep)
- [ ] QEMU missing → friendly error (already handled in `test_validator.py:121-125`)
- [ ] Kernel hangs → QEMU timeout path returns failure, not deadlock
- [ ] Cross-compiler absent → Dockerfile build fails loudly (not at runtime)
- [ ] `-kernel` multiboot header missing → caught by `grub-file --is-x86-multiboot` in CI
- [ ] No `ANTHROPIC_API_KEY` for `orchestrate` → existing CLI fail-fast (`cli.py:96-108`)

---

## Validation Commands

### Static Analysis
```bash
cd agent && ruff check orchestrator && cd tools && cargo clippy -- -D warnings
```
EXPECT: zero errors/warnings

### Unit Tests
```bash
cd agent && pytest tests/unit -q
cd agent/tools && cargo test
```
EXPECT: all pass

### Full Suite (in Docker)
```bash
docker compose run test
```
EXPECT: Python unit+integration, Rust, and SLM tests all green

### Boot the OS (the headline deliverable)
```bash
docker compose run os
```
EXPECT: serial shows `AUTON Kernel booting` … `[DRV] Serial 16550 initialized` … `[SLM] Ready` … `[BOOT] OK`

### Acceptance
```bash
docker compose run acceptance
```
EXPECT: `boot/drivers/slm/integration` groups report ALL PASS for x86_64

### Manual Validation
- [ ] `docker build -t auton .` from clean checkout succeeds
- [ ] `docker compose run os` boots to `[BOOT] OK` with no triple-fault
- [ ] `docker compose run acceptance` passes the boot+drivers+slm+full_boot_to_slm tests
- [ ] `docker compose run orchestrate "Add a VGA text driver"` runs agents against the seeded `kernels/x86_64` tree and produces a buildable branch
- [ ] `scripts/build-iso.sh` ISO boots via `-cdrom`

---

## Acceptance Criteria
- [ ] `docker compose run os` boots the seed kernel in QEMU and reaches `[BOOT] OK` (**MVP: local OS on Docker**)
- [ ] `docker compose run acceptance` passes boot, drivers, slm, and `full_boot_to_slm`
- [ ] Rust `kernel-builder`/`test-runner`/`diff-validator` implemented; `cargo test` green
- [ ] Validators wired into `engine.py` and exercised by a new integration test
- [ ] In-kernel rule-engine SLM reaches `[SLM] Ready`
- [ ] SLM training scripts run end-to-end on the tiny config; `SLM/tests` green
- [ ] README quickstart commands are real and verified

## Completion Checklist
- [ ] Code follows discovered patterns (dataclass results, `%`-logging, async subprocess, clap/anyhow, Linux C style)
- [ ] Error handling matches codebase style (FileNotFound/Timeout branches, anyhow context)
- [ ] No hardcoded secrets; `ANTHROPIC_API_KEY` via env
- [ ] Tests follow existing pytest/cargo patterns
- [ ] No `.DS_Store` / build artifacts committed
- [ ] Docs updated to match shipped behavior
- [ ] Each phase committed independently (0→6); MVP (0–2) shippable alone

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Multiboot2 vs QEMU `-kernel` (v1) mismatch | High | OS won't boot via test harness | Use Multiboot v1 header for `-kernel`; align x86 boot marker (Task 2.4); reserve multiboot2 for GRUB/ISO path |
| Building `x86_64-elf-gcc` is slow/fragile | Med | Slow image builds | Prefer `gcc-x86-64-linux-gnu` + freestanding flags; cache toolchain layer |
| Long-mode trampoline triple-faults | Med | Boot hangs | Copy proven OSDev GDT64/PML4 sequence; validate incrementally (32-bit serial print first, then long mode) |
| Validators double-build → cost/time blowup | Med | Slow/expensive runs | Gate via `[validation]` config; reuse `build_timeout`/`test_timeout` |
| Integration test expects PMM/SCHED markers the seed lacks | Med | `full_boot_to_slm` fails | Emit real-but-minimal PMM/sched init markers (Task 4.2 GOTCHA) |
| No KVM in CI containers | Low | Slow QEMU | TCG is fine for a tiny kernel; keep `-display none` |
| SLM training deps heavy (torch) | Low | Large image | Keep tiny configs; consider a separate `slm` compose profile |

## Notes
- **Architecture reality check:** the orchestrator (`agent/orchestrator/**`) is genuinely complete and tested; the gap is entirely in *outputs* (kernel, build system, Docker, Rust tools, SLM scripts) and one wiring bug (validators unused by `engine.py`; workspace path mismatch). This plan closes exactly those gaps.
- **Why seed instead of pure agent generation:** "get a local OS running on Docker" must be deterministic and verifiable. A committed seed that boots gives a reproducible baseline *and* a buildable scaffold the agents extend — which matches the architecture doc's "Directory Structure (generated by agents)" by pre-creating the tree shape and letting agents fill subsystems.
- **Source-of-truth contracts** the seed must honor are non-negotiable strings: the QEMU command and `build/kernel.bin` path (`test_validator.py`), the `Makefile`-at-workspace-root expectation (`build_validator.py`), and the serial markers (`acceptance_tests.py`). Everything in Phase 2 is derived from those three files.
- Phases are ordered so **0–2 alone satisfy the user's headline ask**; 3–6 "finish the codebase."
```
