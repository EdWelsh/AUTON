"""Probe a packaged application booted as a virtual machine (w23 C3).

    python agent/tools/vm_probe.py --image <tag> --probe <probe.yaml>

The same declaration and rubric as `app_probe.py`, on the second substrate of D-A1
("both, container first"). The image's filesystem is exported, packed into an
initramfs and booted under QEMU inside the `auton-vmhost` container (KVM when
/dev/kvm exists, software emulation otherwise). Checks reach the guest only
through a forwarded port, from a client that is not the guest; `exec` checks have no
equivalent in a guest with no agent inside it and are refused rather than faked.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app_probe import (EXIT_FAILED, EXIT_REFUSED, EXIT_WORKED, ProbeError, Verdict,  # noqa: E402
                       _docker, judge, load_probe)

HOST_DIR = Path(__file__).resolve().parent / "vmhost"


def _host_tag() -> str:
    """Named by the content of vmhost/, so an edit to it rebuilds the host."""
    import hashlib
    h = hashlib.sha256()
    for f in sorted(HOST_DIR.iterdir()):
        h.update(f.name.encode() + f.read_bytes())
    return f"auton-vmhost:{h.hexdigest()[:12]}"


HOST_IMAGE = _host_tag()


def guest_spec(inspect: dict) -> dict:
    """What to exec in the guest, from `docker inspect` of the image. Pure."""
    cfg = inspect.get("Config") or {}
    return {"entrypoint": cfg.get("Entrypoint") or [], "cmd": cfg.get("Cmd") or [],
            "env": cfg.get("Env") or [], "cwd": cfg.get("WorkingDir") or "/"}


def forwards(spec: dict, base: int) -> list[tuple[int, int]]:
    """(host, guest) for every port the probe checks, distinct host ports. Pure."""
    guest = sorted({int(c["port"]) for c in spec["checks"] if c.get("port") is not None})
    return [(base + i, g) for i, g in enumerate(guest)]


def refuse_unsupported(spec: dict) -> None:
    for c in spec["checks"]:
        if c["kind"] == "exec":
            raise ProbeError("an exec check has no equivalent in a VM guest with no agent "
                             "inside it; declare an http or tcp check for this substrate")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ensure_host() -> None:
    if _docker("image", "inspect", HOST_IMAGE).returncode == 0:
        return
    r = subprocess.run(["docker", "build", "-q", "-t", HOST_IMAGE, str(HOST_DIR)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ProbeError(f"could not build {HOST_IMAGE}: {r.stderr.strip()[:300]}")


def _check(check: dict, host_port: int) -> dict:
    import urllib.error
    import urllib.request
    try:
        if check["kind"] == "http":
            url = f"http://127.0.0.1:{host_port}{check.get('path', '/')}"
            try:
                r = urllib.request.urlopen(url, timeout=10)
                return {"status": r.status, "body": r.read(4096).decode("utf-8", "replace")}
            except urllib.error.HTTPError as e:
                return {"status": e.code, "body": e.read(4096).decode("utf-8", "replace")}
        s = socket.create_connection(("127.0.0.1", host_port), timeout=10)
        if check.get("send"):
            s.sendall(check["send"].encode())
        s.settimeout(5)
        data = b""
        if check.get("expect"):
            try:
                data = s.recv(4096)
            except socket.timeout:
                pass
        return {"connected": True, "body": data.decode("utf-8", "replace")}
    except Exception as e:  # a failed check is a verdict, not a crash
        return {"error": f"{type(e).__name__}: {e}"}


def probe_vm(image: str, spec: dict) -> Verdict:
    refuse_unsupported(spec)
    _ensure_host()
    ins = _docker("image", "inspect", image)
    if ins.returncode != 0:
        raise ProbeError(f"no such image {image}")
    gspec = guest_spec(json.loads(ins.stdout)[0])
    run = uuid.uuid4().hex[:10]
    base = _free_port()
    fwd = forwards(spec, base)
    ports = {g: h for h, g in fwd}
    markers = spec.get("refusal_markers") or []
    work = Path(tempfile.mkdtemp(prefix="auton-vm-"))
    holder, vm = f"auton-vmroot-{run}", f"auton-vm-{run}"
    try:
        _docker("create", "--name", holder, image)
        with (work / "rootfs.tar").open("wb") as fh:
            if subprocess.run(["docker", "export", holder], stdout=fh).returncode:
                raise ProbeError("could not export the image filesystem")
        (work / "spec.json").write_text(json.dumps(gspec))
        args = ["run", "-d", "--name", vm, "-v", f"{work}:/in:ro"]
        for h, _g in fwd:
            args += ["-p", f"127.0.0.1:{h}:{h}"]
        args += [HOST_IMAGE, "--rootfs", "/in/rootfs.tar", "--spec", "/in/spec.json"]
        for h, g in fwd:
            args += ["--forward", f"{h}:{g}"]
        if (r := _docker(*args)).returncode != 0:
            raise ProbeError(f"the VM host would not run: {r.stderr.strip()[:300]}")
        return _grade(vm, spec, ports, markers)
    finally:
        _docker("rm", "-f", "-v", holder, vm)
        subprocess.run(["rm", "-rf", str(work)])


def _app_tail(logs: str) -> str:
    """The application's last lines, without the guest kernel's own noise. Pure."""
    own = [ln.strip() for ln in logs.splitlines() if ln.strip() and not ln.startswith("[")]
    return " | ".join(own[-3:]) or "(none)"


def _grade(vm: str, spec: dict, ports: dict[int, int], markers: list[str]) -> Verdict:
    # Emulation is slow: a cold guest needs minutes, not seconds.
    deadline = time.monotonic() + int(spec.get("vm_start_timeout_s",
                                               max(180, 3 * int(spec.get("start_timeout_s", 60)))))
    while True:
        out = _docker("logs", "--tail", "60", vm)
        logs = out.stdout + out.stderr
        state = _docker("inspect", "--format", "{{.State.Status}}", vm).stdout.strip()
        if state != "running":
            hit = next((m for m in markers if m in logs), None)
            if hit:
                return Verdict(EXIT_REFUSED, "HONESTLY REFUSED " +
                               next(ln for ln in logs.splitlines() if hit in ln).strip())
            return Verdict(EXIT_FAILED, "FAILED           the VM stopped before answering; "
                                        f"last log: {_app_tail(logs)}")
        failures = [f for c in spec["checks"]
                    if (f := judge(c, _check(c, ports[int(c["port"])])))]
        if not failures:
            return Verdict(EXIT_WORKED, f"WORKED           {len(spec['checks'])} check(s) "
                                        f"passed from outside the guest (VM)")
        if time.monotonic() > deadline:
            return Verdict(EXIT_FAILED, f"FAILED           {failures[0]}")
        time.sleep(5)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True)
    ap.add_argument("--probe", required=True)
    a = ap.parse_args(argv)
    try:
        v = probe_vm(a.image, load_probe(Path(a.probe)))
    except (ProbeError, subprocess.TimeoutExpired) as exc:
        print(f"HONESTLY REFUSED the probe could not run: {exc}")
        return EXIT_REFUSED
    print(v.line)
    return v.code


if __name__ == "__main__":
    raise SystemExit(main())
