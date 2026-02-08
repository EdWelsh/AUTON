# Model Export Specification

## Objective

Export quantized SLMs to GGUF and ONNX formats for integration into the AUTON kernel. Exported models must be validated for format compliance and functional correctness.

## Export Formats

### GGUF (GPT-Generated Unified Format)

**Primary format for AUTON kernel integration**

**Why GGUF?**
- Native support in llama.cpp (C/C++ inference)
- Optimized for CPU inference
- Supports quantized weights (INT4/INT8)
- Memory-mapped loading (fast startup)
- Cross-platform (x86_64, aarch64, riscv64)

**Use case**: Embed in kernel, load via SLM runtime

### ONNX (Open Neural Network Exchange)

**Alternative format for flexibility**

**Why ONNX?**
- Framework-agnostic
- Supports multiple runtimes (ONNX Runtime, TensorRT)
- Better GPU acceleration support
- Industry standard

**Use case**: Testing, benchmarking, alternative runtimes

## GGUF Export Pipeline

### Step 1: Install Dependencies

```bash
# Install llama.cpp (for conversion tools)
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && make

# Python bindings
pip install gguf
```

### Step 2: Convert Model to GGUF

```python
from gguf import GGUFWriter, GGMLQuantizationType
import torch

def export_to_gguf(model_path, output_path, quant_type="Q4_K_M"):
    """
    Export quantized model to GGUF format.

    Args:
        model_path: Path to quantized model (INT4/INT8)
        output_path: Path to save GGUF file
        quant_type: GGUF quantization type
                    - Q4_K_M: 4-bit medium (default)
                    - Q4_K_S: 4-bit small
                    - Q8_0: 8-bit
    """
    # Load model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model = AutoModelForCausalLM.from_pretrained(model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    # Initialize GGUF writer
    writer = GGUFWriter(output_path, arch="gpt2")

    # Write metadata
    writer.add_name("AUTON SLM")
    writer.add_description(f"AUTON Small Language Model for kernel integration")
    writer.add_architecture("gpt2")
    writer.add_context_length(model.config.n_positions)
    writer.add_embedding_length(model.config.n_embd)
    writer.add_block_count(model.config.n_layer)
    writer.add_head_count(model.config.n_head)

    # Write vocabulary
    tokens = [tokenizer.decode([i]) for i in range(len(tokenizer))]
    writer.add_tokenizer_model("gpt2")
    writer.add_token_list(tokens)

    # Write weights (quantized)
    for name, param in model.named_parameters():
        # Convert to GGUF quantization format
        tensor_data = param.cpu().numpy()
        gguf_tensor = convert_to_gguf_quant(tensor_data, quant_type)
        writer.add_tensor(name, gguf_tensor)

    # Write file
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()

    print(f"Exported to GGUF: {output_path}")
    return output_path
```

### Step 3: Validate GGUF Format

```python
def validate_gguf(gguf_path):
    """Validate GGUF file format and contents."""
    from gguf import GGUFReader

    reader = GGUFReader(gguf_path)

    # Check header
    assert reader.fields, "GGUF header missing"

    # Check metadata
    required_fields = ["general.architecture", "general.name", "tokenizer.ggml.tokens"]
    for field in required_fields:
        assert field in reader.fields, f"Missing required field: {field}"

    # Check tensors
    tensor_count = len(reader.tensors)
    assert tensor_count > 0, "No tensors found in GGUF"

    # Check file size
    file_size_mb = Path(gguf_path).stat().st_size / (1024 * 1024)
    print(f"GGUF file size: {file_size_mb:.1f} MB")
    print(f"Tensor count: {tensor_count}")

    return True
```

### Step 4: Test Inference with llama.cpp

```bash
# Test loading and generation
./llama.cpp/main \
    -m SLM/models/exports/medium_150M.gguf \
    -p "PCI device 8086:10d3 is" \
    -n 50 \
    --temp 0.7

# Expected output:
# "an Intel Gigabit Ethernet controller..."
```

## ONNX Export Pipeline

### Step 1: Install Dependencies

```bash
pip install onnx onnxruntime optimum
```

### Step 2: Convert Model to ONNX

```python
from optimum.onnxruntime import ORTModelForCausalLM
from transformers import AutoTokenizer

def export_to_onnx(model_path, output_path):
    """
    Export model to ONNX format.

    Args:
        model_path: Path to quantized model
        output_path: Directory to save ONNX model
    """
    # Load model
    model = ORTModelForCausalLM.from_pretrained(model_path, export=True)
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    # Save as ONNX
    model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)

    print(f"Exported to ONNX: {output_path}")
    return output_path
```

### Step 3: Validate ONNX Format

```python
import onnx

def validate_onnx(onnx_path):
    """Validate ONNX model format."""
    model = onnx.load(onnx_path)

    # Check model
    onnx.checker.check_model(model)

    # Print model info
    print(f"ONNX opset version: {model.opset_import[0].version}")
    print(f"Graph inputs: {[i.name for i in model.graph.input]}")
    print(f"Graph outputs: {[o.name for o in model.graph.output]}")

    return True
```

### Step 4: Test Inference with ONNX Runtime

```python
import onnxruntime as ort
import numpy as np

def test_onnx_inference(onnx_path, tokenizer_path):
    # Load ONNX model
    session = ort.InferenceSession(onnx_path)

    # Load tokenizer
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)

    # Test input
    prompt = "PCI device 8086:10d3 is"
    input_ids = tokenizer(prompt, return_tensors="np").input_ids

    # Run inference
    outputs = session.run(None, {"input_ids": input_ids})
    logits = outputs[0]

    # Decode
    predicted_token = np.argmax(logits[0, -1])
    predicted_text = tokenizer.decode([predicted_token])

    print(f"Input: {prompt}")
    print(f"Predicted next token: {predicted_text}")

    return True
```

