"""Sample model configurations for testing."""

TINY_CONFIG = {
    "model": {
        "name": "auton-tiny-test",
        "parameters": 1_000_000,
    },
    "architecture": {
        "hidden_size": 128,
        "num_layers": 2,
        "num_heads": 2,
    },
    "training": {
        "batch_size": 4,
        "learning_rate": 1e-4,
        "max_steps": 100,
    },
}
