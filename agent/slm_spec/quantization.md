# Model Quantization Specification

## Objective

Compress trained SLMs from FP16 to INT4/INT8 precision to reduce memory footprint and improve inference speed, while maintaining accuracy degradation < 2%.

## Why Quantization?

**Benefits**:
- **4x smaller** models (INT4 vs FP16)
- **2-4x faster** inference (integer ops)
- **Fits in kernel memory** (embedded models < 100MB)
- **Lower bandwidth** requirements

**Trade-offs**:
- Slight accuracy loss (typically 1-2%)
- Quantization overhead (calibration)
- Format conversion complexity

## Quantization Targets

### Memory Savings

| Model Size | FP16 | INT8 | INT4 |
|-----------|------|------|------|
| Tiny (10M) | 20MB | 10MB | 5MB |
| Small (50M) | 100MB | 50MB | 25MB |
| Medium (150M) | 300MB | 150MB | 75MB |
| Large (500M) | 1GB | 500MB | 250MB |

### Quantization Strategy by Size

| Model | Recommended Precision | Rationale |
|-------|----------------------|-----------|
| Tiny | INT8 | Already small, INT4 too lossy |
| Small | INT4 | Good balance, fits embedded |
| Medium | INT4 | Critical for kernel integration |
| Large | INT4 or INT8 | INT4 preferred for size |

## Quantization Methods

### 1. Post-Training Quantization (PTQ)

Quantize after training completes:
- **Faster** (no retraining)
- **Simpler** implementation
- **Calibration** required (representative data)

**Recommended for**: All AUTON models

### 2. Quantization-Aware Training (QAT)

Train with quantization simulation:
- **Better accuracy** preservation
- **Slower** (full retraining)
- **More complex** implementation

**Use case**: If PTQ accuracy loss > 2%, retry with QAT

## Quantization Algorithms

### GPTQ (Generative Pre-trained Transformer Quantization)

**How it works**:
- Layer-wise quantization
- Optimal Brain Quantization (OBQ) for weight selection
- Hessian-based importance weighting

**Pros**:
- State-of-the-art accuracy
- Fast inference
- Widely supported

**Cons**:
- Requires calibration data
- Memory-intensive during quantization

**Implementation**:
```python
from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

# Configure quantization
quantize_config = BaseQuantizeConfig(
    bits=4,  # INT4
    group_size=128,  # Quantize in groups of 128
    desc_act=False,  # Activation order
)

# Load model
model = AutoGPTQForCausalLM.from_pretrained(
    checkpoint_path,
    quantize_config=quantize_config,
)

# Calibrate with representative data
model.quantize(calibration_dataset)

# Save quantized model
model.save_quantized(output_path)
```

### AWQ (Activation-aware Weight Quantization)

**How it works**:
- Identifies salient weights (important for activations)
- Protects salient weights from quantization
- Scales remaining weights

**Pros**:
- Better accuracy than naive quantization
- Faster than GPTQ
- Less calibration data needed

**Cons**:
- Slightly lower accuracy than GPTQ
- Requires activation statistics

**Implementation**:
```python
from awq import AutoAWQForCausalLM

# Load model
model = AutoAWQForCausalLM.from_pretrained(checkpoint_path)

# Quantize (4-bit)
model.quantize(
    calibration_dataset,
    quant_config={"zero_point": True, "q_group_size": 128},
)

# Save
model.save_quantized(output_path)
```

### Naive Quantization (Baseline)

Simple linear quantization:
- Map FP16 range to INT4/INT8 range
- No calibration, no optimization

**Use case**: Quick baseline to compare against

## Calibration Dataset

### Requirements

**Size**:
- 512-1024 samples (representative subset)
- Total tokens: ~100K-500K

**Content**:
- Should match training data distribution
- Include diverse examples (hardware, commands, docs)

**Source**:
- Use validation set (not train or test)
- Or curate separate calibration set

### Example

```python
# Load calibration data
calibration_texts = load_calibration_dataset("SLM/datasets/processed/val.bin", max_samples=512)

# Tokenize
calibration_dataset = [tokenizer(text) for text in calibration_texts]
```

## Quantization Pipeline

### Step 1: Select Checkpoint

```python
# Best checkpoint from evaluation
checkpoint_path = "SLM/models/checkpoints/medium_150M/step_100000"
```

### Step 2: Load and Quantize

```python
from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

# Config
quantize_config = BaseQuantizeConfig(
    bits=4,
    group_size=128,
    desc_act=False,
)

# Load
model = AutoGPTQForCausalLM.from_pretrained(checkpoint_path, quantize_config=quantize_config)

# Quantize with calibration
model.quantize(calibration_dataset)

# Save
output_path = "SLM/models/quantized/medium_150M_int4"
model.save_quantized(output_path)
```

