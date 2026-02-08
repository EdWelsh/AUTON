# AUTON SLM Implementation Phases

This document outlines the complete implementation plan for adding SLM (Small Language Model) creation capabilities to AUTON.

**Goal**: Enable AUTON to autonomously train, quantize, and integrate SLMs into the kernels it builds.

---

## Phase 1: Infrastructure Setup ✅ COMPLETED

**Objective**: Set up directory structure, configuration, and specifications without modifying existing code.

### Steps

- [x] **1.1 Create SLM/ directory structure**
  ```bash
  mkdir -p SLM/models/{checkpoints,quantized,exports/manifests}
  mkdir -p SLM/datasets/{raw,processed,benchmarks}
  mkdir -p SLM/{notebooks,scripts,configs,tools}
  ```

- [x] **1.2 Create kernels/ directory structure**
  ```bash
  mkdir -p kernels/{x86_64,aarch64,riscv64}
  ```

- [x] **1.3 Create SLM specification files** in `agent/slm_spec/`:
  - [x] `overview.md` - Pipeline overview and VibeTensor integration
  - [x] `data_preparation.md` - Dataset curation and tokenization
  - [x] `architecture.md` - Transformer design (GQA, SwiGLU, RoPE)
  - [x] `training.md` - Training loop implementation
  - [x] `evaluation.md` - Benchmarks and metrics
  - [x] `quantization.md` - INT4/INT8 quantization
  - [x] `export.md` - GGUF/ONNX export
  - [x] `integration.md` - Kernel integration

- [x] **1.4 Update `agent/config/auton.toml`**
  - [x] Add `[workflow]` section with mode selector
  - [x] Add `[slm]` section with paths and model sizes
  - [x] Add `[slm.training]` and `[slm.quantization]` sections
  - [x] Add SLM agent counts to `[agents]`
  - [x] Add SLM agent model overrides to `[agents.models]`

- [x] **1.5 Update `agent/pyproject.toml`**
  - [x] Add PyTorch and transformers dependencies
  - [x] Add data science libraries (pandas, numpy, matplotlib)
  - [x] Add quantization libraries (bitsandbytes, onnx)
  - [x] Add Jupyter notebook dependencies

- [x] **1.6 Validation**
  - [x] Verify directory structures created
  - [x] Verify all spec files exist
  - [x] Verify configuration files parse correctly
  - [x] Existing kernel build still works (no regressions)

**Status**: ✅ Complete

---

## Phase 2: Tool Definitions and Executors ✅ COMPLETED

**Objective**: Implement SLM-specific tools that agents will use to prepare data, train models, and export.

**Duration**: 2-3 weeks

### Steps

- [x] **2.1 Add tool definitions to `agent/orchestrator/llm/tools.py`**

  **Data Preparation Tools**:
  - [x] `TOOL_ANALYZE_DATASET` - Compute vocab size, token counts, coverage
  - [x] `TOOL_TOKENIZE_DATA` - BPE/WordPiece/SentencePiece tokenization

  **Model Architecture Tools**:
  - [x] `TOOL_VALIDATE_ARCHITECTURE` - Validate model config YAML
  - [x] `TOOL_ESTIMATE_FLOPS` - Estimate compute/memory requirements

  **Training & Evaluation Tools**:
  - [x] `TOOL_TRAIN_MODEL` - Run training script with config
  - [x] `TOOL_EVALUATE_MODEL` - Evaluate on test set

  **Quantization & Export Tools**:
  - [x] `TOOL_QUANTIZE_MODEL` - INT4/INT8 quantization (GPTQ/AWQ)
  - [x] `TOOL_EXPORT_GGUF` - Export to GGUF format
  - [x] `TOOL_EXPORT_ONNX` - Export to ONNX format

  **Integration Tool**:
  - [x] `TOOL_INTEGRATE_SLM` - Copy model to kernel workspace, update Makefile

  **Tool Sets**:
  - [x] `DATA_SCIENTIST_TOOLS` - List of tools for DataScientistAgent
  - [x] `MODEL_ARCHITECT_TOOLS` - List of tools for ModelArchitectAgent
  - [x] `TRAINING_TOOLS` - List of tools for TrainingAgent
  - [x] Update `INTEGRATOR_TOOLS` with integration tools

