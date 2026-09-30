"""The ablation score: is every required capability load-bearing?
(application-to-environment A9)

    python agent/tools/ablate.py --workspace <ws> --probe <probe.yaml>

A derived environment can be wrong three ways. Under-claim is caught by the
probe; leakage by the gates. **Over-claim** — requiring something the
application never needs — is caught by nothing else: the image works, passes
and is not minimal. So each capability in the manifest is removed in turn, the
package rebuilt, and the external probe run again:

    probe FAILS   -> load-bearing: the claim was honest
    probe PASSES  -> over-claimed: not needed *by what the probe exercises*
    cannot tell   -> unprobeable (build failed, or the kind cannot be removed)

The score is `load-bearing of ablated`, written to package/ABLATION.json beside
the image the way injected-bug scores sit beside a suite. Over-claims are
reported and never trimmed automatically: a probe covers some paths, and
"not needed" can mean "not exercised". A score that has never found an
over-claim is not evidence that none exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app_probe import EXIT_WORKED, ProbeError, load_probe, probe  # noqa: E402
from package_gate import (  # noqa: E402
    DOCKERFILE, MANIFEST, SUBJECT_DIR, base_problems, load_bases, requirement_problems)

# Removing any of these takes the whole image with it; the probe would fail
# and the capability would be scored load-bearing for the wrong reason.
TOO_BROAD = {"/etc", "/usr", "/usr/lib", "/usr/share", "/var", "/run", "/lib", "/opt",
             "/srv", "/home", "/proc", "/sys", "/tmp"}

OUT = "package/ABLATION.json"
NOT_REMOVABLE = {
    "runtime": "the interpreter itself; removing it proves nothing about the manifest",
    "dial": "an outbound need; the probe's network has no route out to remove",
    "device": "device nodes are supplied by the container runtime, not the image",
    "env": "an environment variable is supplied at run time, not by the image",
}


@dataclass
class Step:
    capability: str
    outcome: str                  # load-bearing | over-claimed | unprobeable | not-ablatable
    detail: str
    seconds: float = 0.0


@dataclass
class Score:
    baseline: str = ""
    steps: list[Step] = field(default_factory=list)
    load_bearing: int = 0
    ablated: int = 0
    over_claimed: list[str] = field(default_factory=list)
    total_seconds: float = 0.0
    note: str = ("over-claimed means the probe passed without it: not needed by what the "
                 "probe exercises. Probe coverage is the limit of this claim.")


def removal(capability: str, probe_spec: dict) -> str | tuple[str, str]:
    """The Dockerfile line that removes `capability`, or (outcome, why) when it
    cannot be removed by recipe. Pure: tested without Docker."""
    kind, _, name = capability.partition(":")
    if kind in NOT_REMOVABLE:
        return ("not-ablatable", NOT_REMOVABLE[kind])
    if kind == "lib":
        return (f"find / -xdev -name {shlex.quote(name)} "
                f"\\( -type f -o -type l \\) -exec rm -f {{}} +")
    if kind == "path":
        if name.rstrip("/") in TOO_BROAD:
            return ("not-ablatable", f"{name} is too broad: removing it removes the system, "
                                     f"so a failing probe would prove nothing about it")
        return f"rm -rf {shlex.quote(name)}"
    if kind == "exec":
        return (f"for d in /bin /sbin /usr/bin /usr/sbin /usr/local/bin; do "
                f"rm -f \"$d\"/{shlex.quote(name)}; done")
    if kind == "listen":
        port = name.rsplit("/", 1)[-1]
        probed = any(str(c.get("port")) == port for c in probe_spec.get("checks") or [])
        return ("not-ablatable",
                f"a listening port is the application's own behaviour; the probe "
                f"{'does' if probed else 'does NOT'} check port {port}")
    return ("not-ablatable", f"no removal defined for kind {kind!r}")


def _build(ws: Path, recipe: str) -> tuple[str | None, str]:
    tag = "auton-ablate-" + hashlib.sha256(recipe.encode()).hexdigest()[:12]
    df = ws / ".auton" / f"{tag}.Dockerfile"
    df.write_text(recipe)
    try:
        r = subprocess.run(["docker", "build", "-q", "-f", str(df), "-t", tag,
                            str(ws / SUBJECT_DIR)], capture_output=True, text=True,
                           timeout=1800)
    except subprocess.TimeoutExpired:
        return None, "build timed out"
    finally:
        df.unlink(missing_ok=True)
    if r.returncode != 0:
        return None, "\n".join(r.stderr.strip().splitlines()[-5:])
    return tag, ""


def _drop(tag: str | None) -> None:
    if tag:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)


ABLATE_SHELL = "/.auton-ablate/busybox"


def _as_root(recipe: str, command: str) -> str:
    """Append a removal as root, then restore the recipe's final USER: a
    non-root final user would make every `rm` fail and every step unprobeable.

    The removal runs under a static busybox copied in for the step and deleted
    by the same step, in exec form: a `scratch` image has no /bin/sh, and a
    `RUN rm` there could not even start (w22 whoami). The ablated image keeps
    no shell it did not have."""
    from observe_sandbox import tracer_tag
    users = re.findall(r"^\s*USER\s+(\S+)", recipe, re.I | re.M)
    run = json.dumps([ABLATE_SHELL, "sh", "-c", f"{command}; rm -f {ABLATE_SHELL}"])
    # USER 0:0, not root or 0: with no /etc/passwd (scratch) BuildKit resolves neither.
    tail = (f"USER 0:0\nCOPY --from={tracer_tag()} /bin/busybox {ABLATE_SHELL}\n"
            f"RUN {run}\n" + (f"USER {users[-1]}\n" if users else ""))
    return recipe.rstrip("\n") + "\n" + tail


def ablate(ws: Path, probe_path: Path, manifest_path: Path | None = None,
           manifest_sha256: str | None = None) -> Score:
    """`manifest_sha256`, when given (the engine gives it), must match: the
    manifest is read from disk here, and a manifest someone rewrote is refused
    rather than scored (w18 review H1)."""
    ws = Path(ws)
    spec = load_probe(probe_path)
    raw = Path(manifest_path or ws / MANIFEST).read_bytes()
    if manifest_sha256 and hashlib.sha256(raw).hexdigest() != manifest_sha256:
        raise ProbeError("the manifest changed after the engine wrote it; refusing to score it")
    manifest = json.loads(raw)
    app = manifest.get("application") or {}
    requires = list(app.get("requires") or [])
    if bad := requirement_problems(requires):
        raise ProbeError("the manifest names capabilities outside the index: " + "; ".join(bad))
    recipe = (ws / DOCKERFILE).read_text()
    if bad := base_problems(recipe, app.get("runtime", ""), load_bases()):
        raise ProbeError("the recipe is not one the package gate would pass: " + "; ".join(bad))
    score = Score()
    started = time.monotonic()

    from observe_sandbox import TRACER_RECIPE, tracer_tag
    subprocess.run(["docker", "build", "-q", "-t", tracer_tag(), "-"], input=TRACER_RECIPE,
                   text=True, capture_output=True, check=True)
    tag, err = _build(ws, recipe)
    if tag is None:
        raise ProbeError(f"the unablated package does not build: {err}")
    base = probe(tag, spec)
    _drop(tag)
    score.baseline = base.line
    if base.code != EXIT_WORKED:
        raise ProbeError(f"the unablated package does not pass its probe ({base.line}); "
                         f"ablation against a failing baseline measures nothing")

    for cap in requires:
        t0 = time.monotonic()
        how = removal(cap, spec)
        if isinstance(how, tuple):
            score.steps.append(Step(cap, how[0], how[1]))
            continue
        tag, err = _build(ws, _as_root(recipe, how))
        if tag is None:
            score.steps.append(Step(cap, "unprobeable", f"build failed: {err}",
                                    round(time.monotonic() - t0, 1)))
            continue
        v = probe(tag, spec)
        _drop(tag)
        outcome = "over-claimed" if v.code == EXIT_WORKED else "load-bearing"
        score.steps.append(Step(cap, outcome, v.line.strip(), round(time.monotonic() - t0, 1)))

    ablated = [s for s in score.steps if s.outcome in ("load-bearing", "over-claimed")]
    score.ablated = len(ablated)
    score.load_bearing = sum(s.outcome == "load-bearing" for s in ablated)
    score.over_claimed = [s.capability for s in ablated if s.outcome == "over-claimed"]
    score.total_seconds = round(time.monotonic() - started, 1)
    out = ws / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(score), indent=2) + "\n")
    return score


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--manifest", help="default: <workspace>/.auton/manifest.json")
    ap.add_argument("--manifest-sha256", help="refuse the manifest unless it hashes to this")
    args = ap.parse_args(argv)
    try:
        s = ablate(Path(args.workspace), Path(args.probe),
                   Path(args.manifest) if args.manifest else None, args.manifest_sha256)
    except (ProbeError, OSError, subprocess.SubprocessError) as exc:
        print(f"UNPROBEABLE: {exc}", file=sys.stderr)
        return 2
    for step in s.steps:
        print(f"{step.outcome:14} {step.capability:28} {step.detail[:90]}")
    print(f"\nSCORE {s.load_bearing} of {s.ablated} load-bearing; over-claimed: "
          f"{', '.join(s.over_claimed) or 'none'} ({s.total_seconds}s)")
    return 0 if not s.over_claimed else 1


if __name__ == "__main__":
    raise SystemExit(main())
