# Model Architecture Specification

## Objective

Design transformer-based Small Language Model (SLM) architectures optimized for AUTON kernel integration. Models must balance accuracy, inference speed, and memory efficiency.

## Transformer Architecture

### Core Design: Decoder-Only Transformer

AUTON SLMs use decoder-only transformers (GPT-style) for autoregressive text generation:

```
Input tokens → Embedding → [Transformer Blocks] × N → Output logits
```

**Why decoder-only?**
- Kernel needs text generation (device descriptions, commands, explanations)
- Simpler than encoder-decoder models
- Proven architecture (GPT, LLaMA, etc.)

### Transformer Block Structure

Each block contains:

1. **Multi-Head Attention** (or Grouped Query Attention)
2. **Feed-Forward Network** (SwiGLU activation)
3. **Layer Normalization** (RMSNorm)
4. **Residual Connections**

```
x → LayerNorm → Attention → Residual Add
                    ↓
                LayerNorm → FFN → Residual Add → output
```

## Attention Mechanism

### Standard Multi-Head Attention (MHA)

Traditional approach:
- Q, K, V projections for each head
- Each head: `dim_head = d_model / num_heads`
- All heads have separate K, V projections

**Memory cost**: `num_heads * 2 * d_model * d_head` (K, V matrices)

### Grouped Query Attention (GQA) - Recommended

Efficiency improvement over MHA:
- Multiple query heads **share** key/value heads
- Reduces KV cache size during inference
- Minimal accuracy loss (< 1%)

**Formula**:
```
num_kv_heads = num_heads // gqa_ratio
gqa_ratio = 2, 4, or 8 (typical)
```

**Memory cost**: `num_kv_heads * 2 * d_model * d_head` (much smaller!)

**Example** (Medium 150M):
- 12 query heads, 4 KV heads (ratio = 3)
- Saves 66% of KV cache memory
- Critical for kernel integration (limited RAM)

### Multi-Query Attention (MQA)

Extreme case of GQA:
- All query heads share **1** key and **1** value head
- `num_kv_heads = 1`
- Maximum memory savings
- Slight accuracy loss (1-2%)

**Use case**: Tiny models for embedded systems

## Feed-Forward Network

### SwiGLU Activation - Recommended

Modern replacement for ReLU/GELU:

```python
def swiglu_ffn(x, W1, W2, W3):
    return (F.silu(x @ W1) * (x @ W2)) @ W3

# silu(x) = x * sigmoid(x)  (also called Swish)
```

**Why SwiGLU?**
- Better training dynamics
- More parameter-efficient than GELU
- Used in LLaMA, PaLM models

**Parameters**:
- Input: `d_model` (embedding dimension)
- Hidden: `d_ffn = 4 * d_model` (or `8/3 * d_model` for SwiGLU)
- Output: `d_model`

### FFN Dimensions

| Model Size | d_model | d_ffn (SwiGLU) | Parameters (FFN) |
|-----------|---------|----------------|------------------|
| Tiny | 256 | 682 | ~1M per block |
| Small | 512 | 1365 | ~3.5M per block |
| Medium | 768 | 2048 | ~8M per block |
| Large | 1024 | 2730 | ~14M per block |

## Position Encoding

### Rotary Position Embeddings (RoPE) - Recommended

Modern alternative to absolute position embeddings:

**How it works:**
1. No learned position embeddings
2. Rotation applied to Q, K before attention
3. Rotation angle depends on position
4. Enables length extrapolation (train 2048, infer 4096)

**Formula**:
```
RoPE(x, pos) = x * cos(pos * θ) + rotate(x) * sin(pos * θ)
θ = 10000^(-2i/d) for dimension i
```

**Why RoPE?**
- Better than absolute position embeddings
- Supports longer contexts at inference
- Used in LLaMA, GPT-NeoX

### ALiBi (Alternative)

Alternative position encoding:
- Adds position-dependent bias to attention scores
- No rotation, just bias matrix
- Even better length extrapolation

**Trade-off**: RoPE is more common and well-tested

## Normalization

### RMSNorm - Recommended

Simplified LayerNorm:

```python
def rmsnorm(x, weight):
    rms = torch.sqrt(torch.mean(x ** 2, dim=-1, keepdim=True))
    return (x / rms) * weight
```

**Why RMSNorm?**
- Faster than LayerNorm (no mean subtraction)
- Similar performance
- Used in LLaMA, T5

**Comparison**:
- LayerNorm: `norm = (x - mean) / std * weight + bias`
- RMSNorm: `norm = x / rms * weight`

## Model Size Specifications

### Tiny (10M parameters)

**Use case**: Embedded systems, ARM Cortex-M, low-end RISC-V

```yaml
model_type: "gpt2"
vocab_size: 16000
n_positions: 1024
n_embd: 256
n_layer: 6
n_head: 6
n_kv_head: 2          # GQA ratio = 3
n_inner: 682          # SwiGLU FFN
activation_function: "swiglu"
rotary_dim: 256       # RoPE
layer_norm_type: "rmsnorm"
```

