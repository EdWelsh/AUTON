# SLM Training Specification

## Objective

Train a transformer-based Small Language Model (SLM) optimized for integration into the AUTON kernel. The trained model will power the kernel's natural language interface for hardware discovery, driver selection, installation, and system management.

## Architecture Requirements

### Model Type
- **Decoder-only transformer** (GPT-style architecture)
- Autoregressive next-token prediction
- Causal masking for attention

### Core Components

**1. Attention Mechanism**
- **Grouped Query Attention (GQA)** for efficiency
- Multiple query heads share key/value heads
- Reduces memory bandwidth and KV cache size
- Formula: `num_kv_heads = num_heads // gqa_ratio`

**2. Feed-Forward Network**
- **SwiGLU activation** (Swish-Gated Linear Unit)
- More parameter-efficient than ReLU/GELU
- Formula: `FFN(x) = (Swish(xW1) ⊙ xW2)W3`

**3. Position Encoding**
- **Rotary Position Embeddings (RoPE)**
- No absolute position embeddings
- Enables better length extrapolation
- Applied to query/key projections before attention

**4. Normalization**
- **RMSNorm** (Root Mean Square LayerNorm)
- Faster than LayerNorm, similar performance
- Formula: `RMSNorm(x) = x / RMS(x) * g`

### Architecture Parameters by Size

| Size | Params | Layers | Heads | Embed Dim | FFN Dim | Vocab Size | Context Length |
|------|--------|--------|-------|-----------|---------|------------|----------------|
| Tiny | 10M | 6 | 6 | 256 | 1024 | 16000 | 1024 |
| Small | 50M | 8 | 8 | 512 | 2048 | 32000 | 2048 |
| Medium | 150M | 12 | 12 | 768 | 3072 | 32000 | 2048 |
| Large | 500M | 24 | 16 | 1024 | 4096 | 32000 | 4096 |

## Training Data Requirements

### Dataset Composition

The training corpus should include:

1. **Operating System Code** (40%)
   - Linux kernel source comments
   - BSD kernel documentation
   - Driver implementation comments
   - System call descriptions

2. **Hardware Documentation** (30%)
   - PCI vendor/device ID databases
   - Datasheets for common peripherals
   - ACPI/Device Tree descriptions
   - Hardware architecture manuals

3. **System Administration** (20%)
   - Shell command documentation
   - Configuration file formats
   - Package manager usage
   - System logs and diagnostics

4. **Natural Language Instructions** (10%)
   - User queries about hardware
   - Driver installation procedures
   - Troubleshooting guides
   - "How to" articles for sysadmins

### Data Format

Tokenized datasets must be stored in binary format:
- **Train**: `SLM/datasets/processed/train.bin` (90% of data)
- **Validation**: `SLM/datasets/processed/val.bin` (5% of data)
- **Test**: `SLM/datasets/processed/test.bin` (5% of data)
- **Vocabulary**: `SLM/datasets/processed/vocab.json`

## Training Loop Implementation

### Setup

```python
import torch
from transformers import GPT2Config, GPT2LMHeadModel, Trainer, TrainingArguments

# Load config
config = load_model_config(config_path)

# Initialize model
model = GPT2LMHeadModel(config)

# Load tokenized dataset
train_dataset = load_tokenized_dataset("train.bin")
val_dataset = load_tokenized_dataset("val.bin")
```

### Training Configuration

**Optimizer**: AdamW
- Learning rate: 3e-4 (with warmup)
- Betas: (0.9, 0.95)
- Weight decay: 0.1
- Gradient clipping: 1.0

**Learning Rate Schedule**:
- Warmup steps: 2000
- Cosine decay to 10% of max LR
- Final LR: 3e-5

**Batch Configuration**:
- Micro-batch size: 8 (per device)
- Gradient accumulation: 4 steps
- Effective batch size: 32

**Training Duration**:
- Tiny: 10K-20K steps
- Small: 50K-100K steps
- Medium: 100K-200K steps
- Large: 200K-500K steps

### Training Loop

```python
# Training arguments
training_args = TrainingArguments(
    output_dir=checkpoint_dir,
    num_train_epochs=1,  # Use max_steps instead
    max_steps=max_steps,
    per_device_train_batch_size=8,
    gradient_accumulation_steps=4,
    learning_rate=3e-4,
    lr_scheduler_type="cosine",
    warmup_steps=2000,
    weight_decay=0.1,
    logging_steps=100,
    save_steps=5000,
    eval_steps=5000,
    evaluation_strategy="steps",
    save_total_limit=5,
    fp16=torch.cuda.is_available(),  # Mixed precision on GPU
    dataloader_num_workers=4,
)

# Initialize trainer
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=val_dataset,
)

# Run training
trainer.train()

# Save final model
trainer.save_model(final_checkpoint_path)
```

