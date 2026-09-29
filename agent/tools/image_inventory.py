"""What is actually inside a built image (application-to-environment A8).

    python agent/tools/image_inventory.py <image>

Read from the exported filesystem, not by running anything in the image: an
image with no shell (distroless, scratch) has an inventory too, and running a
subject's image to list its files would be executing it for no reason.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tarfile

SONAME = re.compile(r"^lib[A-Za-z0-9_+.-]*?\.so(\.[0-9]+)*$")
BIN_DIRS = ("bin/", "sbin/", "usr/bin/", "usr/sbin/", "usr/local/bin/")


def inventory_from_names(names: list[str]) -> dict[str, list[str]]:
    """Sonames under any lib/lib64/lib32 directory, and programs directly in a
    bin directory. Symlinks count: `libz.so.1 -> libz.so.1.2.13` is how a
    soname is usually present."""
    libs, execs = set(), set()
    for raw in names:
        name = raw.strip("/").removeprefix("./")
        parts = name.split("/")
        base = parts[-1]
        if SONAME.match(base) and any(p in ("lib", "lib64", "lib32") for p in parts[:-1]):
            libs.add(base)
        if "/".join(parts[:-1]) + "/" in BIN_DIRS:
            execs.add(base)
    return {"libs": sorted(libs), "execs": sorted(execs)}


def inventory(image: str) -> dict[str, list[str]]:
    cid = subprocess.run(["docker", "create", image], capture_output=True, text=True,
                         check=True).stdout.strip()
    try:
        proc = subprocess.Popen(["docker", "export", cid], stdout=subprocess.PIPE)
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            names = [m.name for m in tar]
        proc.wait()
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True)
    return inventory_from_names(names)


if __name__ == "__main__":
    print(json.dumps(inventory(sys.argv[1]), indent=2))
