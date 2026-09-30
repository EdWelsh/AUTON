"""The gate a Packager's recipe passes before anyone reviews it (A8).

    python agent/tools/package_gate.py --workspace <ws>

The Packager agent writes `package/Dockerfile`; this decides it. Four checks,
each a way a plausible recipe is wrong:

1. **The base is the table's.** Every `FROM` is the base `bases.yaml` lists for
   the manifest's runtime (or an earlier stage). A model choosing its own base
   is the model deciding what is in the environment.
2. **It builds**, with the staged application as the context.
3. **Nothing required is missing.** The built image's inventory — read from its
   exported filesystem — holds every `lib:` and `exec:` the manifest requires.
4. **The application starts** under `--network none`: still running after a
   few seconds, or exited 0. Whether it *works* is the external probe's
   question (A10), not this one.

Everything in the image the manifest did not ask for is reported as `extras`,
the way `gate_leakage` reports an excluded subsystem present in a kernel. It
does not fail the gate: a slim base carries hundreds of libraries nothing
loads, and that number is the baseline the ablation score (A9) measures
against. Hidden, it would be a minimality claim nobody checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BASES = ROOT / "agent" / "app_spec" / "bases.yaml"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from image_inventory import inventory  # noqa: E402

SUBJECT_DIR = ".auton/subject"
MANIFEST = ".auton/manifest.json"
DOCKERFILE = "package/Dockerfile"
REPORT = ".auton/package-report.json"
# How an untrusted packaged application is run for a check: no network, no
# capabilities, no privilege escalation, bounded (w18 review M3). A low port
# is bindable without CAP_NET_BIND_SERVICE via the sysctl.
CONFINE = ["--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--sysctl", "net.ipv4.ip_unprivileged_port_start=0",
           "--pids-limit", "256", "--memory", "1g", "--cpus", "2"]
FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.I | re.M)


@dataclass
class PackageReport:
    ok: bool = False
    problems: list[str] = field(default_factory=list)
    image: str = ""
    missing: list[str] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)
    started: str = ""


def load_bases(path: Path = BASES) -> dict[str, str]:
    return dict(yaml.safe_load(path.read_text())["bases"])


def load_builders(path: Path = BASES) -> set[str]:
    return set((yaml.safe_load(path.read_text()).get("builders") or {}).values())


def requirement_problems(capabilities: list[str]) -> list[str]:
    """Every requirement must be a name the index holds, whoever wrote the file
    it came from. Also what keeps a crafted name out of a Dockerfile line."""
    from artifact_spec import load_index
    index = load_index()
    return [why for cap in capabilities if (why := index.refusal(str(cap)))]


def base_problems(dockerfile: str, runtime: str, bases: dict[str, str],
                  builders: set[str] | None = None) -> list[str]:
    builders = load_builders() if builders is None else builders
    allowed = bases.get(runtime)
    if allowed is None:
        return [f"no base is listed for {runtime} in agent/app_spec/bases.yaml; the "
                f"Packager may not choose one (listed: {', '.join(sorted(bases))})"]
    stages: set[str] = set()
    problems = []
    froms = FROM.findall(dockerfile)
    if not froms:
        return ["the Dockerfile has no FROM"]
    for n, (image, alias) in enumerate(froms, 1):
        final_stage = n == len(froms)
        listed = image == allowed or image in stages or image in bases.values() \
            or (image in builders and not final_stage)
        if not listed:
            problems.append(f"FROM {image} is not a listed base; for {runtime} use "
                            f"FROM {allowed}"
                            + (f" (a build stage may use: {', '.join(sorted(builders))})"
                               if builders else ""))
        if alias:
            stages.add(alias)
    problems += _smuggling(dockerfile, stages | {allowed} | set(bases.values()) | builders)
    final = froms[-1][0]
    if final != allowed and final not in stages and not any(final in p for p in problems):
        problems.append(f"the final stage must build FROM {allowed} (or a stage built "
                        f"from it), not {final}")
    return problems


FROM_FLAG = re.compile(r"--from=(\S+)")
SYNTAX = re.compile(r"^\s*#\s*syntax\s*=", re.I | re.M)
ADD_URL = re.compile(r"^\s*ADD\s+(--\S+\s+)*(https?|git)://", re.I | re.M)


def _smuggling(dockerfile: str, allowed: set[str]) -> list[str]:
    """Checking FROM alone is not checking the base (w18 review): COPY --from,
    RUN --mount from=, a `# syntax=` frontend and ADD <url> each bring in
    content no FROM names."""
    problems = []
    if SYNTAX.search(dockerfile):
        problems.append("a `# syntax=` directive runs a builder frontend of the recipe's "
                        "choosing; remove it")
    refs = dict.fromkeys(FROM_FLAG.findall(dockerfile)
                         + re.findall(r"(?<!-)\bfrom=([^,\s]+)", dockerfile))
    for ref in refs:
        if ref not in allowed and not ref.isdigit():
            hint = ""
            if re.fullmatch(r"[a-z][a-z0-9_.-]*", ref):
                # A bare name is a stage the recipe forgot to declare (w22 whoami:
                # the builder stage was deleted instead of pinned).
                pinned = ", ".join(sorted(b for b in allowed if "@sha256:" in b and
                                          b not in _bases_of(allowed)))
                hint = (f"; no stage is named {ref!r} — declare it, e.g. "
                        f"`FROM <a listed builder> AS {ref}`"
                        + (f" (listed builders: {pinned})" if pinned else ""))
            problems.append(f"--from={ref} names an image that is neither a stage nor listed"
                            + hint)
    if ADD_URL.search(dockerfile):
        problems.append("ADD <url> fetches content no manifest names; COPY from the "
                        "application instead")
    return problems


def _bases_of(allowed: set[str]) -> set[str]:
    return set(load_bases().values()) & allowed


def diff(required: list[str], inv: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    present = {f"lib:{n}" for n in inv["libs"]} | {f"exec:{n}" for n in inv["execs"]}
    needed = [c for c in required if c.startswith(("lib:", "exec:"))]
    missing = sorted(c for c in needed if c not in present)
    extras = sorted(c for c in present if c.startswith("lib:") and c not in needed)
    return missing, extras


def _run(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def check(workspace: Path, *, manifest: dict | None = None,
          start_seconds: int = 4) -> PackageReport:
    """`manifest` is passed by the engine from memory. Read from the workspace
    only when absent (the CLI), and in both cases re-validated: a gate that
    trusts a file an agent could write checks nothing (w18 review H1)."""
    ws = Path(workspace)
    report = PackageReport()
    dockerfile = ws / DOCKERFILE
    if manifest is None:
        if not (ws / MANIFEST).is_file():
            report.problems.append(f"no manifest at {MANIFEST}: nothing says what to package")
            return report
        manifest = json.loads((ws / MANIFEST).read_text())
    if not dockerfile.is_file():
        report.problems.append(f"no {DOCKERFILE}")
        return report
    app = manifest.get("application") or {}
    runtime, required = app.get("runtime", ""), list(app.get("requires") or [])
    report.problems += requirement_problems([runtime, *required])
    if report.problems:
        return report

    report.problems += base_problems(dockerfile.read_text(), runtime, load_bases())
    if report.problems:
        return report

    tag = "auton-package-" + hashlib.sha256(dockerfile.read_bytes()).hexdigest()[:12]
    built = _run(["docker", "build", "-q", "-f", str(dockerfile), "-t", tag,
                  str(ws / SUBJECT_DIR)])
    if built.returncode != 0:
        tail = "\n".join(built.stderr.strip().splitlines()[-15:])
        report.problems.append(f"the recipe does not build:\n{tail}")
        return report
    report.image = tag

    report.missing, report.extras = diff(required, inventory(tag))
    if report.missing:
        report.problems.append(f"the image lacks what the manifest requires: "
                               f"{', '.join(report.missing)}")

    report.started = _starts(tag, start_seconds)
    if report.started not in ("running", "exited 0"):
        report.problems.append(f"the application does not start: {report.started}")
    report.ok = not report.problems
    return report


def _starts(tag: str, seconds: int) -> str:
    name = f"{tag}-start-{int(time.time())}"
    r = _run(["docker", "run", "-d", "--name", name, *CONFINE, tag], timeout=60)
    if r.returncode != 0:
        return f"docker run failed: {r.stderr.strip()[:300]}"
    try:
        time.sleep(seconds)
        state = _run(["docker", "inspect", "--format",
                      "{{.State.Status}} {{.State.ExitCode}}", name]).stdout.split()
        if state and state[0] == "running":
            return "running"
        code = state[1] if len(state) > 1 else "?"
        if code == "0":
            return "exited 0"
        logs = _run(["docker", "logs", "--tail", "10", name])
        return f"exited {code}: {(logs.stdout + logs.stderr).strip()[-400:]}"
    finally:
        _run(["docker", "rm", "-f", "-v", name])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", required=True)
    args = ap.parse_args(argv)
    report = check(Path(args.workspace))
    out = Path(args.workspace) / REPORT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(report), indent=2) + "\n")
    for p in report.problems:
        print(f"REFUSED: {p}", file=sys.stderr)
    print(f"{'OK' if report.ok else 'FAILED'}: image {report.image or '-'}, "
          f"{len(report.missing)} missing, {len(report.extras)} extra libraries "
          f"(reported, not failed), start: {report.started or '-'}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