### Monitoring

**Metrics to log every 100 steps:**
- Training loss (cross-entropy)
- Learning rate
- Gradient norm
- Tokens per second
- GPU memory usage

**Metrics to evaluate every 5000 steps:**
- Validation loss
- Validation perplexity: `exp(val_loss)`
- Sample generations (sanity check)

**TensorBoard Logging**:
```bash
tensorboard --logdir=SLM/models/checkpoints/logs
```

## Checkpointing Strategy

### Checkpoint Frequency
- Save every 5000 steps
- Keep last 5 checkpoints
- Save best checkpoint by validation perplexity

### Checkpoint Contents
Each checkpoint directory contains:
- `pytorch_model.bin` - Model weights
- `config.json` - Model architecture
- `training_args.bin` - Training configuration
- `optimizer.pt` - Optimizer state (for resume)
- `scheduler.pt` - LR scheduler state
- `trainer_state.json` - Step count, metrics

### Resume from Checkpoint

If training is interrupted:
```python
# Resume from latest checkpoint
trainer = Trainer(model=model, args=training_args, ...)
trainer.train(resume_from_checkpoint=latest_checkpoint)
```

## Validation Criteria

### During Training

**Failure conditions (abort training):**
- Loss becomes NaN or Inf
- Gradient norm explodes (> 1000)
- No decrease in loss after 10K steps
- GPU out of memory errors persist

**Success indicators:**
- Training loss decreases monotonically
- Validation perplexity improves
- Gradient norms stable (0.1-10 range)
- Generated samples are coherent

### Final Validation

A trained model is accepted if:

1. ✅ Training completed without NaN/Inf
2. ✅ Validation perplexity meets threshold:
   - Tiny: < 50
   - Small: < 30
   - Medium: < 20
   - Large: < 15
3. ✅ Final checkpoint saves successfully
4. ✅ Model can be loaded and generates coherent text
5. ✅ Checkpoint size matches expected (within 10%)

## Multi-GPU Training (Optional)

For faster training on multiple GPUs:

```python
# Use PyTorch DistributedDataParallel
training_args = TrainingArguments(
    ...,
    local_rank=int(os.environ.get("LOCAL_RANK", -1)),
    ddp_backend="nccl",
)

# Launch with torchrun
# torchrun --nproc_per_node=4 train.py --config medium_150M.yaml
```

## Cost Estimation

**GPU Training Costs (A100 on cloud):**
- Tiny (10M, 20K steps): ~$2-5
- Small (50M, 100K steps): ~$10-20
- Medium (150M, 200K steps): ~$30-50
- Large (500M, 500K steps): ~$100-200

**Budget-Conscious Options:**
- Use local GPUs (free but slower)
- Use lower-end cloud GPUs (T4, V100)
- Train smaller models first
- Use CPU for tiny models (very slow)

## Error Handling

### Common Issues

**1. Out of Memory**
- Reduce batch size
- Increase gradient accumulation
- Use gradient checkpointing
- Use smaller model

**2. Training Instability**
- Lower learning rate
- Increase warmup steps
- Reduce batch size
- Check data quality

**3. Slow Convergence**
- Increase learning rate slightly
- Adjust warmup schedule
- Check dataset diversity
- Verify tokenization quality

### Agent Retry Logic

If training fails, the TrainingAgent will:
1. Analyze error logs
2. Adjust hyperparameters (reduce LR, batch size)
3. Retry training from last good checkpoint
4. Report failure after 3 attempts

## Integration with VibeTensor Loop

Training integrates into the VibeTensor validation loop:

```
TrainingAgent → train model → checkpoint
                    ↓
         loss decreases? → YES → continue
                    ↓ NO
         retry with adjusted hyperparams
                    ↓
         3 failures? → report error to Manager
                    ↓
         success? → commit checkpoint → ReviewerAgent
```

## Reference Implementation

See `SLM/scripts/train.py` for the complete training script implementation.

## Related Specifications

- [data_preparation.md](data_preparation.md) - Dataset requirements
- [architecture.md](architecture.md) - Architecture design details
- [evaluation.md](evaluation.md) - Post-training evaluation
- [quantization.md](quantization.md) - Model compression
