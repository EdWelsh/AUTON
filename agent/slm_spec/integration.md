# Kernel-SLM Integration Specification

## Objective

Integrate exported SLM models (GGUF format) into AUTON kernel workspaces, enabling the kernel to load and run the SLM runtime with the embedded model for natural language OS interactions.

## Integration Overview

### High-Level Flow

```
SLM Training Pipeline:
  DataScientist → ModelArchitect → Training → Evaluation → Quantization → Export
                                                                              ↓
                                                                       medium_150M.gguf
                                                                              ↓
Kernel Integration Pipeline:                                                  │
  IntegratorAgent ← [Copy model to kernel workspace] ←─────────────────────────┘
        ↓
  [Update kernel Makefile to embed model]
        ↓
  [Build kernel with embedded SLM]
        ↓
  [Test in QEMU: boot + SLM runtime load + inference]
        ↓
  [Validate: outputs coherent, memory within bounds]
        ↓
  [Commit to kernel main branch]
```

## Kernel SLM Runtime Overview

The AUTON kernel includes an SLM runtime (see `kernel_spec/subsystems/slm.md`) with:

**Two Backends**:
1. **Rule Engine** (default, no model file needed)
2. **Neural Backend** (requires GGUF model file)

**Neural Backend Structure**:
```c
// kernel/slm/neural/gguf_loader.c
int slm_load_gguf(const char *model_path);
int slm_neural_inference(const char *prompt, char *output, size_t output_size);
void slm_unload_model(void);
```

**Model Storage**:
```
kernels/x86_64/kernel/slm/models/
└── auton-slm-150M.gguf  (embedded in kernel binary)
```

## Integration Steps

### Step 1: Copy Model to Kernel Workspace

```python
import shutil
from pathlib import Path

def integrate_slm_model(
    model_path: str,  # SLM/models/exports/medium_150M.gguf
    kernel_workspace: str,  # kernels/x86_64
    manifest_path: str,  # SLM/models/exports/manifests/medium_150M.json
):
    """Copy SLM model and manifest to kernel workspace."""

    # Destination paths
    models_dir = Path(kernel_workspace) / "kernel/slm/models"
    models_dir.mkdir(parents=True, exist_ok=True)

    model_dest = models_dir / "auton-slm.gguf"
    manifest_dest = models_dir / "model_manifest.json"

    # Copy files
    shutil.copy(model_path, model_dest)
    shutil.copy(manifest_path, manifest_dest)

    print(f"Copied model to {model_dest}")
    print(f"Copied manifest to {manifest_dest}")

    return model_dest, manifest_dest
```

### Step 2: Update Kernel Makefile

The kernel Makefile needs to embed the GGUF model as a binary blob:

```makefile
# kernels/x86_64/Makefile

SLM_MODEL := kernel/slm/models/auton-slm.gguf

# Check if model exists
ifneq (,$(wildcard $(SLM_MODEL)))
    SLM_ENABLED := 1
else
    SLM_ENABLED := 0
endif

# Convert GGUF to object file (embed as binary data)
kernel/slm/model_data.o: $(SLM_MODEL)
	$(OBJCOPY) -I binary -O elf64-x86-64 -B i386:x86-64 \
	           --rename-section .data=.slm_model,alloc,load,readonly,data \
	           --redefine-sym _binary_kernel_slm_models_auton_slm_gguf_start=slm_model_start \
	           --redefine-sym _binary_kernel_slm_models_auton_slm_gguf_end=slm_model_end \
	           --redefine-sym _binary_kernel_slm_models_auton_slm_gguf_size=slm_model_size \
	           $< $@

# Add to kernel link
ifeq ($(SLM_ENABLED),1)
    KERNEL_OBJS += kernel/slm/model_data.o
    CFLAGS += -DSLM_NEURAL_BACKEND_ENABLED
endif

kernel.elf: $(KERNEL_OBJS)
	$(LD) $(LDFLAGS) -o $@ $(KERNEL_OBJS)
```

**What this does**:
- Converts GGUF file to ELF object file
- Creates symbols: `slm_model_start`, `slm_model_end`, `slm_model_size`
- Links model data into kernel binary
- Sets `SLM_NEURAL_BACKEND_ENABLED` preprocessor flag

### Step 3: Update Kernel SLM Runtime

Kernel code can now access the embedded model:

