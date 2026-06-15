"""End-to-end neural-pipeline tests: train -> evaluate -> quantize -> export.

Skipped entirely when torch is unavailable so the lightweight test run still
passes. Uses a deliberately tiny model so the full pipeline runs in well under a
second on CPU, plus a check that the shipped tiny_10M.yaml config builds.
"""

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")

SLM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SLM_ROOT))
sys.path.insert(0, str(SLM_ROOT / "scripts"))

import evaluate as evaluate_mod  # noqa: E402
import export_gguf as gguf_mod  # noqa: E402
import export_onnx as onnx_mod  # noqa: E402
import quantize as quantize_mod  # noqa: E402
import train as train_mod  # noqa: E402

from model.config import ModelConfig, load_config  # noqa: E402
from model.transformer import SLMTransformer  # noqa: E402
from tools.gguf_validator import validate_gguf  # noqa: E402

# Small model config written to YAML so train/evaluate load it like a real run.
_TINY_YAML = """
architecture:
  hidden_size: 32
  num_layers: 2
  num_attention_heads: 4
  num_key_value_heads: 2
  intermediate_size: 64
  vocab_size: 128
  max_position_embeddings: 256
training:
  batch_size: 2
  learning_rate: 0.001
  warmup_steps: 1
  max_steps: 5
  checkpoint_every: 1000
"""


@pytest.fixture
def tiny_config(tmp_path):
    cfg = tmp_path / "tiny.yaml"
    cfg.write_text(_TINY_YAML)
    return cfg


@pytest.fixture
def tiny_dataset(tmp_path):
    """A tokenized JSONL dataset with enough tokens for several windows."""
    ds = tmp_path / "data.jsonl"
    lines = [json.dumps({"ids": list(range(0, 100))}) for _ in range(20)]
    ds.write_text("\n".join(lines))
    return ds


def test_shipped_tiny_config_builds():
    """The real tiny_10M.yaml config should load and instantiate a model."""
    model_cfg, _ = load_config(SLM_ROOT / "configs" / "tiny_10M.yaml")
    model = SLMTransformer(model_cfg)
    assert model.num_parameters() > 0


def test_model_forward_shapes():
    import torch

    cfg = ModelConfig(hidden_size=32, num_layers=2, num_attention_heads=4,
                      num_key_value_heads=2, intermediate_size=64, vocab_size=64)
    model = SLMTransformer(cfg)
    ids = torch.randint(0, cfg.vocab_size, (2, 8))
    logits, loss = model(ids, ids)
    assert logits.shape == (2, 8, cfg.vocab_size)
    assert loss.item() > 0


def test_full_pipeline(tiny_config, tiny_dataset, tmp_path):
    out = tmp_path / "out"

    # Train
    summary = train_mod.train(
        str(tiny_config), str(tiny_dataset), str(out),
        max_steps=5, seq_len=8, batch_size=2,
    )
    ckpt = Path(summary["checkpoint"])
    assert ckpt.exists()
    assert summary["steps"] == 5
    assert summary["final_loss"] == summary["final_loss"]  # not NaN

    # Evaluate
    ev = evaluate_mod.evaluate(str(ckpt), str(tiny_dataset), seq_len=8, batch_size=2)
    assert ev["perplexity"] > 0
    assert ev["loss"] > 0

    # Quantize (both bit widths)
    for bits in (8, 4):
        q_out = tmp_path / f"model_int{bits}.pt"
        stats = quantize_mod.quantize_checkpoint(str(ckpt), str(q_out), bits)
        assert q_out.exists()
        assert stats["bits"] == bits
        assert stats["quantized_params"] > 0

    # Export ONNX
    onnx_out = tmp_path / "model.onnx"
    onnx_summary = onnx_mod.export_onnx(str(ckpt), str(onnx_out))
    assert onnx_out.exists()
    assert onnx_summary["valid"] is True

    # Export GGUF + validate
    gguf_out = tmp_path / "model.gguf"
    gguf_summary = gguf_mod.export_gguf(str(ckpt), str(gguf_out))
    assert gguf_out.exists()
    assert gguf_summary["tensors"] > 0
    result = validate_gguf(str(gguf_out))
    assert result["valid"] is True
    assert result["tensor_count"] == gguf_summary["tensors"]
