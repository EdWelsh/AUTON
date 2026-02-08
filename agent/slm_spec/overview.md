# SLM Training Pipeline Overview

## Purpose

This specification defines the complete pipeline for training Small Language Models (SLMs) that will be integrated into the AUTON kernel. These SLMs power the kernel's natural language interface for hardware discovery, driver selection, package management, and system administration.

## Pipeline Stages

The SLM training pipeline consists of 7 stages, each handled by specialized agents:

### 1. Data Preparation (DataScientistAgent)
- Collect and clean training corpora
- Tokenize text using BPE/WordPiece/SentencePiece
- Create train/validation/test splits
- Generate vocabulary files
- **Output**: Tokenized datasets in `SLM/datasets/processed/`

### 2. Architecture Design (ModelArchitectAgent)
- Design transformer architecture configs
- Select hyperparameters (layers, heads, embedding dims)
- Estimate compute and memory requirements
- Validate architecture feasibility
- **Output**: YAML config files in `SLM/configs/`

### 3. Training (TrainingAgent)
- Execute training loops with PyTorch
- Monitor metrics (loss, perplexity)
- Save checkpoints at regular intervals
- Handle training failures and restarts
- **Output**: Model checkpoints in `SLM/models/checkpoints/`

### 4. Review (ReviewerAgent)
- Validate training scripts for correctness
- Check config files for consistency
- Review checkpoint quality
- **Output**: Approval or rejection with feedback

### 5. Evaluation (TesterAgent as EvaluationAgent)
- Run standard benchmarks (perplexity, accuracy)
- Compare multiple trained models
- Select best checkpoint for quantization
- **Output**: Evaluation reports, best model selection

### 6. Quantization (TrainingAgent)
- Quantize models to INT4/INT8 using GPTQ/AWQ
- Validate accuracy degradation < 2%
- **Output**: Quantized models in `SLM/models/quantized/`

### 7. Export (TrainingAgent)
- Export to GGUF format (for llama.cpp)
- Export to ONNX format (alternative)
- Validate format compliance
- Create deployment manifests
- **Output**: Exportable models in `SLM/models/exports/`

### 8. Integration (IntegratorAgent)
- Copy GGUF model to kernel workspace
- Update kernel Makefile to embed model
- Test kernel boot with embedded model
- Validate SLM runtime loads and inferences
- **Output**: Kernel with integrated SLM

## Model Size Tiers

AUTON supports 4 SLM size tiers optimized for different hardware:

| Tier | Parameters | RAM Required | Use Case | Target Hardware |
|------|-----------|--------------|----------|-----------------|
| Tiny | 10M-50M | 64-128 MB | Embedded systems | ARM Cortex-M, low-end RISC-V |
| Small | 50M-150M | 128-256 MB | Resource-constrained | Entry-level x86_64, ARM SBCs |
| Medium | 150M-500M | 256-512 MB | General-purpose | Standard desktops, servers |
| Large | 500M-1B | 512MB-2GB | High-end systems | Workstations, data centers |

## VibeTensor Validation Loop

The SLM training follows the same VibeTensor-style iterative loop as kernel development:

```
Specify → Design → Implement → Validate → Accept/Reject → Iterate
```

**Key validation points:**
- Training: Loss must decrease, no NaN/Inf, checkpoints save successfully
- Evaluation: Perplexity must meet threshold (< 50 for tiny, < 20 for medium+)
- Quantization: Accuracy drop must be < 2%
- Export: Format validation must pass
- Integration: Kernel must boot, SLM runtime must load model, inference must work

## Architecture-Aware Training

SLMs are trained with awareness of the target kernel architecture:

- **x86_64**: Focus on PCI device descriptions, ACPI tables, Intel/AMD driver selection
- **aarch64**: Focus on device tree parsing, ARM peripherals, SoC-specific drivers
- **riscv64**: Focus on OpenSBI, RISC-V CSRs, minimal driver set

The DataScientistAgent curates architecture-specific training data, and the ModelArchitectAgent designs models optimized for each architecture's memory and compute constraints.

## Success Criteria

An SLM training run is considered successful when:

1. ✅ Training completes without NaN/Inf
2. ✅ Validation perplexity meets threshold
3. ✅ Quantization preserves accuracy (< 2% degradation)
4. ✅ Export formats validate successfully
5. ✅ Kernel boots with embedded model
6. ✅ SLM runtime loads model without errors
7. ✅ Inference produces coherent, relevant outputs
8. ✅ Total cost within budget (< $25 USD per training run)

## Related Specifications

- [data_preparation.md](data_preparation.md) - Dataset curation and tokenization
- [architecture.md](architecture.md) - Transformer design and hyperparameters
- [training.md](training.md) - Training loop implementation
- [evaluation.md](evaluation.md) - Benchmarks and metrics
- [quantization.md](quantization.md) - INT4/INT8 quantization
- [export.md](export.md) - GGUF/ONNX export formats
- [integration.md](integration.md) - Kernel integration process
