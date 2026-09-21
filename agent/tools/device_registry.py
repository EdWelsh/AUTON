"""Identify a PCI device from the ingested registry — a lookup, never a guess.

A model asked to name `8086:100e` produces something plausible. Plausible is the
whole problem: a phantom device id with a driver decision attached is worse than
no answer, because nothing downstream can tell it from a real one. So this is a
table lookup with provenance, and every answer cites the document it came from.

Three outcomes, because two would lie:

    IDENTIFIED   the registry lists it
    UNKNOWN      the registry was read and does not list it
    UNAVAILABLE  no registry was read at all

The last is the one that matters on a fresh checkout. `.cache/vendor/` is
gitignored, so a clone has no registry, and collapsing UNAVAILABLE into UNKNOWN
would report every device in the world as unlisted. Anything built on that —
a build gate, say — would then refuse every build for a reason that is false.

    python agent/tools/device_registry.py --identify 8086:100e
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

VENDOR = "pci-sig"
DOCUMENT = "pci-ids"


class Outcome(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class Identification:
    """One answer, with the document that supports it.

    `document_revision` and `sha256` travel with the fact for the same reason
    `Record` carries them: an identification that cannot say which revision of
    pci.ids it came from cannot be re-checked when the registry is updated.
    """
    device_id: str
    outcome: Outcome
    title: str = ""
    vendor: str = ""
    document_id: str = ""
    document_revision: str = ""
    sha256: str = ""
    reason: str = ""

    def __bool__(self) -> bool:
        return self.outcome is Outcome.IDENTIFIED

    def describe(self) -> str:
        if self.outcome is Outcome.IDENTIFIED:
            return f"{self.title} [{self.document_id} {self.document_revision}]"
        return self.reason


@lru_cache(maxsize=1)
def _index() -> tuple[dict[str, object], str]:
    """Parse the registry once. 21,564 devices re-parsed per lookup would make
    a gate that checks a handful of ids noticeably slow for no reason."""
    from vendor_ingest import ingest

    records, report = ingest(VENDOR, DOCUMENT)
    return {r.key: r for r in records}, report.get("document_revision", "unknown")


def identify(device_id: str) -> Identification:
    key = device_id.strip().lower()
    try:
        index, revision = _index()
    except ImportError as exc:
        return Identification(key, Outcome.UNAVAILABLE,
                              reason=f"vendor_ingest not importable: {exc}")
    except Exception as exc:
        # Registry not fetched, or cached payload unreadable. Not knowing is a
        # different state from knowing it is absent, and the caller decides what
        # to do about it.
        return Identification(
            key, Outcome.UNAVAILABLE,
            reason=(f"no {VENDOR}/{DOCUMENT} registry cached "
                    f"({str(exc).splitlines()[0]}); run vendor_fetch.py to "
                    f"populate .cache/vendor/"))

    record = index.get(key)
    if record is None:
        return Identification(
            key, Outcome.UNKNOWN, document_id=DOCUMENT,
            document_revision=revision,
            reason=f"not listed in {DOCUMENT} {revision}")
    return Identification(
        key, Outcome.IDENTIFIED, title=record.title, vendor=record.vendor,
        document_id=record.document_id,
        document_revision=record.document_revision, sha256=record.sha256)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--identify", metavar="VVVV:DDDD", required=True)
    args = ap.parse_args(argv)

    ident = identify(args.identify)
    print(f"{ident.device_id}: {ident.outcome.value}")
    if ident:
        print(f"  {ident.title}")
        print(f"  from {ident.document_id} rev {ident.document_revision}")
        print(f"  sha256 {ident.sha256[:16]}…")
    else:
        print(f"  {ident.reason}")
    return 0 if ident else 1


if __name__ == "__main__":
    raise SystemExit(main())
