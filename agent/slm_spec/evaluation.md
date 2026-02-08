# Model Evaluation Specification

## Objective

Evaluate trained SLM checkpoints using standard benchmarks and domain-specific tests to select the best model for quantization and kernel integration.

## Evaluation Metrics

### Primary Metrics

**1. Perplexity**
- Measures how well model predicts text
- Formula: `perplexity = exp(average_cross_entropy_loss)`
- Lower is better
- Computed on held-out test set

**Thresholds**:
- Tiny models: < 50
- Small models: < 30
- Medium models: < 20
- Large models: < 15

**2. Accuracy (Next-Token Prediction)**
- Percentage of tokens predicted correctly
- Top-1 accuracy: `correct / total`
- Top-5 accuracy: correct token in top 5 predictions

**Thresholds**:
- Top-1: > 30%
- Top-5: > 60%

### Secondary Metrics

**3. Generation Quality**
- Sample coherence (human evaluation or automated)
- Relevance to prompts
- Technical accuracy

**4. Inference Speed**
- Tokens per second on target hardware
- Latency per token
- Memory bandwidth usage

**5. Domain-Specific Performance**
- Hardware identification accuracy
- Driver selection correctness
- Command completion quality

## Standard Benchmarks

### 1. Perplexity on Test Set

**Implementation**:

```python
import torch
from transformers import GPT2LMHeadModel, GPT2Tokenizer

def compute_perplexity(model, test_dataset):
    model.eval()
    total_loss = 0
    total_tokens = 0

    with torch.no_grad():
        for batch in test_dataset:
            outputs = model(batch['input_ids'], labels=batch['input_ids'])
            loss = outputs.loss
            total_loss += loss.item() * len(batch['input_ids'])
            total_tokens += len(batch['input_ids'])

    avg_loss = total_loss / total_tokens
    perplexity = torch.exp(torch.tensor(avg_loss))
    return perplexity.item()
```

### 2. MMLU (Massive Multitask Language Understanding)

Subset of MMLU focused on:
- Computer science
- Engineering
- Electronics

**Reason**: General knowledge less important than technical knowledge

### 3. HellaSwag (Common Sense Reasoning)

Subset focused on:
- Technical troubleshooting scenarios
- System administration tasks

### 4. Custom OS Evaluation

AUTON-specific benchmark:

**Hardware Identification** (100 samples):
- Prompt: "PCI device 8086:1234 is a"
- Expected: "Intel Ethernet controller"
- Metric: Accuracy of device type identification

**Driver Selection** (100 samples):
- Prompt: "Which driver for Realtek RTL8139?"
- Expected: "8139too.ko" or "8139cp.ko"
- Metric: Correct driver name in top-3 predictions

**Command Completion** (100 samples):
- Prompt: "List all PCI devices:"
- Expected: "lspci" or "lspci -v"
- Metric: Correct command in top-3

**Installation Steps** (100 samples):
- Prompt: "Install nginx on Debian"
- Expected: "apt update && apt install nginx"
- Metric: Correct sequence of commands

## Evaluation Pipeline

### Step 1: Load Checkpoint

```python
from transformers import GPT2LMHeadModel

checkpoint_path = "SLM/models/checkpoints/medium_150M/step_100000"
model = GPT2LMHeadModel.from_pretrained(checkpoint_path)
model.eval()
```

### Step 2: Run Standard Benchmarks

```python
# Perplexity
test_perplexity = compute_perplexity(model, test_dataset)
print(f"Test Perplexity: {test_perplexity:.2f}")

# MMLU (subset)
mmlu_score = run_mmlu_benchmark(model, "computer_science")
print(f"MMLU CS: {mmlu_score:.2%}")

# HellaSwag
hellaswag_score = run_hellaswag_benchmark(model, "technical")
print(f"HellaSwag: {hellaswag_score:.2%}")
```

### Step 3: Domain-Specific Evaluation

```python
# Custom OS benchmark
os_benchmark_results = run_os_benchmark(model, "SLM/datasets/benchmarks/custom_os_eval/")

print(f"Hardware ID Accuracy: {os_benchmark_results['hardware_id']:.2%}")
print(f"Driver Selection Accuracy: {os_benchmark_results['driver_select']:.2%}")
print(f"Command Completion Accuracy: {os_benchmark_results['command_complete']:.2%}")
```

### Step 4: Inference Speed

```python
import time

# Measure tokens/sec
num_tokens = 1000
start = time.time()
model.generate(input_ids, max_length=num_tokens)
elapsed = time.time() - start
tokens_per_sec = num_tokens / elapsed

print(f"Inference Speed: {tokens_per_sec:.1f} tokens/sec")
```

### Step 5: Generate Report