```c
// kernel/slm/neural/gguf_loader.c

// Symbols from Makefile
extern const uint8_t slm_model_start[];
extern const uint8_t slm_model_end[];
extern const size_t slm_model_size;

int slm_init_neural_backend(void) {
    size_t model_size = (size_t)&slm_model_size;

    printk("SLM: Loading embedded neural model (%zu bytes)...\n", model_size);

    // Parse GGUF from embedded binary
    struct gguf_model *model = gguf_parse(slm_model_start, model_size);
    if (!model) {
        printk("SLM: Failed to parse GGUF model\n");
        return -1;
    }

    // Initialize inference engine
    int ret = slm_neural_init(model);
    if (ret < 0) {
        printk("SLM: Failed to initialize neural backend\n");
        return -1;
    }

    printk("SLM: Neural backend ready (vocab=%d, ctx=%d)\n",
           model->vocab_size, model->context_length);

    return 0;
}
```

### Step 4: Build Kernel

```bash
cd kernels/x86_64
make clean
make

# Expected output:
# CC kernel/slm/neural/gguf_loader.c
# OBJCOPY kernel/slm/model_data.o
# LD kernel.elf
# Kernel size: 2.5 MB (including 75 MB SLM model)
```

**Build Validation**:
- Build completes without errors
- `kernel.elf` size increases by model size (~75MB for medium)
- `slm_model_start` symbol exists in binary: `nm kernel.elf | grep slm_model`

### Step 5: Test in QEMU

```bash
# Boot kernel in QEMU with serial console
qemu-system-x86_64 \
    -kernel kernel.elf \
    -m 512M \
    -serial stdio \
    -nographic \
    -no-reboot

# Expected boot log:
# [  0.001] AUTON kernel booting...
# [  0.023] MM: Initialized page allocator
# [  0.045] SLM: Loading embedded neural model (78643200 bytes)...
# [  0.250] SLM: Neural backend ready (vocab=32000, ctx=2048)
# [  0.251] SLM: Runtime initialized successfully
# [  0.300] Init: System ready
# Shell>
```

### Step 6: Test SLM Inference

From kernel shell, test SLM inference:

```
Shell> slm query "PCI device 8086:10d3 is"
SLM: Inference starting...
SLM: Output: an Intel Gigabit Ethernet controller, specifically the 82574L model...
Shell>
```

**Validation**:
- SLM responds within reasonable time (< 5 seconds)
- Output is coherent and technically accurate
- No kernel panics or errors
- Memory usage within expected bounds

## Validation Criteria

### Build Validation

✅ **Kernel builds successfully** with embedded model
✅ **Binary size** increases by model size (± 5%)
✅ **Symbols present**: `slm_model_start`, `slm_model_end`, `slm_model_size`
✅ **No linker errors** or warnings

### Boot Validation

✅ **Kernel boots** in QEMU without panics
✅ **SLM runtime initializes** and loads model
✅ **No memory errors** during model loading
✅ **Boot time** acceptable (< 10 seconds)

### Inference Validation

✅ **SLM inference works** (generates text)
✅ **Output is coherent** (not gibberish)
✅ **Technical accuracy** (correct device names, commands)
✅ **Response time** reasonable (< 5 sec for 50 tokens)
✅ **Memory usage** within SLM pool (< 150MB for medium model)

### Regression Validation

✅ **Existing kernel tests pass** (boot, MM, scheduler, etc.)
✅ **No conflicts** with other subsystems
✅ **Performance impact** minimal (< 5% boot time increase)

## Memory Management

### SLM Memory Pool

The kernel reserves a dedicated memory pool for SLM:

```c
// kernel/slm/slm_init.c

#define SLM_POOL_SIZE_MB 256

void slm_init(void) {
    // Allocate memory pool for SLM
    void *pool = mm_alloc_pages(SLM_POOL_SIZE_MB << 20);
    if (!pool) {
        panic("SLM: Failed to allocate memory pool");
    }

    slm_set_memory_pool(pool, SLM_POOL_SIZE_MB << 20);
}
```

**Pool Usage**:
- Model weights: ~75MB (medium INT4)
- KV cache: ~50MB (for 2048 context)
- Activation buffers: ~25MB
- Tokenizer data: ~5MB
- **Total**: ~155MB (fits in 256MB pool)

### Multi-Architecture Considerations

Different architectures may have different memory constraints:

| Architecture | Available RAM | Max Model Size | Recommended Model |
|-------------|---------------|----------------|-------------------|
| x86_64 | 512MB+ | 150M (medium) | Medium 150M |
| aarch64 | 256MB+ | 50M (small) | Small 50M |
| riscv64 | 128MB+ | 10M (tiny) | Tiny 10M |

**Dynamic Selection** in Makefile:
```makefile
ifeq ($(ARCH),x86_64)
    SLM_MODEL := models/medium_150M.gguf
else ifeq ($(ARCH),aarch64)
    SLM_MODEL := models/small_50M.gguf
else ifeq ($(ARCH),riscv64)
    SLM_MODEL := models/tiny_10M.gguf
endif
```