## Deployment Manifest

### Create Manifest File

Each exported model needs a manifest for kernel integration:

```json
{
  "model_name": "auton-slm-medium-150M",
  "version": "1.0.0",
  "format": "gguf",
  "quantization": "int4",
  "architecture": "gpt2",
  "parameters": 150000000,
  "vocab_size": 32000,
  "context_length": 2048,
  "embedding_dim": 768,
  "num_layers": 12,
  "num_heads": 12,
  "size_bytes": 78643200,
  "checksum": "sha256:a1b2c3d4e5f67890...",
  "trained_on": "2026-02-08",
  "target_architectures": ["x86_64", "aarch64", "riscv64"],
  "performance": {
    "perplexity": 18.5,
    "os_benchmark_accuracy": 0.82,
    "inference_speed_tokens_per_sec": 32
  },
  "files": {
    "model": "medium_150M.gguf",
    "tokenizer": "tokenizer.json",
    "vocab": "vocab.json"
  }
}
```

**Save to**: `SLM/models/exports/manifests/medium_150M.json`

## Validation Criteria

### Format Validation

**GGUF**:
✅ Valid header and magic number
✅ All required metadata fields present
✅ Tensors loadable
✅ Tokenizer vocabulary matches model
✅ File size matches expected (± 10%)

**ONNX**:
✅ Passes `onnx.checker.check_model()`
✅ Input/output shapes correct
✅ Opset version compatible (>= 11)
✅ Can be loaded by ONNX Runtime

### Functional Validation

**Test inference**:
✅ Model loads without errors
✅ Generates coherent text
✅ Output matches PyTorch model (within tolerance)
✅ Inference speed meets target (> 10 tok/s)

**Tolerance for output matching**:
- Logits should match within 1e-2 (FP16 precision)
- Top-5 predictions should be identical or very similar

### Acceptance Criteria

An exported model is accepted if:

✅ **Format validation passes** (GGUF or ONNX)
✅ **Functional validation passes** (inference works)
✅ **Output consistency** (matches original model)
✅ **Performance acceptable** (speed, memory)
✅ **Manifest created** with all required fields
✅ **Checksum generated** for integrity verification

## Cross-Platform Testing

### Test on Target Architectures

**x86_64**:
```bash
./llama.cpp/main -m medium_150M.gguf -p "Test prompt" -n 50
```

**aarch64** (ARM):
```bash
qemu-aarch64 ./llama.cpp/main -m medium_150M.gguf -p "Test prompt" -n 50
```

**riscv64**:
```bash
qemu-riscv64 ./llama.cpp/main -m medium_150M.gguf -p "Test prompt" -n 50
```

**Validation**: All architectures should produce similar outputs (tokens may vary slightly due to floating-point precision)

## Agent Tools

ExportAgent has access to:

**`export_gguf(model_path, output_path, quant_type)`**
- Exports model to GGUF format
- Returns GGUF file path

**`export_onnx(model_path, output_path)`**
- Exports model to ONNX format
- Returns ONNX directory path

**`validate_format(export_path, format_type)`**
- Validates exported model format
- Returns validation report (pass/fail + details)

**`test_inference(export_path, format_type, test_prompts)`**
- Tests inference on exported model
- Compares outputs with original
- Returns inference test report

**`create_manifest(model_info, output_path)`**
- Creates deployment manifest JSON
- Includes all metadata, checksums, performance metrics

## Output Artifacts

After export:

```
SLM/models/exports/
├── medium_150M.gguf (GGUF format)
├── medium_150M_onnx/ (ONNX format)
│   ├── model.onnx
│   ├── tokenizer.json
│   └── config.json
├── manifests/
│   ├── medium_150M.json (deployment manifest)
│   └── checksums.txt (SHA256 hashes)
└── validation_reports/
    ├── medium_150M_gguf_validation.json
    └── medium_150M_onnx_validation.json
```

## Integration with VibeTensor Loop

```
QuantizationAgent → produces quantized model
        ↓
ExportAgent → export to GGUF + ONNX
        ↓
    format validation passes? → YES
        ↓
    test inference passes? → YES
        ↓
    create manifest → commit
        ↓
IntegratorAgent → integrate into kernel
```

## Common Issues and Troubleshooting

### Issue: GGUF export fails

**Causes**:
- Incompatible model architecture
- Missing llama.cpp tools
- Unsupported quantization type

**Solutions**:
- Verify model architecture matches GGUF spec
- Install latest llama.cpp
- Use supported quant types (Q4_K_M, Q8_0)

### Issue: ONNX export fails

**Causes**:
- Unsupported operations in model
- Dynamic shapes not handled
- Opset version mismatch

**Solutions**:
- Update optimum/onnx libraries
- Specify fixed shapes
- Use compatible opset version

### Issue: Exported model outputs differ from original

**Causes**:
- Quantization precision loss
- Different random seeds
- Platform-specific floating-point differences

**Solutions**:
- Check if difference within tolerance (1e-2)
- Use deterministic mode (set seeds)
- Accept small differences for quantized models

## Related Specifications

- [quantization.md](quantization.md) - Quantization produces models to export
- [integration.md](integration.md) - Integration of exported models into kernel
