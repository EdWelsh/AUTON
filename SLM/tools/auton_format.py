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
# v2: the vocabulary carries <sep> (id 4), which divides a question from its
# answer. A v1 model has no such token, so a v2 kernel prompting with <sep>
# would feed it an id that means something else entirely — a silently wrong
# model rather than a load error. The kernel rejects any version but its own.
VERSION = 2
QUANT_FP32 = 0
QUANT_INT8 = 1


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


# Which tensors, in the documented order, are 2D weight matrices. Mirrors the
# kernel's loader and quantize.py's rule (2D float tensors are quantized, 1D
# norm vectors pass through). Both sides must agree exactly or the int8 stream
# is parsed at the wrong offsets.
def quantized_tensor_flags(header: FlatHeader) -> list[bool]:
    """True where a tensor is a 2D matrix (quantized), False for 1D norms."""
    flags = [True]                     # token embedding
    for _ in range(header.n_layers):
        flags += [False,               # rms_att
                  True, True, True, True,   # wq wk wv wo
                  False,               # rms_ffn
                  True, True, True]    # w1 w2 w3
    flags.append(False)                # final rms_norm
    return flags


def write_model_int8(
    path: str,
    header: FlatHeader,
    tensors: list[list[float]],
    vocab: list[tuple[float, bytes]],
) -> int:
    """Write an int8 flat model: per-tensor scale then int8 codes.

    ``tensors`` is the tensor list in documented order, each already flattened.
    2D matrices are quantized symmetrically per tensor (matching
    SLM/scripts/quantize.py); 1D norm vectors are written as fp32 because
    quantizing a per-channel scale vector costs accuracy for almost no bytes.
    """
    import array
    import struct as _struct

    flags = quantized_tensor_flags(header)
    if len(tensors) != len(flags):
        raise ValueError(f"expected {len(flags)} tensors, got {len(tensors)}")

    total = sum(len(t) for t in tensors)
    if total != weight_element_count(header):
        raise ValueError(f"weight count {total} != expected {weight_element_count(header)}")

    max_token_len = max((len(b) for _, b in vocab), default=0)
    with open(path, "wb") as f:
        hdr = FlatHeader(**{**header.__dict__, "quant": QUANT_INT8})
        f.write(hdr.pack())
        for values, is_q in zip(tensors, flags):
            if not is_q:
                f.write(array.array("f", values).tobytes())
                continue
            amax = max((abs(v) for v in values), default=0.0)
            scale = (amax / 127.0) if amax > 0 else 1.0
            f.write(_struct.pack("<f", scale))
            codes = array.array("b", (
                max(-128, min(127, int(round(v / scale)))) for v in values
            ))
            f.write(codes.tobytes())
        f.write(_struct.pack("<I", max_token_len))
        for score, b in vocab:
            f.write(_struct.pack("<fI", score, len(b)))
            f.write(b)
        return f.tell()


def tensor_element_counts(h: FlatHeader) -> list[int]:
    """Element count per tensor, in the documented order."""
    hd = h.dim // h.n_heads
    counts = [h.vocab_size * h.dim]
    for _ in range(h.n_layers):
        counts += [h.dim,
                   h.n_heads * hd * h.dim,
                   h.n_kv_heads * hd * h.dim,
                   h.n_kv_heads * hd * h.dim,
                   h.dim * h.n_heads * hd,
                   h.dim,
                   h.hidden_dim * h.dim,
                   h.dim * h.hidden_dim,
                   h.hidden_dim * h.dim]
    counts.append(h.dim)
    return counts


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
        raise ValueError("write_model is the fp32 path; use write_model_int8")

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
    if header.quant == QUANT_INT8:
        # Per quantized tensor: 4-byte scale + 1 byte per element. 1D norm
        # vectors stay fp32 at 4 bytes each.
        flags = quantized_tensor_flags(header)
        sizes = tensor_element_counts(header)
        weight_bytes = sum(
            (4 + n) if q else (n * 4) for n, q in zip(sizes, flags)
        )
    elif header.quant == QUANT_FP32:
        weight_bytes = weight_element_count(header) * 4
    else:
        raise ValueError(f"unsupported quant mode {header.quant}")
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
