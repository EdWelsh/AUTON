"""Unit tests for SLM.model.config loading and type coercion."""

import sys
from pathlib import Path

import pytest

SLM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SLM_ROOT))

from model.config import ModelConfig, TrainConfig, load_config  # noqa: E402


def test_scientific_notation_lr_coerced_to_float(tmp_path):
    """YAML parses unquoted 3e-4 as a string; it must load as a float.

    Regression: AdamW received a str learning rate and raised TypeError.
    """
    cfg = tmp_path / "c.yaml"
    cfg.write_text("training:\n  learning_rate: 3e-4\n  warmup_steps: 1000\n")
    _, train_cfg = load_config(cfg)
    assert isinstance(train_cfg.learning_rate, float)
    assert train_cfg.learning_rate == pytest.approx(3e-4)


def test_int_fields_coerced(tmp_path):
    """String integer values coerce to int."""
    cfg = tmp_path / "c.yaml"
    cfg.write_text("architecture:\n  hidden_size: '256'\n  num_attention_heads: 4\n  num_key_value_heads: 2\n")
    model_cfg, _ = load_config(cfg)
    assert model_cfg.hidden_size == 256
    assert isinstance(model_cfg.hidden_size, int)


@pytest.mark.parametrize(
    "name", ["tiny_10M.yaml", "small_50M.yaml", "medium_150M.yaml", "large_500M.yaml"]
)
def test_shipped_configs_load_with_numeric_lr(name):
    """All shipped configs load with a numeric learning rate and valid GQA."""
    model_cfg, train_cfg = load_config(SLM_ROOT / "configs" / name)
    assert isinstance(train_cfg.learning_rate, float)
    assert isinstance(model_cfg, ModelConfig)
    assert isinstance(train_cfg, TrainConfig)
    # __post_init__ would have raised if head counts were inconsistent.
    assert model_cfg.num_attention_heads % model_cfg.num_key_value_heads == 0


def test_invalid_head_ratio_raises():
    """A head count not divisible by KV head count is rejected."""
    with pytest.raises(ValueError):
        ModelConfig(num_attention_heads=4, num_key_value_heads=3)
