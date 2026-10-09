"""Inside the vmhost container: turn an exported rootfs into an initramfs and boot it.

    boot.py --rootfs /in/rootfs.tar --spec /in/spec.json --forward 8080:80 [--seconds N]

The guest's init (busybox, static) mounts the pseudo filesystems, loads virtio_net,
configures QEMU user networking (10.0.2.15, gateway 10.0.2.2) and execs the image's
entrypoint. Guest serial goes to stdout, so the caller sees the application's logs.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

VM = Path("/opt/vm")
INIT = """#!/.auton/busybox sh
B=/.auton/busybox
$B mkdir -p /proc /sys /dev /tmp
$B mount -t proc proc /proc; $B mount -t sysfs sys /sys; $B mount -t devtmpfs dev /dev
for m in failover net_failover virtio_net; do $B insmod /.auton/$m.ko; done
$B ip link set lo up; $B ip link set eth0 up
$B ip addr add 10.0.2.15/24 dev eth0; $B ip route add default via 10.0.2.2
echo "AUTON-VM: network up"
cd {cwd}
{env}
{cmd}
echo "AUTON-VM: application exited $?"
$B poweroff -f
"""


def build_initramfs(rootfs: Path, spec: dict, out: Path) -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        subprocess.run(["tar", "-xf", str(rootfs), "-C", str(root), "--exclude=dev/*"], check=True)
        aut = root / ".auton"
        aut.mkdir(exist_ok=True)
        for f in ("busybox", "failover.ko", "net_failover.ko", "virtio_net.ko"):
            (aut / f).write_bytes((VM / f).read_bytes())
        (aut / "busybox").chmod(0o755)
        argv = (spec.get("entrypoint") or []) + (spec.get("cmd") or [])
        if not argv:
            raise SystemExit("the image declares no entrypoint or command")
        env = "\n".join(f"export {shlex.quote(e)}" for e in spec.get("env") or [])
        init = INIT.format(cwd=shlex.quote(spec.get("cwd") or "/"), env=env,
                           cmd=" ".join(shlex.quote(a) for a in argv))
        (root / "init").write_text(init)
        (root / "init").chmod(0o755)
        find = subprocess.Popen(["find", ".", "-print0"], cwd=root, stdout=subprocess.PIPE)
        cpio = subprocess.Popen(["cpio", "--null", "-o", "-H", "newc", "--quiet"], cwd=root,
                                stdin=find.stdout, stdout=subprocess.PIPE)
        with out.open("wb") as fh:
            subprocess.run(["gzip", "-1"], stdin=cpio.stdout, stdout=fh, check=True)
        if cpio.wait() or find.wait():
            raise SystemExit("could not pack the initramfs")


def qemu_cmd(initrd: Path, forwards: list[str], memory: int) -> list[str]:
    arch = platform.machine()
    kvm = os.access("/dev/kvm", os.R_OK | os.W_OK)
    hostfwd = "".join(f",hostfwd=tcp::{f.split(':')[0]}-:{f.split(':')[1]}" for f in forwards)
    if arch in ("aarch64", "arm64"):
        base = ["qemu-system-aarch64", "-M", "virt", "-cpu", "host" if kvm else "max"]
        console = "console=ttyAMA0"
    else:
        base = ["qemu-system-x86_64", "-M", "q35", "-cpu", "host" if kvm else "max"]
        console = "console=ttyS0"
    return [*base, *(["-accel", "kvm"] if kvm else ["-accel", "tcg"]), "-m", str(memory),
            "-nographic", "-no-reboot", "-kernel", str(VM / "kernel"), "-initrd", str(initrd),
            "-append", f"{console} panic=-1 quiet", "-netdev", f"user,id=n0{hostfwd}",
            "-device", "virtio-net-pci,netdev=n0"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rootfs", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--forward", action="append", default=[], help="HOST:GUEST tcp")
    ap.add_argument("--memory", type=int, default=1024)
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text())
    initrd = Path(tempfile.mkdtemp()) / "initramfs.gz"
    build_initramfs(Path(a.rootfs), spec, initrd)
    cmd = qemu_cmd(initrd, a.forward, a.memory)
    print("AUTON-VM: " + ("kvm" if "kvm" in cmd else "tcg (software emulation)"), flush=True)
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    sys.exit(main())
