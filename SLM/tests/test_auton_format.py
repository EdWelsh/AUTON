"""Tests for the AUTON flat model format (tools/auton_format.py).

These run without torch: they exercise the byte layout the kernel loader mirrors,
which is the hard host<->kernel contract.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from tools import auton_format as af


def _tiny_header() -> af.FlatHeader:
    # dim=8, 2 layers, 2 heads, 1 kv head, hidden 16, vocab 5, seq 32
    return af.FlatHeader(
        dim=8, hidden_dim=16, n_layers=2, n_heads=2, n_kv_heads=1,
        vocab_size=5, seq_len=32,
    )


def _weights_for(h: af.FlatHeader) -> list[float]:
    return [0.0] * af.weight_element_count(h)


def _vocab_for(h: af.FlatHeader) -> list[tuple[float, bytes]]:
    return [(float(-i), f"tok{i}".encode()) for i in range(h.vocab_size)]


def test_header_pack_unpack_roundtrip():
    h = _tiny_header()
    back = af.FlatHeader.unpack(h.pack())
    assert back == h


def test_weight_element_count_matches_formula():
    h = _tiny_header()
    hd = h.head_dim
    # Explicit recomputation independent of the implementation.
    per_layer = (
        h.dim
        + h.n_heads * hd * h.dim
        + h.n_kv_heads * hd * h.dim
        + h.n_kv_heads * hd * h.dim
        + h.dim * h.n_heads * hd
        + h.dim
        + h.hidden_dim * h.dim
        + h.dim * h.hidden_dim
        + h.hidden_dim * h.dim
    )
    expected = h.vocab_size * h.dim + h.n_layers * per_layer + h.dim
    assert af.weight_element_count(h) == expected


def test_write_and_validate_roundtrip(tmp_path: Path):
    h = _tiny_header()
    out = tmp_path / "tiny.bin"
    n = af.write_model(str(out), h, _weights_for(h), _vocab_for(h))
    assert n == out.stat().st_size
    parsed = af.validate(str(out))
    assert parsed == h


def test_validate_rejects_bad_magic(tmp_path: Path):
    out = tmp_path / "bad.bin"
    h = _tiny_header()
    af.write_model(str(out), h, _weights_for(h), _vocab_for(h))
    data = bytearray(out.read_bytes())
    struct.pack_into("<I", data, 0, 0xDEADBEEF)
    out.write_bytes(data)
    with pytest.raises(ValueError, match="bad magic"):
        af.validate(str(out))


def test_validate_rejects_truncated_file(tmp_path: Path):
    out = tmp_path / "short.bin"
    h = _tiny_header()
    af.write_model(str(out), h, _weights_for(h), _vocab_for(h))
    data = out.read_bytes()
    out.write_bytes(data[: len(data) - 3])  # chop the last token's bytes
    with pytest.raises(ValueError):
        af.validate(str(out))


def test_write_rejects_wrong_weight_count(tmp_path: Path):
    h = _tiny_header()
    with pytest.raises(ValueError, match="weight count"):
        af.write_model(str(tmp_path / "x.bin"), h, [0.0] * 3, _vocab_for(h))


def test_offsets_are_contiguous(tmp_path: Path):
    """The tokenizer section must start exactly after the weight block."""
    h = _tiny_header()
    out = tmp_path / "c.bin"
    af.write_model(str(out), h, _weights_for(h), _vocab_for(h))
    data = out.read_bytes()
    weight_bytes = af.weight_element_count(h) * 4
    off = af.HEADER_SIZE + weight_bytes
    (max_len,) = struct.unpack_from("<I", data, off)
    assert max_len == max(len(b) for _, b in _vocab_for(h))