**Estimated**:
- Parameters: ~10M
- Memory (FP16): ~20MB
- Memory (INT4): ~5MB
- Inference speed: ~10 tokens/sec (CPU)

### Small (50M parameters)

**Use case**: Resource-constrained systems, Raspberry Pi, entry x86_64

```yaml
model_type: "gpt2"
vocab_size: 32000
n_positions: 2048
n_embd: 512
n_layer: 8
n_head: 8
n_kv_head: 2          # GQA ratio = 4
n_inner: 1365         # SwiGLU FFN
activation_function: "swiglu"
rotary_dim: 512
layer_norm_type: "rmsnorm"
```

**Estimated**:
- Parameters: ~50M
- Memory (FP16): ~100MB
- Memory (INT4): ~25MB
- Inference speed: ~20 tokens/sec (CPU)

### Medium (150M parameters)

**Use case**: General-purpose desktops, servers

```yaml
model_type: "gpt2"
vocab_size: 32000
n_positions: 2048
n_embd: 768
n_layer: 12
n_head: 12
n_kv_head: 4          # GQA ratio = 3
n_inner: 2048         # SwiGLU FFN
activation_function: "swiglu"
rotary_dim: 768
layer_norm_type: "rmsnorm"
initializer_range: 0.02
```

**Estimated**:
- Parameters: ~150M
- Memory (FP16): ~300MB
- Memory (INT4): ~75MB
- Inference speed: ~30 tokens/sec (CPU)

### Large (500M parameters)

**Use case**: Workstations, data centers

```yaml
model_type: "gpt2"
vocab_size: 32000
n_positions: 4096
n_embd: 1024
n_layer: 24
n_head: 16
n_kv_head: 4          # GQA ratio = 4
n_inner: 2730         # SwiGLU FFN
activation_function: "swiglu"
rotary_dim: 1024
layer_norm_type: "rmsnorm"
```

**Estimated**:
- Parameters: ~500M
- Memory (FP16): ~1GB
- Memory (INT4): ~250MB
- Inference speed: ~50 tokens/sec (CPU)

## Parameter Estimation

### Formula

Total parameters ≈ `vocab_size * d_model + n_layer * params_per_layer`

Where `params_per_layer` ≈ `12 * d_model^2 + 4 * d_model * d_ffn`

**Breakdown**:
- Token embeddings: `vocab_size * d_model`
- Each attention layer: `4 * d_model^2` (Q, K, V, O projections)
- Each FFN layer: `3 * d_model * d_ffn` (W1, W2, W3 for SwiGLU)
- Layer norms: `2 * d_model * n_layer` (negligible)

### Validation Tool

Use `estimate_flops` tool:

```python
def estimate_model_size(config):
    vocab_size = config['vocab_size']
    d_model = config['n_embd']
    n_layer = config['n_layer']
    d_ffn = config['n_inner']

    embedding_params = vocab_size * d_model
    attention_params_per_layer = 4 * d_model * d_model
    ffn_params_per_layer = 3 * d_model * d_ffn

    total = embedding_params + n_layer * (attention_params_per_layer + ffn_params_per_layer)
    return total
```

## Architecture Validation

### Config Validation

ModelArchitectAgent uses `validate_architecture` tool to check:

✅ **Sanity checks**:
- `n_embd % n_head == 0` (head dimension must be integer)
- `n_head % n_kv_head == 0` (GQA ratio must be integer)
- `n_positions` is power of 2 (for efficiency)
- `vocab_size < 100000` (not too large)

✅ **Parameter budget**:
- Tiny: 5M-50M
- Small: 50M-150M
- Medium: 150M-500M
- Large: 500M-1B

✅ **Memory constraints**:
- Tiny: Model (FP16) < 100MB
- Small: Model (FP16) < 300MB
- Medium: Model (FP16) < 1GB
- Large: Model (FP16) < 3GB

### FLOPs Estimation

For inference (one forward pass):

```
FLOPs ≈ 2 * params + 2 * n_layer * batch_size * seq_len * d_model^2
```

**Use case**: Estimate if model can run on target hardware (CPU/GPU)

## Agent Tools

ModelArchitectAgent has access to:

**`validate_architecture(config_path)`**
- Validates config YAML for correctness
- Checks parameter budget, memory constraints
- Returns errors if invalid

**`estimate_flops(config_path)`**
- Estimates FLOPs per forward pass
- Estimates memory usage (FP16, INT4)
- Returns JSON report

## Output Artifacts

After architecture design:

```
SLM/configs/
├── tiny_10M.yaml
├── small_50M.yaml
├── medium_150M.yaml
├── large_500M.yaml
└── arch_validation_report.json
```

## Related Specifications

- [training.md](training.md) - Training loop using designed architecture
- [quantization.md](quantization.md) - INT4/INT8 compression
- [export.md](export.md) - GGUF/ONNX export formats
