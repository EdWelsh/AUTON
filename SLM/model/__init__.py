"""AUTON SLM neural backend: model definition, config, data, and checkpoints.

``SLMTransformer`` is imported lazily so that torch-free consumers (config/data
loading, the host tooling, the torch-free Docker `test` image) can
``from model.config import ...`` without pulling in torch. Accessing
``model.SLMTransformer`` triggers the (torch-dependent) import on demand.
"""

from model.config import ModelConfig, TrainConfig, load_config

__all__ = ["ModelConfig", "TrainConfig", "load_config", "SLMTransformer"]


def __getattr__(name: str):
    if name == "SLMTransformer":
        from model.transformer import SLMTransformer

        return SLMTransformer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
