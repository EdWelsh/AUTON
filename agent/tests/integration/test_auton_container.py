"""The AUTON kernel as a container in Rancher/Docker (w23): build the kernel base ISO on the
host, package it with scripts/auton-container.sh, boot it, and talk to its monitor from outside."""
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from qmp_probe import parse_address  # noqa: E402

SH = ROOT / "scripts" / "auton-container.sh"


def test_a_host_port_address_is_tcp_and_a_path_is_a_unix_socket():
    assert parse_address("127.0.0.1:32768") == ("127.0.0.1", 32768)
    assert parse_address("/tmp/qmp.sock") == (None, 0)
    assert parse_address("relative.sock") == (None, 0)


@pytest.mark.skipif(not shutil.which("docker") or not shutil.which("x86_64-elf-gcc")
                    or subprocess.run(["docker", "info"], capture_output=True).returncode != 0,
                    reason="needs Docker and the x86_64-elf toolchain")
def test_the_kernel_base_boots_in_a_container_and_its_monitor_answers_from_outside(tmp_path):
    tree = tmp_path / "kb"
    subprocess.run([str(ROOT / "scripts/kernel-base.sh"), str(tree)], check=True, capture_output=True)
    mk = ["make", "-C", str(tree), "iso", "CC=x86_64-elf-gcc"]
    if shutil.which("i686-elf-grub-mkrescue"):
        mk.append("GRUB_MKRESCUE=i686-elf-grub-mkrescue")
    subprocess.run(mk, check=True, capture_output=True)
    name = f"auton-test-{tmp_path.name[-8:]}"
    try:
        subprocess.run([str(SH), "build", str(tree / "build/auton.iso"), "test"], check=True, capture_output=True)
        out = subprocess.run([str(SH), "run", "test", name], check=True, capture_output=True, text=True).stdout
        qmp = out.split("qmp=")[1].split()[0]
        assert subprocess.run([str(SH), "wait", name, r"\[BOOT\] OK", "180"]).returncode == 0
        host, port = parse_address(qmp)
        s = socket.create_connection((host, port), timeout=20)
        s.recv(65536)
        s.sendall(b'{"execute":"qmp_capabilities"}\n{"execute":"query-status"}\n')
        time.sleep(1)
        data = s.recv(65536).decode()
        assert '"running"' in data
    finally:
        subprocess.run([str(SH), "stop", name], capture_output=True)
