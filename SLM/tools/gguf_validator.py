"""GGUF format validator.

Performs real structural validation of a GGUF container: it checks the ``GGUF``
magic bytes and parses the little-endian header (version, tensor count, metadata
KV count). Dependency-free — it reads the header directly rather than requiring
the ``gguf`` package.
"""

from __future__ import annotations

import struct
from pathlib import Path

GGUF_MAGIC = b"GGUF"
_HEADER = struct.Struct("<4sIQQ")  # magic, version(u32), tensor_count(u64), kv_count(u64)


def validate_gguf(file_path: str) -> dict:
    """Validate a GGUF file.

    Returns ``{"valid": True, "size_mb", "version", "tensor_count", "kv_count"}``
    for a well-formed header, or ``{"valid": False, "error": ...}`` otherwise.
    """
    path = Path(file_path)

    if not path.exists():
        return {"valid": False, "error": "File not found"}

    size_bytes = path.stat().st_size
    if size_bytes < _HEADER.size:
        return {"valid": False, "error": "File too small to contain a GGUF header"}

    with path.open("rb") as fh:
        header = fh.read(_HEADER.size)

    magic, version, tensor_count, kv_count = _HEADER.unpack(header)
    if magic != GGUF_MAGIC:
        return {"valid": False, "error": f"Invalid magic: expected GGUF, got {magic!r}"}

    return {
        "valid": True,
        "size_mb": size_bytes / (1024 * 1024),
        "version": version,
        "tensor_count": tensor_count,
        "kv_count": kv_count,
    }


def make_minimal_header(version: int = 3, tensor_count: int = 0, kv_count: int = 0) -> bytes:
    """Build a minimal valid GGUF header (test/fixtures helper)."""
    return _HEADER.pack(GGUF_MAGIC, version, tensor_count, kv_count)
