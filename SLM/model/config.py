"""Model + training configuration loaded from the YAML config files.

Mirrors the schema in ``SLM/configs/*.yaml`` (``architecture`` and ``training``
sections). Kept as frozen dataclasses so a loaded config is an immutable record
shared across train/evaluate/quantize/export.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml


def _coerce(cls, data: dict) -> dict:
    """Keep only known fields, coercing each to its declared int/float type.

    YAML 1.1 parses unquoted scientific notation like ``3e-4`` as a *string*;
    this coerces such values back to the dataclass field type so configs load
    robustly regardless of how the number was written.
    """
    typed = {f.name: f.type for f in fields(cls)}
    out: dict = {}
    for key, value in data.items():
        if key not in typed:
            continue
        target = typed[key]
        try:
            if target in (int, "int") and not isinstance(value, bool):
                out[key] = int(value)
            elif target in (float, "float"):
                out[key] = float(value)
            else:
                out[key] = value
        except (TypeError, ValueError):
            out[key] = value
    return out


@dataclass(frozen=True)
class ModelConfig:
    """Decoder-only transformer hyperparameters (the ``architecture`` block)."""

    hidden_size: int = 256
    num_layers: int = 6
    num_attention_heads: int = 4
    num_key_value_heads: int = 2
    intermediate_size: int = 1024
    vocab_size: int = 32000
    max_position_embeddings: int = 2048
    rope_theta: float = 10000.0
    attention_dropout: float = 0.0
    hidden_dropout: float = 0.0
    activation: str = "swiglu"

    def __post_init__(self) -> None:
        if self.num_attention_heads % self.num_key_value_heads != 0:
            raise ValueError(
                "num_attention_heads must be divisible by num_key_value_heads "
                f"({self.num_attention_heads} % {self.num_key_value_heads} != 0)"
            )
        if self.hidden_size % self.num_attention_heads != 0:
            raise ValueError(
                "hidden_size must be divisible by num_attention_heads "
                f"({self.hidden_size} % {self.num_attention_heads} != 0)"
            )

    @property
    def head_dim(self) -> int:
        return self.hidden_size // self.num_attention_heads

    def to_dict(self) -> dict:
        return {
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "num_attention_heads": self.num_attention_heads,
            "num_key_value_heads": self.num_key_value_heads,
            "intermediate_size": self.intermediate_size,
            "vocab_size": self.vocab_size,
            "max_position_embeddings": self.max_position_embeddings,
            "rope_theta": self.rope_theta,
            "attention_dropout": self.attention_dropout,
            "hidden_dropout": self.hidden_dropout,
            "activation": self.activation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelConfig":
        return cls(**_coerce(cls, data))


@dataclass(frozen=True)
class TrainConfig:
    """Optimization hyperparameters (the ``training`` block)."""

    batch_size: int = 32
    learning_rate: float = 3e-4
    weight_decay: float = 0.1
    warmup_steps: int = 1000
    max_steps: int = 10000
    gradient_accumulation_steps: int = 1
    optimizer: str = "adamw"
    scheduler: str = "cosine"
    checkpoint_every: int = 1000
    eval_every: int = 500

    @classmethod
    def from_dict(cls, data: dict) -> "TrainConfig":
        return cls(**_coerce(cls, data))


def load_config(path: str | Path) -> tuple[ModelConfig, TrainConfig]:
    """Load ``(ModelConfig, TrainConfig)`` from a YAML config file.

    Missing sections fall back to dataclass defaults so partial configs load.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    arch = raw.get("architecture", {}) or {}
    train = raw.get("training", {}) or {}
    return ModelConfig.from_dict(arch), TrainConfig.from_dict(train)