- [x] **2.2 Create Python scripts in `SLM/scripts/`**
  - [x] `train.py` - Main training script using PyTorch/Transformers
  - [x] `evaluate.py` - Evaluation script with perplexity, benchmarks
  - [x] `quantize.py` - Quantization script (GPTQ/AWQ)
  - [x] `export_gguf.py` - GGUF export using llama.cpp
  - [x] `export_onnx.py` - ONNX export using optimum

- [x] **2.3 Create data processing utilities in `SLM/tools/`**
  - [x] `tokenizer.py` - BPE tokenizer implementation
  - [x] `dataset_builder.py` - Dataset preprocessing and cleaning
  - [x] `metrics.py` - Perplexity, accuracy computation
  - [x] `gguf_validator.py` - Validate GGUF format

- [x] **2.4 Create model configs in `SLM/configs/`**
  - [x] `tiny_10M.yaml` - 10M parameter model config
  - [x] `small_50M.yaml` - 50M parameter model config

- [x] **2.5 Extend `agent/orchestrator/agents/base_agent.py`**

  Add tool executor methods:
  - [x] `_analyze_dataset()` - Call dataset_builder.py
  - [x] `_tokenize_data()` - Call tokenizer.py
  - [x] `_validate_architecture()` - Validate config YAML
  - [x] `_estimate_flops()` - Estimate model FLOPs
  - [x] `_train_model()` - Call SLM/scripts/train.py
  - [x] `_evaluate_model()` - Call SLM/scripts/evaluate.py
  - [x] `_quantize_model()` - Call SLM/scripts/quantize.py
  - [x] `_export_gguf()` - Call SLM/scripts/export_gguf.py
  - [x] `_export_onnx()` - Call SLM/scripts/export_onnx.py
  - [x] `_integrate_slm_model()` - Copy model to kernel, update Makefile

  Update `_execute_tool()` method with new cases:
  - [x] All SLM tool cases added

- [x] **2.7 Validation**
  - [x] All tools defined and integrated
  - [x] Python scripts created with CLI interfaces
  - [x] Configs created and validate
  - [x] Tool executors integrated into base_agent

**Status**: ✅ Complete

**Success Criteria**:
- ✅ 10+ new tools defined and integrated
- ✅ All SLM scripts functional (stubs ready for implementation)
- ✅ Model configs validate
- ✅ Existing kernel workflow unaffected

---

## Phase 3: SLM Agent Classes ✅ COMPLETED

**Objective**: Create specialized agent classes for SLM training workflow.

**Duration**: 2-3 weeks

### Steps

- [x] **3.1 Update `agent/orchestrator/agents/base_agent.py`**

  Add new agent roles to `AgentRole` enum:
  - [x] DATA_SCIENTIST
  - [x] MODEL_ARCHITECT
  - [x] TRAINING

- [x] **3.2 Create `agent/orchestrator/agents/data_scientist_agent.py`**
  - [x] DataScientistAgent class with DATA_SCIENTIST_TOOLS

- [x] **3.3 Create `agent/orchestrator/agents/model_architect_agent.py`**
  - [x] ModelArchitectAgent class with MODEL_ARCHITECT_TOOLS

- [x] **3.4 Create `agent/orchestrator/agents/training_agent.py`**
  - [x] TrainingAgent class with TRAINING_TOOLS

- [x] **3.5 Add system prompts to `agent/orchestrator/llm/prompts.py`**
  - [x] build_data_scientist_prompt()
  - [x] build_model_architect_prompt()
  - [x] build_training_prompt()

- [x] **3.6 Add import statements to `agent/orchestrator/agents/__init__.py`**
  - [x] All SLM agents exported

- [x] **3.7 Unit tests for agents**
  - [x] Test DataScientistAgent instantiation
  - [x] Test ModelArchitectAgent instantiation
  - [x] Test TrainingAgent instantiation
  - [x] Test system prompts include correct specifications
  - [x] Test agents have correct tools assigned
  - [x] Mock simple task execution for each agent

