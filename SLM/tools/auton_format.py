"""AUTON flat model format — single source of truth for the byte layout shared
between the host exporter (``export_auton.py``) and the in-kernel loader
(``kernel/slm/neural/loader.c``). llama2.c-style: a fixed header followed by
weights in a fixed tensor order, then the tokenizer vocab.

The kernel runs the model in place from the boot module, so the layout must be
trivially parseable: little-endian, no padding beyond what is stated.

HEADER (all uint32, little-endian):
    magic        0x4E4F5455  ("UTON" little-endian of bytes 'U','T','O','N')
    version      1
    dim          hidden size
    hidden_dim   FFN intermediate size
    n_layers
    n_heads
    n_kv_heads
    vocab_size
    seq_len      max context
    quant        0 = fp32 (only fp32 is supported by the MVP kernel loader)

WEIGHTS (float32, in this exact order; head_dim = dim / n_heads):
    token_embedding              [vocab_size, dim]
    for each layer: rms_att      [dim]
    for each layer: wq           [n_heads*head_dim, dim]
    for each layer: wk           [n_kv_heads*head_dim, dim]
    for each layer: wv           [n_kv_heads*head_dim, dim]
    for each layer: wo           [dim, n_heads*head_dim]
    for each layer: rms_ffn      [dim]
    for each layer: w1 (gate)    [hidden_dim, dim]
    for each layer: w2 (down)    [dim, hidden_dim]
    for each layer: w3 (up)      [hidden_dim, dim]
    final rms_norm               [dim]
  (input/output embeddings are tied, so there is no separate lm_head.)

TOKENIZER (after weights):
    max_token_len    uint32
    for each of vocab_size tokens:
        score   float32
        length  uint32
        bytes   [length]  (UTF-8, no NUL)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = 0x4E4F5455
VERSION = 1
QUANT_FP32 = 0


@dataclass(frozen=True)
class FlatHeader:
    dim: int
    hidden_dim: int
    n_layers: int
    n_heads: int
    n_kv_heads: int
    vocab_size: int
    seq_len: int
    quant: int = QUANT_FP32

    @property
    def head_dim(self) -> int:
        return self.dim // self.n_heads

    def pack(self) -> bytes:
        return struct.pack(
            "<10I",
            MAGIC,
            VERSION,
            self.dim,
            self.hidden_dim,
            self.n_layers,
            self.n_heads,
            self.n_kv_heads,
            self.vocab_size,
            self.seq_len,
            self.quant,
        )

    @staticmethod
    def unpack(data: bytes) -> "FlatHeader":
        fields = struct.unpack_from("<10I", data, 0)
        if fields[0] != MAGIC:
            raise ValueError(f"bad magic 0x{fields[0]:08X}, expected 0x{MAGIC:08X}")
        if fields[1] != VERSION:
            raise ValueError(f"unsupported version {fields[1]}")
        return FlatHeader(
            dim=fields[2],
            hidden_dim=fields[3],
            n_layers=fields[4],
            n_heads=fields[5],
            n_kv_heads=fields[6],
            vocab_size=fields[7],
            seq_len=fields[8],
            quant=fields[9],
        )


HEADER_SIZE = 10 * 4


def weight_element_count(h: FlatHeader) -> int:
    """Total number of float32 weight elements, in tensor order."""
    hd = h.head_dim
    per_layer = (
        h.dim                       # rms_att
        + h.n_heads * hd * h.dim    # wq
        + h.n_kv_heads * hd * h.dim  # wk
        + h.n_kv_heads * hd * h.dim  # wv
        + h.dim * h.n_heads * hd    # wo
        + h.dim                     # rms_ffn
        + h.hidden_dim * h.dim      # w1
        + h.dim * h.hidden_dim      # w2
        + h.hidden_dim * h.dim      # w3
    )
    return (
        h.vocab_size * h.dim        # token embedding
        + h.n_layers * per_layer
        + h.dim                     # final rms_norm
    )


def write_model(
    path: str,
    header: FlatHeader,
    weights: list,
    vocab: list[tuple[float, bytes]],
) -> int:
    """Write a flat model file. ``weights`` is a flat float iterable already in
    the documented tensor order. Returns the number of bytes written."""
    import array

    if header.quant != QUANT_FP32:
        raise ValueError("MVP writer supports fp32 only")

    flat = array.array("f", weights)
    if len(flat) != weight_element_count(header):
        raise ValueError(
            f"weight count {len(flat)} != expected {weight_element_count(header)}"
        )

    max_token_len = max((len(b) for _, b in vocab), default=0)
    with open(path, "wb") as f:
        f.write(header.pack())
        f.write(flat.tobytes())
        f.write(struct.pack("<I", max_token_len))
        for score, b in vocab:
            f.write(struct.pack("<fI", score, len(b)))
            f.write(b)
        return f.tell()


def validate(path: str) -> FlatHeader:
    """Re-read a flat file: verify the header and that sizes are consistent.
    Returns the parsed header. Raises ValueError on any mismatch."""
    with open(path, "rb") as f:
        data = f.read()

    header = FlatHeader.unpack(data)
    weight_bytes = weight_element_count(header) * 4
    offset = HEADER_SIZE + weight_bytes
    if offset + 4 > len(data):
        raise ValueError("file truncated before tokenizer section")

    (max_token_len,) = struct.unpack_from("<I", data, offset)
    offset += 4
    for i in range(header.vocab_size):
        if offset + 8 > len(data):
            raise ValueError(f"truncated token table at token {i}")
        _score, length = struct.unpack_from("<fI", data, offset)
        offset += 8
        if length > max_token_len:
            raise ValueError(f"token {i} length {length} exceeds max {max_token_len}")
        offset += length
    if offset != len(data):
        raise ValueError(f"trailing bytes: parsed {offset}, file {len(data)}")
    return header


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inspect/validate an AUTON flat model")
    parser.add_argument("--validate", metavar="FILE", required=True)
    args = parser.parse_args()
    h = validate(args.validate)
    print(f"OK: dim={h.dim} layers={h.n_layers} heads={h.n_heads}/{h.n_kv_heads} "
          f"vocab={h.vocab_size} seq={h.seq_len} quant={h.quant}")