### Step 3: Validate Quantized Model

```python
# Load quantized model
quantized_model = AutoGPTQForCausalLM.from_quantized(output_path)

# Compute metrics
quantized_perplexity = compute_perplexity(quantized_model, test_dataset)
original_perplexity = 18.5  # From evaluation

# Check accuracy degradation
accuracy_loss = (quantized_perplexity - original_perplexity) / original_perplexity
print(f"Accuracy loss: {accuracy_loss:.2%}")

# Must be < 2%
assert accuracy_loss < 0.02, f"Accuracy loss {accuracy_loss:.2%} exceeds threshold"
```

### Step 4: Benchmark Speed

```python
import time

# Measure inference speed
input_ids = tokenizer("PCI device 8086:10d3 is", return_tensors="pt").input_ids
start = time.time()
output = quantized_model.generate(input_ids, max_length=100)
elapsed = time.time() - start

tokens_per_sec = 100 / elapsed
print(f"Quantized inference speed: {tokens_per_sec:.1f} tokens/sec")

# Should be faster than FP16
```

## Validation Criteria

### Acceptance Criteria

A quantized model is accepted if:

✅ **Accuracy degradation < 2%**
- Perplexity increase < 2%
- OR OS benchmark accuracy drop < 2 percentage points

✅ **Inference speed improves**
- At least 1.5x faster than FP16
- Preferably 2-3x faster

✅ **Memory usage reduced**
- INT4: ~4x smaller than FP16
- INT8: ~2x smaller than FP16

✅ **No generation failures**
- Generates coherent text
- No nonsense outputs
- No repetition loops

### Failure Handling

**If accuracy loss > 2%**:

**Option 1**: Retry with INT8 instead of INT4
```python
quantize_config = BaseQuantizeConfig(bits=8, ...)
```

**Option 2**: Retry with more calibration data
```python
calibration_dataset = load_calibration_dataset(..., max_samples=2048)
```

**Option 3**: Use QAT (Quantization-Aware Training)
- Retrain model with quantization simulation
- Slower but better accuracy

**Option 4**: Select different checkpoint
- Try earlier/later training checkpoint
- May have better quantization properties

## Mixed Precision Quantization

For critical layers, use higher precision:

```python
# Example: Keep attention weights in INT8, FFN in INT4
quantize_config = BaseQuantizeConfig(
    bits=4,
    group_size=128,
    desc_act=False,
    modules_to_not_convert=["self_attn"],  # Keep attention in INT8
)
```

**Trade-off**: Slightly larger model, better accuracy

## Agent Tools

QuantizationAgent has access to:

**`quantize_model(checkpoint_path, output_path, quant_type, calibration_dataset)`**
- Quantizes model to INT4/INT8
- Uses GPTQ or AWQ
- Returns quantized model path

**`validate_quantization(original_path, quantized_path, test_dataset)`**
- Compares original vs quantized accuracy
- Computes perplexity difference
- Returns validation report

**`compare_outputs(original_model, quantized_model, prompts)`**
- Generates text from both models
- Compares outputs for quality
- Returns comparison report

## Output Artifacts

After quantization:

```
SLM/models/quantized/
├── medium_150M_int4/
│   ├── model.safetensors (quantized weights)
│   ├── config.json
│   ├── quantization_config.json (GPTQ params)
│   └── validation_report.json (accuracy, speed)
├── medium_150M_int8/  (if INT4 fails)
│   └── ...
└── quantization_summary.json (comparison of all quantized models)
```

## Integration with VibeTensor Loop

```
EvaluationAgent → selects best checkpoint
        ↓
QuantizationAgent → quantizes to INT4
        ↓
    accuracy loss < 2%? → YES → approve
        ↓ NO
    try INT8 or more calibration data
        ↓
    still fails? → report to ReviewerAgent
        ↓
ReviewerAgent → recommend QAT or different checkpoint
```

## Performance Benchmarks

### Expected Speed Improvements

| Hardware | FP16 (tok/s) | INT8 (tok/s) | INT4 (tok/s) |
|----------|--------------|--------------|--------------|
| x86_64 CPU (AVX2) | 20 | 40 | 60 |
| ARM Cortex-A72 | 5 | 10 | 15 |
| RISC-V U74 | 3 | 6 | 9 |

**Note**: Actual speed depends on implementation (llama.cpp optimizations)

## Related Specifications

- [evaluation.md](evaluation.md) - Evaluation produces checkpoints to quantize
- [export.md](export.md) - Export quantized models to GGUF/ONNX
- [integration.md](integration.md) - Kernel integration of quantized models