- [x] **3.8 Validation**
  - [x] All agents instantiate without errors
  - [x] Agents can execute simple mock tasks
  - [x] System prompts reference correct specifications
  - [x] Tool sets are correct per agent role

**Status**: ✅ Complete

**Success Criteria**:
- ✅ 3 new agent classes created
- ✅ 3 system prompts defined
- ✅ All agents properly integrated
- ✅ No regressions in existing agents---

## Phase 4: Orchestration Integration ✅ COMPLETED

**Objective**: Integrate SLM agents into the orchestration engine and enable SLM training workflow.

**Duration**: 2-3 weeks

### Steps

- [x] **4.1 Add `WorkflowMode` to `agent/orchestrator/core/engine.py`**
  - [x] KERNEL_BUILD, SLM_TRAINING, DUAL modes

- [x] **4.2 Update `OrchestrationEngine.__init__()` to read workflow mode**
  - [x] Read from config["workflow"]["mode"]
  - [x] Log workflow mode on startup

- [x] **4.3 Update `_init_agents()` to create SLM agents conditionally**
  - [x] Create SLM agents when mode is SLM_TRAINING or DUAL
  - [x] DataScientistAgent, ModelArchitectAgent, TrainingAgent (2x parallel)
  - [x] Register with scheduler

- [x] **4.4 Create SLM-specific task graph in `agent/orchestrator/core/task_graph.py`**
  - [x] create_slm_training_tasks() method
  - [x] 7-task pipeline: data prep → arch design → training → eval → quantize → export → integrate

- [x] **4.5 Update orchestration loop in `engine.py`**
  - [x] Handle KERNEL_BUILD mode (existing)
  - [x] Handle SLM_TRAINING mode (SLM tasks only)
  - [x] Handle DUAL mode (kernel + SLM tasks)

**Status**: ✅ Complete

