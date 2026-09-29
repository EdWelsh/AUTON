"""Run an application under observation; record what it actually reached for.

    python agent/tools/observe.py --subject <dir> [--record analysis/app.artifact.yaml]
                                  [--exercise exercise.sh] [--command ...]

Application-to-environment A5. Static reading misses what an application loads
at run time — a `dlopen` of a name read from a config file, a CA bundle, a
resolver it dials on start-up. This tool runs the subject in the sandbox
(`observe_sandbox.py`), traces it, and records each such need as a fact with
`source: observed`.

**This is the only writer of `observed`**, as `probe_ingest.py` is the only
writer of `probed`: an agent may not stamp the word, and
`test_observed_monopoly.py` holds that from both directions. Every observed
fact names the observation it came from, and the observation says exactly what
was exercised — the coverage is the exercise script, and nothing else. A path
the exercise did not take was not observed, and the record does not claim it
was.

The syscall set is recorded in the observation and never becomes a fact
(`decisions/syscall-scope.md`: report only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import observe_sandbox as sandbox  # noqa: E402
from artifact_spec import subject_hash, validate  # noqa: E402
from observe_parse import Observed, observe_text  # noqa: E402

COVERAGE = ("the run below and nothing else: the application's own start command, then the "
            "exercise script. Any code path they did not reach was not observed.")


def observation_record(obs: Observed, *, trace: str, subject: Path, image: str,
                       command: list[str], exercise: str, exercise_exit: int,
                       duration: float) -> dict:
    trace_sha = hashlib.sha256(trace.encode()).hexdigest()
    oid = f"obs-{trace_sha[:12]}"
    return {
        "id": oid,
        "subject_tree_hash": subject_hash.tree_hash(subject),
        "image": image,
        "command": command,
        "exercise": exercise,
        "exercise_sha256": hashlib.sha256(exercise.encode()).hexdigest(),
        "exercise_exit": exercise_exit,
        "duration_s": round(duration, 1),
        "trace_sha256": trace_sha,
        "coverage": COVERAGE,
        "facts": [{"capability": cap, "source": "observed", "observation": oid,
                   "detail": d["detail"]} for cap, d in sorted(obs.facts.items())],
        "unindexed": obs.unindexed,
        "syscalls": sorted(obs.syscalls),
    }


def merge(record_path: Path, observation: dict) -> dict:
    """Add observed facts to a record. An observed fact supersedes a declared or
    inferred one for the same capability, keeping its evidence: the static
    reading and the run agree, and the record says both."""
    data = yaml.safe_load(record_path.read_text())
    by_cap = {f.get("capability"): f for f in data.get("facts") or []}
    for fact in observation["facts"]:
        cap = fact["capability"]
        if cap.startswith("runtime:"):
            continue
        existing = by_cap.get(cap)
        if existing is not None:
            existing["source"] = "observed"
            existing["observation"] = observation["id"]
            existing.pop("looked_at", None)
        else:
            new = {"capability": cap, "source": "observed", "observation": observation["id"]}
            data.setdefault("facts", []).append(new)
            by_cap[cap] = new
    return data


def observe(subject: Path, *, record: Path | None = None, exercise: str = "",
            command: list[str] | None = None, dockerfile: Path | None = None,
            limits: sandbox.Limits = sandbox.Limits()) -> dict:
    subject = Path(subject).resolve()
    tag = sandbox.image_tag(subject)
    image = sandbox.build(subject, tag, dockerfile)
    command = command or sandbox.command_of(f"{tag}-app")
    started = time.monotonic()
    trace, exercise_exit = sandbox.run(tag, command, exercise, limits)
    obs = observe_text(trace)
    observation = observation_record(
        obs, trace=trace, subject=subject, image=image, command=command,
        exercise=exercise, exercise_exit=exercise_exit, duration=time.monotonic() - started)

    if record is not None:
        # Validate the merged record BEFORE it replaces the original: a merge
        # that does not validate must leave the record as it was (w18 review).
        merged = merge(record, observation)
        staged = record.with_suffix(".merging.yaml")
        staged.write_text(yaml.safe_dump(merged, sort_keys=False))
        report = validate(staged, allow_observed=True)
        if not report.ok:
            staged.unlink()
            raise RuntimeError("the merged record does not validate:\n  "
                               + "\n  ".join(report.problems))
        out_dir = record.parent / "observations"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{observation['id']}.json").write_text(json.dumps(observation, indent=2) + "\n")
        staged.replace(record)
    return observation


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject", required=True, help="the application (with a Dockerfile)")
    ap.add_argument("--record", help="an artifact record to merge observed facts into")
    ap.add_argument("--exercise", help="a shell script run inside the sandbox, untraced")
    ap.add_argument("--command", nargs="+", help="override the image's start command")
    ap.add_argument("--dockerfile", help="a recipe to build with, e.g. the gated "
                                         "package/Dockerfile, when the subject has none")
    ap.add_argument("--warmup", type=int, default=3)
    args = ap.parse_args(argv)

    exercise = Path(args.exercise).read_text() if args.exercise else ""
    try:
        obs = observe(Path(args.subject), record=Path(args.record) if args.record else None,
                      exercise=exercise, command=args.command,
                      dockerfile=Path(args.dockerfile) if args.dockerfile else None,
                      limits=sandbox.Limits(warmup_seconds=args.warmup))
    except (RuntimeError, OSError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({k: obs[k] for k in ("id", "exercise_exit", "duration_s", "coverage")},
                     indent=2))
    for f in obs["facts"]:
        print(f"OBSERVED {f['capability']}  ({f['detail']})")
    for kind, caps in obs["unindexed"].items():
        print(f"UNINDEXED {kind}: {', '.join(caps)} — seen, but not in the index; review "
              f"before adding", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
