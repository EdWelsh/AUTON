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


# --- int8 quantized layout (rung 3c) ---------------------------------------


class TestInt8Layout:
    """Both quant modes must load; int8 is an addition, not a replacement.

    The layout is per-tensor: a f32 scale followed by one int8 code per element
    for 2D matrices, and plain fp32 for the 1D norm vectors — matching
    SLM/scripts/quantize.py, which quantizes 2D float tensors and passes
    everything else through.
    """

    def _header(self, quant=af.QUANT_FP32):
        return af.FlatHeader(
            dim=8, hidden_dim=16, n_layers=2, n_heads=2, n_kv_heads=1,
            vocab_size=6, seq_len=32, quant=quant,
        )

    def _tensors(self, h):
        # Deterministic, spanning negatives so the symmetric scale is exercised.
        return [
            [((i % 17) - 8) * 0.25 for i in range(n)]
            for n in af.tensor_element_counts(h)
        ]

    def _vocab(self, h):
        return [(float(-i), f"tok{i}".encode()) for i in range(h.vocab_size)]

    def test_tensor_counts_match_flat_count(self):
        h = self._header()
        assert sum(af.tensor_element_counts(h)) == af.weight_element_count(h)

    def test_flags_align_with_tensor_list(self):
        h = self._header()
        assert len(af.quantized_tensor_flags(h)) == len(af.tensor_element_counts(h))

    def test_norm_vectors_are_not_quantized(self):
        h = self._header()
        flags = af.quantized_tensor_flags(h)
        counts = af.tensor_element_counts(h)
        # Every 1D norm vector has exactly `dim` elements and must be fp32.
        for n, q in zip(counts, flags):
            if not q:
                assert n == h.dim

    def test_int8_round_trips(self, tmp_path):
        h = self._header()
        out = tmp_path / "m-int8.bin"
        size = af.write_model_int8(str(out), h, self._tensors(h), self._vocab(h))
        assert size == out.stat().st_size
        parsed = af.validate(str(out))
        assert parsed.quant == af.QUANT_INT8
        assert parsed.vocab_size == h.vocab_size

    def test_fp32_still_round_trips(self, tmp_path):
        h = self._header()
        flat = [v for t in self._tensors(h) for v in t]
        out = tmp_path / "m-fp32.bin"
        af.write_model(str(out), h, flat, self._vocab(h))
        assert af.validate(str(out)).quant == af.QUANT_FP32

    def test_int8_is_about_four_times_smaller(self, tmp_path):
        h = self._header()
        tensors = self._tensors(h)
        f32 = tmp_path / "a.bin"
        i8 = tmp_path / "b.bin"
        af.write_model(str(f32), h, [v for t in tensors for v in t], self._vocab(h))
        af.write_model_int8(str(i8), h, tensors, self._vocab(h))
        # Not exactly 4x: norm vectors stay fp32 and each matrix adds a scale.
        assert i8.stat().st_size < f32.stat().st_size / 3

    def test_write_model_rejects_non_fp32(self, tmp_path):
        h = self._header(quant=af.QUANT_INT8)
        flat = [v for t in self._tensors(h) for v in t]
        with pytest.raises(ValueError, match="fp32 path"):
            af.write_model(str(tmp_path / "x.bin"), h, flat, self._vocab(h))

    def test_validate_rejects_unknown_quant_mode(self, tmp_path):
        h = self._header()
        out = tmp_path / "m.bin"
        af.write_model(str(out), h, [v for t in self._tensors(h) for v in t],
                       self._vocab(h))
        raw = bytearray(out.read_bytes())
        raw[36:40] = (7).to_bytes(4, "little")   # quant field -> nonsense
        out.write_bytes(bytes(raw))
        with pytest.raises(ValueError, match="unsupported quant"):
            af.validate(str(out))
