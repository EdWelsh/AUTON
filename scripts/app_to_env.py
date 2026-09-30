#!/usr/bin/env python3
"""Application to environment, end to end: one repository in, a scored package out.

    .venv/bin/python scripts/app_to_env.py --subject <app dir> --probe <probe.yaml> \
        --out <dir> [--config auton.toml] [--exercise exercise.sh] [--timeout 7200]

Each stage is the tool or the agent run the PRD names, in order, and each
records its verdict in <out>/STAGES.json before the next starts. A stage that
fails stops the chain there and says so: a later stage built on a failed one
would be grading nothing.

    1 analyst    the Analyst agent writes analysis/<app>.artifact.yaml (A3, A4)
    2 manifest   artifact_manifest builds the Manifest (A6)
    3 packager   the Packager agent writes package/Dockerfile, gated by a build (A8)
    4 observe    observe.py runs the package in the sandbox; observed facts merge in (A5)
    5 regate     the manifest is rebuilt from the observed record; the package gate
                 re-checks the same recipe against it
    6 probe      app_probe.py grades it from outside (A10)
    7 ablate     ablate.py scores every requirement (A9)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "agent" / "tools"
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv/bin/python").exists() else sys.executable
sys.path.insert(0, str(TOOLS))


class Stages:
    def __init__(self, out: Path):
        self.path = out / "STAGES.json"
        self.stages: list[dict] = []

    def record(self, name: str, ok: bool, detail: str, started: float, **extra) -> bool:
        self.stages.append({"stage": name, "ok": ok, "detail": detail,
                            "seconds": round(time.monotonic() - started, 1), **extra})
        self.path.write_text(json.dumps(self.stages, indent=2) + "\n")
        print(f"[{'PASS' if ok else 'STOP'}] {name}: {detail}", flush=True)
        return ok


def orchestrate(ws: Path, config: Path, goal: str, timeout: int, log: Path, *extra: str) -> int:
    cfg = config.read_text()
    local = ws.parent / f"{ws.name}.toml"
    lines = [f'path = "{ws}"' if ln.startswith("path =") else ln for ln in cfg.splitlines()]
    local.write_text("\n".join(lines) + "\n")
    env = {**os.environ, "ORCH_TIMEOUT": str(timeout), "ORCH_CONFIG": str(local),
           "ORCH_LOG": str(log)}
    # A pinned copy: bash reads a script as it runs, so an edit to the repo's
    # copy mid-run breaks the run (w18 live run 3).
    script = ws.parent / "orchestrate-native.sh"
    if not script.exists():
        text = (ROOT / "scripts/orchestrate-native.sh").read_text()
        script.write_text(text.replace('ROOT="$(cd "$(dirname "$0")/.." && pwd)"',
                                       f'ROOT="{ROOT}"', 1))
    r = subprocess.run(["bash", str(script), goal, *extra],
                       env=env, capture_output=True, text=True)
    (log.parent / f"{log.stem}.out").write_text(r.stdout + r.stderr)
    return r.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=str(ROOT / "agent/config/auton.toml"))
    ap.add_argument("--exercise")
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--record", help="skip stage 1: use this artifact record")
    ap.add_argument("--recipe", help="skip the Packager: a HUMAN-written Dockerfile, gated "
                                     "the same way and labelled human in STAGES.json")
    args = ap.parse_args(argv)

    subject, probe = Path(args.subject).resolve(), Path(args.probe).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    st = Stages(out)
    config = Path(args.config).resolve()

    # 1 analyst
    t = time.monotonic()
    ws_a = out / "ws-analyst"
    if args.record:
        record = Path(args.record).resolve()
        st.record("analyst", True, f"given: {record}", t, skipped=True)
    else:
        rc = orchestrate(ws_a, config, "Analyse the application staged at .auton/subject/ "
                         "and write its artifact record.", args.timeout, out / "analyst.log",
                         "--subject", str(subject))
        found = sorted((ws_a / "analysis").glob("*.artifact.yaml")) if (ws_a / "analysis").is_dir() else []
        merged = subprocess.run(["git", "-C", str(ws_a), "log", "main", "--oneline", "--",
                                 "analysis"], capture_output=True, text=True).stdout.strip()
        if not (found and merged):
            st.record("analyst", False, f"no merged artifact record (orchestrator exit {rc}); "
                      f"see analyst.log", t)
            return 1
        record = out / found[0].name
        shutil.copy(found[0], record)
        st.record("analyst", True, f"merged {found[0].name}", t)

    # 2 manifest
    t = time.monotonic()
    from artifact_manifest import build_from_artifact
    from intent_manifest import IntentError
    try:
        manifest = json.loads(build_from_artifact(record, "docker", subject=subject).to_json())
    except IntentError as exc:
        st.record("manifest", False, str(exc)[:400], t)
        return 1
    mpath = out / "manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2) + "\n")
    st.record("manifest", True, f"{len(manifest['application']['requires'])} requirement(s), "
              f"{len(manifest['assumptions'])} assumption(s)", t)

    # 3 packager
    t = time.monotonic()
    ws_p = out / "ws-packager"
    report = ws_p / ".auton" / "package-report.json"
    dockerfile = ws_p / "package" / "Dockerfile"
    author = "human" if args.recipe else "agent"
    if args.recipe:
        from package_gate import check as gate
        sys.path.insert(0, str(ROOT / "agent"))
        from orchestrator.comms.git_workspace import GitWorkspace
        gw = GitWorkspace(ws_p)
        gw.init()
        if not gw.subject_path.exists():
            gw.stage_subject(subject)
        (ws_p / ".auton" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        dockerfile.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(args.recipe, dockerfile)
        gated = gate(ws_p)
        report.write_text(json.dumps(gated.__dict__, indent=2) + "\n")
        rep, merged, rc = gated.__dict__, "human", 0
    else:
        rc = orchestrate(ws_p, config, "", args.timeout, out / "packager.log",
                         "--manifest", str(mpath), "--subject", str(subject),
                         "--probe", str(probe))
        rep = json.loads(report.read_text()) if report.is_file() else {}
        merged = subprocess.run(["git", "-C", str(ws_p), "log", "main", "--oneline", "--",
                                 "package/Dockerfile"], capture_output=True,
                                text=True).stdout.strip()
    if not (rep.get("ok") and merged):
        st.record("packager", False, f"no merged, gated recipe (orchestrator exit {rc}; gate: "
                  f"{rep.get('problems') or 'never ran'})", t, author=author)
        return 1
    st.record("packager", True, f"image {rep['image']}, {len(rep['extras'])} extras", t,
              author=author)

    # 4 observe
    t = time.monotonic()
    from observe import observe
    exercise = Path(args.exercise).read_text() if args.exercise else ""
    try:
        obs = observe(subject, record=record, exercise=exercise, dockerfile=dockerfile)
    except Exception as exc:          # noqa: BLE001 — recorded, and the chain stops
        st.record("observe", False, str(exc)[:400], t)
        return 1
    st.record("observe", True, f"{len(obs['facts'])} observed, "
              f"{sum(len(v) for v in obs['unindexed'].values())} unindexed; exercise exit "
              f"{obs['exercise_exit']}", t, observation=obs["id"])

    # 5 regate
    t = time.monotonic()
    try:
        manifest = json.loads(build_from_artifact(record, "docker", subject=subject).to_json())
    except IntentError as exc:
        st.record("regate", False, str(exc)[:400], t)
        return 1
    (ws_p / ".auton" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    mpath.write_text(json.dumps(manifest, indent=2) + "\n")
    from package_gate import check
    rep = check(ws_p)
    if not rep.ok:
        st.record("regate", False, "; ".join(rep.problems)[:400], t)
        return 1
    report.write_text(json.dumps(rep.__dict__, indent=2) + "\n")
    st.record("regate", True, f"{len(manifest['application']['requires'])} requirement(s) "
              f"after observation; 0 missing", t)

    # 6 probe
    t = time.monotonic()
    from app_probe import probe as run_probe, load_probe
    v = run_probe(rep.image, load_probe(probe))
    if not st.record("probe", v.code == 0, v.line.strip(), t, verdict=v.line.split()[0]):
        return 1

    # 7 ablate
    t = time.monotonic()
    from ablate import ablate
    score = ablate(ws_p, probe)
    shutil.copy(ws_p / "package" / "ABLATION.json", out / "ABLATION.json")
    st.record("ablate", True, f"{score.load_bearing} of {score.ablated} load-bearing; "
              f"over-claimed: {', '.join(score.over_claimed) or 'none'}", t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