## Agent Tools

IntegratorAgent has access to:

**`integrate_slm_model(model_path, kernel_workspace, manifest_path)`**
- Copies model and manifest to kernel workspace
- Updates Makefile with model path
- Returns integration report

**`build_kernel(workspace_path, arch)`**
- Builds kernel with embedded SLM
- Returns build status (success/failure + logs)

**`test_kernel_boot(workspace_path, arch)`**
- Boots kernel in QEMU
- Captures boot logs
- Returns boot status + logs

**`test_slm_inference(workspace_path, arch, test_prompts)`**
- Boots kernel and runs SLM inference tests
- Captures SLM outputs
- Returns inference test results

## Integration Test Suite

### Test 1: Model Embedding
```python
def test_model_embedding():
    # Build kernel
    build_result = build_kernel("kernels/x86_64", "x86_64")
    assert build_result["success"], "Kernel build failed"

    # Check binary size
    kernel_size = Path("kernels/x86_64/kernel.elf").stat().st_size
    expected_size = 2500000 + 78643200  # Base kernel + model
    assert abs(kernel_size - expected_size) / expected_size < 0.05, "Binary size mismatch"

    # Check symbols
    symbols = subprocess.check_output(["nm", "kernels/x86_64/kernel.elf"]).decode()
    assert "slm_model_start" in symbols, "Missing slm_model_start symbol"
```

### Test 2: Boot and SLM Init
```python
def test_boot_and_slm_init():
    # Boot kernel in QEMU
    boot_result = test_kernel_boot("kernels/x86_64", "x86_64")
    assert boot_result["success"], "Kernel boot failed"

    # Check SLM initialization in logs
    logs = boot_result["logs"]
    assert "SLM: Loading embedded neural model" in logs
    assert "SLM: Neural backend ready" in logs
    assert "SLM: Runtime initialized successfully" in logs
```

### Test 3: SLM Inference
```python
def test_slm_inference():
    test_prompts = [
        "PCI device 8086:10d3 is",
        "Install nginx on Debian",
        "List all PCI devices:",
    ]

    # Run inference tests
    inference_result = test_slm_inference("kernels/x86_64", "x86_64", test_prompts)

    for prompt, output in zip(test_prompts, inference_result["outputs"]):
        assert len(output) > 10, f"Output too short for prompt: {prompt}"
        assert not is_gibberish(output), f"Gibberish output for prompt: {prompt}"
        print(f"Prompt: {prompt}\nOutput: {output}\n")
```

## Rollback Strategy

If integration fails:

**Step 1**: Identify failure point
- Build failure: Check Makefile, model path
- Boot failure: Check memory allocation, GGUF parsing
- Inference failure: Check model compatibility, tokenizer

**Step 2**: Rollback options
- Revert to rule engine backend (no model needed)
- Use smaller model (if memory issue)
- Use different quantization (INT8 if INT4 fails)

**Step 3**: Report to orchestrator
- IntegratorAgent reports failure to ManagerAgent
- ManagerAgent assigns ReviewerAgent to analyze
- Recommend fixes or alternative models

## Output Artifacts

After successful integration:

```
kernels/x86_64/
├── kernel/
│   └── slm/
│       ├── models/
│       │   ├── auton-slm.gguf (copied from SLM/)
│       │   └── model_manifest.json
│       ├── neural/
│       │   └── gguf_loader.c (loads embedded model)
│       └── model_data.o (binary blob of GGUF)
├── Makefile (updated with SLM_MODEL path)
├── kernel.elf (kernel with embedded SLM)
└── integration_test_report.json (validation results)
```

## VibeTensor Loop Integration

```
ExportAgent → exports GGUF model
        ↓
IntegratorAgent → integrate into kernel workspace
        ↓
    build passes? → YES
        ↓
    boot passes? → YES
        ↓
    inference works? → YES
        ↓
    commit to main branch → SUCCESS
        ↓
ManagerAgent → marks SLM training task COMPLETE
```

## Success Metrics

A kernel-SLM integration is successful if:

✅ Kernel builds without errors
✅ Kernel boots and initializes SLM runtime
✅ SLM inference produces coherent, accurate outputs
✅ Memory usage within allocated pool
✅ Performance meets targets (inference < 5 sec)
✅ No regressions in existing kernel functionality
✅ Works across target architectures (x86_64, aarch64, riscv64)

## Related Specifications

- [export.md](export.md) - Export produces GGUF models to integrate
- [../kernel_spec/subsystems/slm.md](../kernel_spec/subsystems/slm.md) - Kernel SLM runtime specification
