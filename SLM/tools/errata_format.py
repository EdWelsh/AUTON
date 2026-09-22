"""The errata module format: `errata.bin`, loaded by the kernel beside the model.

Hardware-truth H13. A running image answers "is this machine safe?" from data it
carries, keyed by its own silicon identity (H5). The answers are precomputed on
the host by `agent/tools/errata_table.py`, whose applicability logic (processor
lines, "Plan Fix" meaning UNKNOWN when microcode was not read) must exist
exactly once. The kernel only looks them up.

**Why a separate module and not a model-file section** (the PRD's Open Question
3): errata change on a vendor's schedule, not a training schedule. A second boot
module can be replaced without retraining or re-exporting the model, and the
model file's exact-version contract (auton_format.VERSION) is untouched.

LAYOUT (little-endian, no padding beyond what is stated):

    magic         u32   0x52524541  ("AERR")
    version       u32   1           exact match, as the model file
    doc_count     u32
    for each document:
        id_len    u16,  id   [id_len]    e.g. "intel/intel-spec-update"
        rev_len   u16,  rev  [rev_len]   the document's own revision
    key_count     u32
    keys, sorted ascending by (vendor, family, model, stepping), 16 bytes each:
        vendor    u8    1 = GenuineIntel, 2 = AuthenticAMD
        stepping  u8
        family    u16
        model     u16
        _pad      u16
        first     u32   index of the key's first record
        count     u32
    rec_count     u32
    records, 12 bytes each:
        text_off  u32   offset into the pool: "<erratum id>: <title>"
        verdict   u8    0 = does not apply, 1 = applies, 2 = unknown
        status    u8    0 unknown, 1 No Fix, 2 Fixed, 3 Plan Fix, 4 Doc, 5 N/A
        doc       u8    index into the documents above
        _pad      u8
        page      u16   0 when the document gave none
        _pad      u16
    pool_len      u32
    pool          [pool_len]  NUL-separated UTF-8
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = 0x52524541
VERSION = 1

VENDORS = {"GenuineIntel": 1, "AuthenticAMD": 2}
VERDICTS = {"NO": 0, "YES": 1, "UNKNOWN": 2}
STATUSES = {"no fix": 1, "fixed": 2, "plan fix": 3, "planned fix": 3, "doc": 4, "n/a": 5}


class ErrataFormatError(Exception):
    pass


@dataclass(frozen=True, order=True)
class Key:
    vendor: int
    family: int
    model: int
    stepping: int

    def sort_key(self) -> tuple[int, int, int, int]:
        return (self.vendor, self.family, self.model, self.stepping)


@dataclass(frozen=True)
class Rec:
    text: str
    verdict: int
    status: int
    doc: int
    page: int


def pack(docs: list[tuple[str, str]], table: dict[Key, list[Rec]]) -> bytes:
    out = bytearray(struct.pack("<III", MAGIC, VERSION, len(docs)))
    for doc_id, rev in docs:
        for s in (doc_id, rev):
            b = s.encode()
            out += struct.pack("<H", len(b)) + b
    keys = sorted(table, key=Key.sort_key)
    pool = bytearray()
    offsets: dict[str, int] = {}
    records = bytearray()
    key_bytes = bytearray()
    n = 0
    for k in keys:
        recs = table[k]
        key_bytes += struct.pack("<BBHHHII", k.vendor, k.stepping, k.family, k.model, 0,
                                 n, len(recs))
        for r in recs:
            if r.text not in offsets:
                offsets[r.text] = len(pool)
                pool += r.text.encode() + b"\0"
            records += struct.pack("<IBBBBHH", offsets[r.text], r.verdict, r.status, r.doc, 0,
                                   r.page, 0)
            n += 1
    out += struct.pack("<I", len(keys)) + key_bytes
    out += struct.pack("<I", n) + records
    out += struct.pack("<I", len(pool)) + pool
    return bytes(out)


def unpack(data: bytes) -> tuple[list[tuple[str, str]], dict[Key, list[Rec]]]:
    def need(at: int, n: int) -> None:
        if at + n > len(data):
            raise ErrataFormatError(f"truncated at byte {at}")

    need(0, 12)
    magic, version, ndocs = struct.unpack_from("<III", data, 0)
    if magic != MAGIC:
        raise ErrataFormatError("not an errata module (bad magic)")
    if version != VERSION:
        raise ErrataFormatError(f"errata module version {version}, reader is {VERSION}")
    at = 12
    docs = []
    for _ in range(ndocs):
        pair = []
        for _ in range(2):
            need(at, 2)
            (n,) = struct.unpack_from("<H", data, at)
            need(at + 2, n)
            pair.append(data[at + 2:at + 2 + n].decode())
            at += 2 + n
        docs.append((pair[0], pair[1]))
    need(at, 4)
    (nkeys,) = struct.unpack_from("<I", data, at)
    at += 4
    need(at, nkeys * 16)
    raw_keys = [struct.unpack_from("<BBHHHII", data, at + 16 * i) for i in range(nkeys)]
    at += nkeys * 16
    need(at, 4)
    (nrec,) = struct.unpack_from("<I", data, at)
    at += 4
    need(at, nrec * 12)
    raw_recs = [struct.unpack_from("<IBBBBHH", data, at + 12 * i) for i in range(nrec)]
    at += nrec * 12
    need(at, 4)
    (pool_len,) = struct.unpack_from("<I", data, at)
    need(at + 4, pool_len)
    pool = data[at + 4:at + 4 + pool_len]

    def text(off: int) -> str:
        if off >= len(pool):
            raise ErrataFormatError("record text offset past the pool")
        return pool[off:pool.index(b"\0", off)].decode()

    table: dict[Key, list[Rec]] = {}
    for vendor, stepping, family, model, _pad, first, count in raw_keys:
        if first + count > nrec:
            raise ErrataFormatError("key points past the records")
        table[Key(vendor, family, model, stepping)] = [
            Rec(text(off), verdict, status, doc, page)
            for off, verdict, status, doc, _p, page, _q in raw_recs[first:first + count]]
    return docs, table