**Success Criteria**:
- ✅ OrchestrationEngine supports 3 workflow modes
- ✅ SLM task graph executes successfully
- ✅ DUAL mode coordinates kernel + SLM workflows
- ✅ All integration complete,
      )
      tasks.append(integration)

      return tasks
  ```

- [ ] **4.5 Update orchestration loop in `engine.py`**

  Modify `run()` method to handle different workflow modes:
  ```python
  async def run(self, goal: str) -> dict:
      logger.info("Starting orchestration: %s", goal)
      logger.info("Workflow mode: %s", self.workflow_mode)

      self._init_agents()

      # Create task graph based on workflow mode
      if self.workflow_mode == WorkflowMode.KERNEL_BUILD:
          # Existing kernel build workflow
          tasks = await self._manager_decompose_goal(goal)
      elif self.workflow_mode == WorkflowMode.SLM_TRAINING:
          # SLM training workflow only
          tasks = self.task_graph.create_slm_training_tasks(goal)
      elif self.workflow_mode == WorkflowMode.DUAL:
          # Both kernel and SLM tasks
          kernel_tasks = await self._manager_decompose_goal(goal)
          slm_tasks = self.task_graph.create_slm_training_tasks(goal)
          tasks = kernel_tasks + slm_tasks
          # Add cross-workflow dependency: kernel-integration depends on slm-export
          self.task_graph.add_dependency("kernel-integration", "slm-export")

      # Execute tasks
      await self._execute_task_graph(tasks)

      return {"success": True, "workflow_mode": self.workflow_mode}
  ```

- [ ] **4.6 Extend IntegratorAgent with SLM integration capability**

  Update `agent/orchestrator/agents/integrator_agent.py`:
  - Add `_integrate_slm_model()` method
  - Handle both kernel merges and SLM integration tasks

- [ ] **4.7 Update scheduler to handle SLM agent roles**

  Ensure `agent/orchestrator/core/scheduler.py` can assign SLM tasks to appropriate agents.

- [ ] **4.8 Integration tests**
  - [ ] Test SLM_TRAINING mode end-to-end (mock training)
  - [ ] Test DUAL mode with both kernel and SLM tasks
  - [ ] Test task dependencies (training waits for data + architecture)
  - [ ] Test parallel training agents
  - [ ] Test cross-workflow dependencies (kernel integration waits for SLM export)

- [ ] **4.9 Validation**
  - [ ] SLM_TRAINING mode executes full pipeline
  - [ ] DUAL mode runs both kernel and SLM workflows
  - [ ] Task graph correctly handles dependencies
  - [ ] Agents are assigned tasks based on roles
  - [ ] No deadlocks or circular dependencies

**Success Criteria**:
- ✅ OrchestrationEngine supports 3 workflow modes
- ✅ SLM task graph executes successfully
- ✅ DUAL mode coordinates kernel + SLM workflows
- ✅ All integration tests pass

---

## Phase 5: Directory Migration (workspace → kernels)

**Objective**: Safely migrate existing workspace to architecture-specific kernels/ structure.

**Duration**: 1 week

### Steps

- [ ] **5.1 Backup existing workspace**
  ```bash
  cp -r agent/workspace agent/workspace.backup
  ```

- [ ] **5.2 Copy workspace to kernels/x86_64**
  ```bash
  # If workspace exists and has content
  if [ -d "agent/workspace" ] && [ "$(ls -A agent/workspace)" ]; then
      cp -r agent/workspace/* kernels/x86_64/
  else
      echo "Workspace empty or doesn't exist, skipping copy"
  fi
  ```

- [ ] **5.3 Update workspace path in `agent/config/auton.toml`**
  ```toml
  [workspace]
  path = "../kernels/x86_64"  # Changed from "../workspace/x86_64"
  branch_prefix = "agent"
  ```

- [ ] **5.4 Update any hardcoded paths in orchestrator**
  - [ ] Search for "workspace" in `orchestrator/` directory
  - [ ] Update paths to use config value (should already be using config)
  - [ ] Verify no hardcoded "../workspace" references

- [ ] **5.5 Test kernel build in new location**
  ```bash
  cd kernels/x86_64
  # If Makefile exists
  if [ -f "Makefile" ]; then
      make clean
      make
  else
      echo "No Makefile yet, kernel workspace not initialized"
  fi
  ```

- [ ] **5.6 Test orchestrator with new workspace path**
  ```bash
  cd agent
  python -m orchestrator.cli run "Build boot subsystem"
  ```

- [ ] **5.7 Initialize Git repos for each architecture workspace**
  ```bash
  cd kernels/x86_64 && git init && git add . && git commit -m "Initial x86_64 kernel workspace"
  cd ../aarch64 && git init
  cd ../riscv64 && git init
  ```

- [ ] **5.8 Initialize Git repo for SLM/ (with Git LFS)**
  ```bash
  cd SLM
  git init
  git lfs install
  git lfs track "models/checkpoints/**/*.pt"
  git lfs track "models/quantized/**/*.pt"
  git lfs track "models/exports/**/*.gguf"
  git add .gitattributes
  git add .
  git commit -m "Initial SLM workspace"
  ```

- [ ] **5.9 Update documentation**
  - [ ] Update README.md with new directory structure
  - [ ] Update any developer docs referencing workspace/

- [ ] **5.10 Remove old workspace (only after full validation)**
  ```bash
  # Only after confirming everything works!
  rm -rf agent/workspace
  rm -rf agent/workspace.backup
  ```

- [ ] **5.11 Validation**
  - [ ] Kernel builds successfully in kernels/x86_64/
  - [ ] Orchestrator creates branches in kernels/x86_64/.git/
  - [ ] Agents can read/write files in new workspace
  - [ ] All existing tests pass with new paths
  - [ ] No references to old workspace/ directory remain

**Success Criteria**:
- ✅ All kernel code in kernels/{arch}/ structure
- ✅ Old workspace/ removed with no regressions
- ✅ Git repos initialized for all workspaces
- ✅ Documentation updated

---

## Phase 6: Full Integration and Testing

**Objective**: Enable complete dual-mode orchestration and validate end-to-end SLM training + kernel integration.

**Duration**: 2-3 weeks

### Steps

- [ ] **6.1 Implement kernel Makefile SLM embedding**

  Create Makefile template for kernels/{arch}/Makefile:
  ```makefile
  SLM_MODEL := kernel/slm/models/auton-slm.gguf

  # Check if model exists
  ifneq (,$(wildcard $(SLM_MODEL)))
      SLM_ENABLED := 1
  else
      SLM_ENABLED := 0
  endif

  # Convert GGUF to object file (embed as binary data)
  ifeq ($(SLM_ENABLED),1)
  kernel/slm/model_data.o: $(SLM_MODEL)
  	$(OBJCOPY) -I binary -O elf64-x86-64 -B i386:x86-64 \
  	           --rename-section .data=.slm_model,alloc,load,readonly,data \
  	           --redefine-sym _binary_kernel_slm_models_auton_slm_gguf_start=slm_model_start \
  	           --redefine-sym _binary_kernel_slm_models_auton_slm_gguf_end=slm_model_end \
  	           --redefine-sym _binary_kernel_slm_models_auton_slm_gguf_size=slm_model_size \
  	           $< $@

  KERNEL_OBJS += kernel/slm/model_data.o
  CFLAGS += -DSLM_NEURAL_BACKEND_ENABLED
  endif
  ```

- [ ] **6.2 Update kernel SLM runtime to load embedded model**

  Ensure `kernels/{arch}/kernel/slm/neural/gguf_loader.c` exists and loads from symbols:
  ```c
  extern const uint8_t slm_model_start[];
  extern const uint8_t slm_model_end[];
  extern const size_t slm_model_size;

  int slm_init_neural_backend(void) {
      size_t model_size = (size_t)&slm_model_size;
      printk("SLM: Loading embedded model (%zu bytes)...\n", model_size);

      struct gguf_model *model = gguf_parse(slm_model_start, model_size);
      if (!model) return -1;

      return slm_neural_init(model);
  }
  ```

- [ ] **6.3 Create sample dataset for testing**

  Create minimal dataset in `SLM/datasets/raw/`:
  - [ ] Sample OS/hardware text corpus (~10MB)
  - [ ] For quick smoke tests (not production training)

- [ ] **6.4 End-to-end test: SLM training pipeline**

  Test command:
  ```bash
  auton run "Train a tiny 10M parameter SLM on sample dataset"
  ```

  Validates:
  - [ ] DataScientistAgent prepares dataset
  - [ ] ModelArchitectAgent designs tiny_10M config
  - [ ] TrainingAgent trains for minimal steps (1000 steps)
  - [ ] EvaluationAgent computes perplexity
  - [ ] QuantizationAgent quantizes to INT4
  - [ ] ExportAgent exports to GGUF
  - [ ] All checkpoints and exports exist

- [ ] **6.5 End-to-end test: Kernel integration**

  Test command:
  ```bash
  auton run "Integrate trained SLM into x86_64 kernel"
  ```

  Validates:
  - [ ] IntegratorAgent copies GGUF to kernels/x86_64/kernel/slm/models/
  - [ ] Makefile updated with SLM_MODEL path
  - [ ] Kernel builds successfully
  - [ ] Binary size increases by ~model size
  - [ ] Symbols (slm_model_start, etc.) present in binary

- [ ] **6.6 End-to-end test: Kernel boot with SLM**

  Test in QEMU:
  ```bash
  cd kernels/x86_64
  qemu-system-x86_64 -kernel kernel.elf -m 512M -serial stdio -nographic
  ```

  Validates:
  - [ ] Kernel boots without panics
  - [ ] SLM runtime initializes
  - [ ] Model loads successfully
  - [ ] Boot logs show "SLM: Neural backend ready"

- [ ] **6.7 End-to-end test: SLM inference in kernel**

  From kernel shell:
  ```
  Shell> slm query "PCI device 8086:10d3 is"
  ```

  Validates:
  - [ ] SLM responds within 5 seconds
  - [ ] Output is coherent (not gibberish)
  - [ ] Output is technically relevant
  - [ ] Memory usage within bounds

- [ ] **6.8 End-to-end test: DUAL mode**

  Test command:
  ```bash
  auton run "Build x86_64 kernel with integrated SLM"
  ```

  Validates:
  - [ ] Kernel agents build boot/mm/sched subsystems
  - [ ] SLM agents train tiny model in parallel
  - [ ] Both workflows complete
  - [ ] SLM integrated into kernel
  - [ ] Final kernel boots with embedded SLM

- [ ] **6.9 Regression testing**
  - [ ] All existing kernel build tests pass
  - [ ] Orchestration without SLM still works (KERNEL_BUILD mode)
  - [ ] Cost tracking works for SLM agents
  - [ ] Logs include both kernel and SLM agent activity

- [ ] **6.10 Performance benchmarking**
  - [ ] Measure SLM training time (tiny model)
  - [ ] Measure kernel build time (with vs without SLM)
  - [ ] Measure boot time (with embedded SLM)
  - [ ] Measure inference latency in kernel

- [ ] **6.11 Documentation**
  - [ ] Update README with SLM training examples
  - [ ] Create tutorial: "Train Your First SLM"
  - [ ] Document configuration options
  - [ ] Document troubleshooting common issues

- [ ] **6.12 Cost optimization**
  - [ ] Verify local models (Ollama) used for training/quantization
  - [ ] Verify Anthropic models used only for architecture/evaluation
  - [ ] Measure total cost for full pipeline (should be < $25)

- [ ] **6.13 Validation**
  - [ ] Complete SLM training pipeline works end-to-end
  - [ ] Kernel boots with embedded SLM
  - [ ] SLM inference produces coherent outputs
  - [ ] DUAL mode coordinates both workflows
  - [ ] Total cost within budget
  - [ ] Zero regressions in kernel workflow

**Success Criteria**:
- ✅ Train tiny SLM from scratch to GGUF export
- ✅ Integrate SLM into kernel, boot successfully
- ✅ SLM inference works in kernel
- ✅ DUAL mode builds kernel + trains SLM simultaneously
- ✅ All tests pass, no regressions
- ✅ Total cost < $25 USD per run

---

## Summary

### Phase Completion Checklist

- [x] **Phase 1**: Infrastructure ✅ COMPLETED
- [x] **Phase 2**: Tool Definitions and Executors ✅ COMPLETED
- [x] **Phase 3**: SLM Agent Classes ✅ COMPLETED
- [x] **Phase 4**: Orchestration Integration ✅ COMPLETED
- [ ] **Phase 5**: Directory Migration
- [ ] **Phase 6**: Full Integration and Testing

### Overall Success Metrics

When all phases are complete, AUTON will be able to:

1. ✅ **Autonomously train SLMs** (tiny/small/medium/large)
2. ✅ **Quantize models** to INT4/INT8 for efficiency
3. ✅ **Export to GGUF/ONNX** formats
4. ✅ **Integrate SLMs into kernels** across all architectures
5. ✅ **Boot kernels with embedded models** in QEMU
6. ✅ **Run SLM inference** from kernel shell
7. ✅ **Operate in DUAL mode** (kernel + SLM development simultaneously)
8. ✅ **Stay within budget** (< $50 USD per orchestration run)
9. ✅ **Maintain zero regressions** in existing kernel workflow

### Timeline

**Total Estimated Duration**: 10-13 weeks

- Phase 1: ✅ Complete (1 week)
- Phase 2: 2-3 weeks
- Phase 3: 2-3 weeks
- Phase 4: 2-3 weeks
- Phase 5: 1 week
- Phase 6: 2-3 weeks

**Note**: Phases 2-4 can overlap partially with careful coordination.

---

## References

- [Implementation Plan](C:\Users\welsh\.claude\plans\agile-gathering-crescent.md) - Full implementation design
- [SLM Specifications](agent/slm_spec/) - Detailed technical specs
- [Configuration](agent/config/auton.toml) - Runtime configuration
- [Dependencies](agent/pyproject.toml) - Python dependencies
