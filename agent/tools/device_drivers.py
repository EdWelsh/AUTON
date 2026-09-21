"""Which driver binds to which device, and what capability that supplies.

This table used to live in `SLM/tools/build_corpus.py`, which is corpus
tooling. The factory read its device knowledge from the corpus generator, so a
change made to improve a training set would silently change what got built.
The dependency now runs the other way: this is the source, and the corpus reads
it.

The join is on **role**, not on device id. A microVM's network device is
`virtio-mmio:1` — there is no vendor:device pair anywhere in the transport — so
a lookup keyed on `vvvv:dddd` cannot see it at all. A target already records
`role` for every device, which is the key that works on both transports.
"""

from __future__ import annotations

# (vendor, device, description, driver). PCI ids only; the MMIO and modern
# virtio cases are handled by transport below, because they are computed from a
# device type rather than enumerated.
PCI_DEVICE_DRIVERS: tuple[tuple[str, str, str, str], ...] = (
    ("8086", "100e", "Intel 82540EM Gigabit Ethernet (e1000)", "e1000"),
    ("8086", "10d3", "Intel 82574L Gigabit Ethernet (e1000e)", "e1000e"),
    ("1af4", "1000", "Virtio network device (transitional)", "virtio-net"),
    ("1af4", "1001", "Virtio block device (transitional)", "virtio-blk"),
)

# Which capability a driver supplies once bound.
DRIVER_CAPS: dict[str, set[str]] = {
    "e1000": {"net"},
    "e1000e": {"net"},
    "virtio-net": {"net"},
    "virtio-blk": {"fs"},
}

# VIRTIO device type -> driver, for both virtio transports. Modern virtio-pci
# ids are 0x1040 + type (VIRTIO 1.2 §4.1.2), and MMIO carries the type in a
# register with no id at all, so one table covers both rather than enumerating
# a PCI pair per type.
VIRTIO_TYPE_DRIVERS: dict[int, str] = {
    1: "virtio-net",
    2: "virtio-blk",
}

# Which driver capability each target device role needs. A role with no entry
# needs no driver — a host bridge is on the bus and nothing binds to it.
ROLE_CAPS: dict[str, str] = {
    "network": "net",
    "storage": "fs",
}


def driver_for_device(device_id: str) -> str | None:
    """Resolve a device id to a driver name, on either transport.

    Returns None when nothing in the table drives it. That is a real answer —
    a device present on the machine with no driver is the case a build should
    refuse rather than paper over.
    """
    ident = device_id.strip().lower()

    if ident.startswith("virtio-mmio:"):
        try:
            return VIRTIO_TYPE_DRIVERS.get(int(ident.split(":", 1)[1]))
        except ValueError:
            return None

    for vendor, device, _desc, driver in PCI_DEVICE_DRIVERS:
        if ident == f"{vendor}:{device}":
            return driver

    # Modern virtio-pci: 0x1040 + device type. Enumerating every pair would
    # duplicate VIRTIO_TYPE_DRIVERS and drift from it.
    if ident.startswith("1af4:"):
        try:
            code = int(ident.split(":", 1)[1], 16)
        except ValueError:
            return None
        if 0x1040 <= code <= 0x107F:
            return VIRTIO_TYPE_DRIVERS.get(code - 0x1040)
    return None


def capabilities_for(driver: str) -> set[str]:
    return set(DRIVER_CAPS.get(driver, ()))
