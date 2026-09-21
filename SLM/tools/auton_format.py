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

DEVICE TABLE (after the tokenizer; v3 and later):
    count            uint32   entries; 0 means the section is present and empty
    revision_len     uint32
    revision         [revision_len]   which registry revision this came from
    for each of count entries, sorted ascending by (bus, vendor, device):
        bus          uint16   0 = PCI, 1 = USB
        vendor       uint16
        device       uint16
        _pad         uint16   keeps the key 8 bytes so a binary search strides
        name_off     uint32   byte offset into the pool below
    pool_len         uint32
    pool             [pool_len]   NUL-separated UTF-8 names

    Binary-searchable where it lies. The kernel maps this file from a boot
    module and runs it in place, so an entry is a fixed 12 bytes and the names
    live in one pool rather than inline — a variable-width entry cannot be
    indexed without walking the whole table.

    The id is two uint16s, not text. `8086:100e` as a string costs nine bytes
    per entry and turns the search into a strcmp.

    A v2 file has no section and that is legal for v2. It is not legal for v3:
    the version is an exact match, so a reader always knows whether to expect
    one. See VERSION below.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = 0x4E4F5455
# v2: the vocabulary carries <sep> (id 4), which divides a question from its
# answer. A v1 model has no such token, so a v2 kernel prompting with <sep>
# would feed it an id that means something else entirely — a silently wrong
# model rather than a load error. The kernel rejects any version but its own.
#
# v3: a device table follows the tokenizer. A v2 reader handed a v3 file would
# parse the table's bytes as further tokenizer entries — the same silently-wrong
# failure the v1->v2 note warns about, which is why the version is an exact
# match rather than a minimum.
VERSION = 3

# Bus codes in a device-table key. Two registries are ingested and both are
# device registries; anything else would need its own code and its own parser.
BUS_PCI = 0
BUS_USB = 1
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
    devices: list["DeviceEntry"] | None = None,
    device_revision: str = "",
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
        f.write(pack_device_table(devices or [], device_revision))
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
    devices: list["DeviceEntry"] | None = None,
    device_revision: str = "",
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
        # Always written, even when empty: a reader must be able to tell "this
        # image knows no devices" from "this file predates the section".
        f.write(pack_device_table(devices or [], device_revision))
        return f.tell()


@dataclass(frozen=True)
class DeviceEntry:
    """One device, as it sits in the table. Sorted by (bus, vendor, device)."""
    bus: int
    vendor: int
    device: int
    name: str

    @property
    def key(self) -> tuple[int, int, int]:
        return (self.bus, self.vendor, self.device)

    def ident(self) -> str:
        return f"{self.vendor:04x}:{self.device:04x}"


DEVICE_ENTRY_SIZE = 12          # bus, vendor, device, pad (u16 x4) + name_off (u32)


def pack_device_table(entries: list[DeviceEntry], revision: str) -> bytes:
    """Serialise the device-table section.

    Refuses an unsorted or duplicated table rather than fixing it quietly: a
    binary search over unsorted keys returns an arbitrary answer, and over
    duplicates returns an arbitrary one of several. Both are a lookup that
    looks like it worked.
    """
    keys = [e.key for e in entries]
    if keys != sorted(keys):
        raise ValueError("device table is not sorted; a binary search over it "
                         "would return arbitrary answers")
    dupes = {k for k in keys if keys.count(k) > 1} if len(keys) != len(set(keys)) else set()
    if dupes:
        first = sorted(dupes)[0]
        raise ValueError(
            f"device table has {len(dupes)} duplicate key(s), first "
            f"{first[1]:04x}:{first[2]:04x}. A binary search cannot say which "
            f"one it found — resolve the registries rather than picking")

    rev = revision.encode("utf-8")
    out = bytearray()
    out += struct.pack("<II", len(entries), len(rev))
    out += rev

    pool = bytearray()
    offsets = []
    for e in entries:
        offsets.append(len(pool))
        pool += e.name.encode("utf-8") + b"\x00"

    for e, off in zip(entries, offsets):
        out += struct.pack("<4HI", e.bus, e.vendor, e.device, 0, off)
    out += struct.pack("<I", len(pool))
    out += pool
    return bytes(out)


def unpack_device_table(data: bytes, offset: int) -> tuple[list[DeviceEntry], str, int]:
    """Read the section back. Returns (entries, revision, end offset).

    Truncation raises ValueError, not struct.error: `validate()` promises
    ValueError on any mismatch, and a struct.error escaping through it means a
    caller catching the documented type misses a corrupt file.
    """
    try:
        return _unpack_device_table(data, offset)
    except (struct.error, IndexError, UnicodeDecodeError) as exc:
        raise ValueError(f"device-table section is truncated or corrupt: {exc}") from exc


def _unpack_device_table(data: bytes, offset: int) -> tuple[list[DeviceEntry], str, int]:
    count, rev_len = struct.unpack_from("<II", data, offset)
    offset += 8
    revision = data[offset:offset + rev_len].decode("utf-8")
    offset += rev_len

    raw = []
    for _ in range(count):
        bus, vendor, device, _pad, name_off = struct.unpack_from("<4HI", data, offset)
        offset += DEVICE_ENTRY_SIZE
        raw.append((bus, vendor, device, name_off))

    (pool_len,) = struct.unpack_from("<I", data, offset)
    offset += 4
    pool = data[offset:offset + pool_len]
    offset += pool_len

    if len(pool) != pool_len:
        raise ValueError(
            f"device-table string pool is {len(pool)} bytes, header says {pool_len}")

    entries = []
    for bus, vendor, device, name_off in raw:
        end = pool.index(b"\x00", name_off)
        entries.append(DeviceEntry(bus, vendor, device,
                                   pool[name_off:end].decode("utf-8")))
    return entries, revision, offset


def lookup(entries: list[DeviceEntry], bus: int, vendor: int,
           device: int) -> DeviceEntry | None:
    """Binary search, the way the kernel will.

    Present here so the host and the kernel search the same sorted order — a
    table the exporter sorts one way and the loader searches another is a
    lookup that silently returns the wrong device.
    """
    import bisect

    keys = [e.key for e in entries]
    i = bisect.bisect_left(keys, (bus, vendor, device))
    if i < len(entries) and entries[i].key == (bus, vendor, device):
        return entries[i]
    return None


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
    if offset == len(data):
        raise ValueError(
            f"no device-table section. Version {VERSION} files carry one after "
            f"the tokenizer — write an empty table rather than omitting it, so "
            f"a reader can tell 'no devices' from 'older format'")

    entries, revision, offset = unpack_device_table(data, offset)
    keys = [e.key for e in entries]
    if keys != sorted(keys):
        raise ValueError("device table is not sorted")
    if len(keys) != len(set(keys)):
        raise ValueError("device table has duplicate keys")
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