```json
{
  "checkpoint": "medium_150M/step_100000",
  "perplexity": 18.5,
  "accuracy_top1": 0.35,
  "accuracy_top5": 0.68,
  "mmlu_cs": 0.42,
  "hellaswag": 0.55,
  "os_benchmark": {
    "hardware_id": 0.82,
    "driver_select": 0.75,
    "command_complete": 0.88
  },
  "inference_speed": 32.5,
  "memory_usage_mb": 320,
  "timestamp": "2026-02-08T12:34:56Z"
}
```

## Model Selection

### Comparing Multiple Checkpoints

If multiple checkpoints or models trained:

**Weighted Score**:
```python
def compute_weighted_score(metrics):
    score = (
        0.4 * (1 / metrics['perplexity']) * 10 +  # Lower perplexity better
        0.3 * metrics['os_benchmark']['avg'] +     # Domain accuracy
        0.2 * metrics['mmlu_cs'] +                 # General accuracy
        0.1 * (metrics['inference_speed'] / 50)    # Speed (normalize to ~50 tok/s)
    )
    return score

# Select best checkpoint
best_checkpoint = max(checkpoints, key=lambda c: compute_weighted_score(c.metrics))
```

**Selection Criteria**:
1. Must meet perplexity threshold
2. Must meet domain accuracy threshold (> 70%)
3. Among passing models, select highest weighted score

### Acceptance Criteria

A model is accepted for quantization if:

✅ **Perplexity meets threshold** (see above)
✅ **OS benchmark accuracy > 70%** (average across 3 tasks)
✅ **Inference speed reasonable** (> 10 tokens/sec on CPU for target size)
✅ **No generation failures** (no infinite loops, repetition, nonsense)
✅ **Memory usage within bounds** (see architecture spec)

## Sample Generation Tests

### Qualitative Evaluation

Generate responses to sample prompts:

```
Prompt: "PCI device 8086:10d3 is"
Generation: "an Intel Gigabit Ethernet controller, specifically the 82574L model. This is commonly found in servers and requires the e1000e driver."

✅ Correct device type
✅ Correct vendor (Intel)
✅ Correct driver (e1000e)
✅ Coherent, technical explanation
```

```
Prompt: "Install Apache web server on Ubuntu:"
Generation: "sudo apt update && sudo apt install apache2. After installation, start the service with sudo systemctl start apache2 and enable it to run on boot with sudo systemctl enable apache2."

✅ Correct commands
✅ Correct sequence
✅ Helpful additional steps
✅ Proper syntax
```

### Automated Quality Checks

```python
def check_generation_quality(prompt, generation):
    checks = {
        "length": 10 < len(generation.split()) < 200,  # Reasonable length
        "repetition": not has_excessive_repetition(generation),
        "coherence": is_coherent(generation),  # Simple heuristics
        "technical_terms": has_technical_terms(generation),
    }
    return all(checks.values())
```

## Benchmark Dataset Locations

Store benchmark datasets in:

```
SLM/datasets/benchmarks/
├── mmlu/
│   └── computer_science.json
├── hellaswag/
│   └── technical_subset.json
└── custom_os_eval/
    ├── hardware_id.json
    ├── driver_select.json
    ├── command_complete.json
    └── installation.json
```

## Agent Tools

TesterAgent (as EvaluationAgent) has access to:

**`evaluate_model(checkpoint_path, test_dataset, metrics)`**
- Runs evaluation on specified checkpoint
- Computes requested metrics (perplexity, accuracy, etc.)
- Returns JSON report

**`run_benchmark(checkpoint_path, benchmark_suite)`**
- Runs standard benchmark (MMLU, HellaSwag, custom OS eval)
- Returns score

**`generate_samples(checkpoint_path, prompts)`**
- Generates text for qualitative evaluation
- Returns generations for human review

## Iteration and Improvement

### Failed Evaluation

If model doesn't meet acceptance criteria:

**High perplexity** (> threshold):
- Train longer (more steps)
- Increase model size
- Improve dataset quality

**Low domain accuracy** (< 70%):
- Add more domain-specific training data
- Adjust data mixture (more hardware/driver docs)
- Fine-tune on domain data

**Slow inference** (< 10 tok/s):
- Use smaller model
- Profile for bottlenecks
- Consider quantization earlier

### VibeTensor Loop Integration

```
TrainingAgent → trains model → checkpoint
        ↓
TesterAgent (Evaluation) → runs benchmarks → metrics
        ↓
    meets threshold? → YES → approve for quantization
        ↓ NO
ReviewerAgent → analyze failures → recommend changes
        ↓
TrainingAgent → retrain with adjustments → iterate
```

## Output Artifacts

After evaluation:

```
SLM/models/checkpoints/medium_150M/
├── step_100000/
│   ├── pytorch_model.bin
│   ├── config.json
│   └── evaluation_report.json  # NEW
├── step_150000/
│   └── evaluation_report.json
└── best_checkpoint_selection.json  # NEW: selected model
```

## Related Specifications

- [training.md](training.md) - Training produces checkpoints to evaluate
- [quantization.md](quantization.md) - Next step for accepted models
- [integration.md](integration.md) - Final validation in kernel
