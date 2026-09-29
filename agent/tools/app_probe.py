"""Grade a packaged application from outside it (application-to-environment A10).

    python agent/tools/app_probe.py --image <tag> --probe <probe.yaml>

The rubric `run-intent-probe.sh` uses for kernel images, lifted to applications:

    WORKED           every declared check passed
    HONESTLY REFUSED the application printed a declared refusal marker and stopped
    FAILED           a check failed, or it died, or claimed to start and did not answer

Exit 0, 1, 2 respectively; 2 also when the probe could not run, saying why.

**The probe is outside the application.** It runs on an `--internal` Docker
network — no route anywhere but between the two containers — and every check
comes from a separate sidecar, so a log line reading "started" is never the
image grading itself.

**The declaration is a person's.** `probe.yaml` says what *works* means for
this application, and it is written by the operator, never by an agent: a
model-written success criterion would be the image grading itself one step
removed. It lives outside anything an agent writes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from package_gate import CONFINE, load_bases  # noqa: E402

EXIT_WORKED, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
KINDS = ("http", "tcp", "exec")

# Runs in the sidecar. Prints one JSON line; never raises.
CLIENT = r'''
import json, socket, sys, urllib.request, urllib.error
spec = json.loads(sys.argv[1])
out = {}
try:
    if spec["kind"] == "http":
        url = f"http://app:{spec['port']}{spec.get('path', '/')}"
        try:
            r = urllib.request.urlopen(url, timeout=5)
            out = {"status": r.status, "body": r.read(4096).decode("utf-8", "replace")}
        except urllib.error.HTTPError as e:
            out = {"status": e.code, "body": e.read(4096).decode("utf-8", "replace")}
    elif spec["kind"] == "tcp":
        s = socket.create_connection(("app", spec["port"]), timeout=5)
        if spec.get("send"):
            s.sendall(spec["send"].encode())
        s.settimeout(3)
        data = b""
        if spec.get("expect"):
            try:
                data = s.recv(4096)
            except socket.timeout:
                pass
        out = {"connected": True, "body": data.decode("utf-8", "replace")}
except Exception as e:
    out = {"error": f"{type(e).__name__}: {e}"}
print(json.dumps(out))
'''


class ProbeError(Exception):
    """The probe could not run. Not a verdict on the application."""


@dataclass
class Verdict:
    code: int
    line: str


def load_probe(path: Path) -> dict:
    if not path.is_file():
        raise ProbeError(f"no probe declaration at {path}; what 'works' means is declared "
                         f"by a person, and nothing was")
    data = yaml.safe_load(path.read_text()) or {}
    checks = data.get("checks") or []
    if not checks:
        raise ProbeError(f"{path.name} declares no checks")
    for n, c in enumerate(checks, 1):
        if c.get("kind") not in KINDS:
            raise ProbeError(f"{path.name}: check {n} kind {c.get('kind')!r} is not one of "
                             f"{', '.join(KINDS)}")
    return data


def judge(check: dict, result: dict) -> str | None:
    """None when the check passed, else why not. Pure: tested without Docker."""
    if "error" in result:
        return f"{check['kind']} {check.get('port', '')}: {result['error']}"
    if check["kind"] == "http":
        want = check.get("expect_status", 200)
        if result.get("status") != want:
            return (f"GET :{check['port']}{check.get('path', '/')} returned "
                    f"{result.get('status')}, expected {want}")
        needle = check.get("expect_body_contains")
        if needle and needle not in result.get("body", ""):
            return (f"GET :{check['port']}{check.get('path', '/')} body lacks {needle!r}: "
                    f"{result.get('body', '')[:120]!r}")
    elif check["kind"] == "tcp":
        if check.get("expect") and check["expect"] not in result.get("body", ""):
            return f"tcp :{check['port']} did not answer {check['expect']!r}"
    elif check["kind"] == "exec":
        if result.get("exit") != check.get("expect_exit", 0):
            return (f"exec {' '.join(check['command'])} exited {result.get('exit')}, "
                    f"expected {check.get('expect_exit', 0)}")
    return None


def _docker(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def _state(name: str) -> tuple[str, str]:
    out = _docker("inspect", "--format", "{{.State.Status}} {{.State.ExitCode}}", name).stdout
    parts = out.split()
    return (parts[0], parts[1]) if len(parts) == 2 else ("gone", "?")


def _logs(name: str) -> str:
    r = _docker("logs", "--tail", "40", name)
    return (r.stdout + r.stderr).strip()


def probe(image: str, spec: dict) -> Verdict:
    run = uuid.uuid4().hex[:10]
    net, app = f"auton-probe-{run}", f"auton-probe-app-{run}"
    sidecar = load_bases()["runtime:python-3.12"]
    markers = spec.get("refusal_markers") or []
    if _docker("network", "create", "--internal", net).returncode != 0:
        raise ProbeError("could not create an internal network (is Docker running?)")
    try:
        # CONFINE's --network none is replaced by the internal network.
        confine = [a for a in CONFINE]
        i = confine.index("--network")
        confine[i + 1] = net
        r = _docker("run", "-d", "--name", app, "--network-alias", "app", *confine, image)
        if r.returncode != 0:
            raise ProbeError(f"the image would not run: {r.stderr.strip()[:300]}")
        return _grade(app, net, sidecar, spec, markers)
    finally:
        leftovers = _docker("ps", "-aq", "--filter", f"network={net}").stdout.split()
        _docker("rm", "-f", "-v", app, *leftovers)
        _docker("network", "rm", net)


def _grade(app: str, net: str, sidecar: str, spec: dict, markers: list[str]) -> Verdict:
    deadline = time.monotonic() + int(spec.get("start_timeout_s", 60))
    checks = spec["checks"]
    last = ""
    while True:
        status, code = _state(app)
        if status != "running":
            logs = _logs(app)
            hit = next((m for m in markers if m in logs), None)
            if hit:
                line = next(ln for ln in logs.splitlines() if hit in ln)
                return Verdict(EXIT_REFUSED, f"HONESTLY REFUSED {line.strip()}")
            return Verdict(EXIT_FAILED, f"FAILED           exited {code} before answering; "
                                        f"last log: {logs.splitlines()[-1] if logs else '(none)'}")
        failures = [f for c in checks if (f := judge(c, _run_check(app, net, sidecar, c)))]
        if not failures:
            return Verdict(EXIT_WORKED, f"WORKED           {len(checks)} check(s) passed "
                                        f"from outside the application")
        last = failures[0]
        if time.monotonic() > deadline:
            return Verdict(EXIT_FAILED, f"FAILED           {last}")
        time.sleep(2)


def _run_check(app: str, net: str, sidecar: str, check: dict) -> dict:
    if check["kind"] == "exec":
        r = _docker("exec", app, *check["command"], timeout=60)
        return {"exit": r.returncode, "body": r.stdout}
    try:
        r = _docker("run", "--rm", "--network", net, "--cap-drop", "ALL", sidecar,
                    "python", "-c", CLIENT, json.dumps(check), timeout=60)
    except subprocess.TimeoutExpired:
        return {"error": "the probe client timed out"}
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"error": f"the probe client failed: {r.stderr.strip()[:200]}"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # An image, never a report file: the image tag comes from whoever ran the
    # package gate, not from a file in a workspace an agent works in (w18 H1).
    ap.add_argument("--image", required=True, help="the packaged image")
    ap.add_argument("--probe", required=True, help="the operator's probe.yaml")
    args = ap.parse_args(argv)
    try:
        verdict = probe(args.image, load_probe(Path(args.probe)))
    except (ProbeError, subprocess.TimeoutExpired) as exc:
        print(f"HONESTLY REFUSED the probe could not run: {exc}")
        return EXIT_REFUSED
    print(verdict.line)
    return verdict.code


if __name__ == "__main__":
    raise SystemExit(main())
