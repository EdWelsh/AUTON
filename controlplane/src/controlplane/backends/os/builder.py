"""Drive Docker to provision, launch, and manage the AUTON OS containers.

The argv builders are pure (and unit-tested without Docker). :class:`OSManager`
executes them against the real ``docker`` CLI — no mocks. KVM-only profiles are
guarded: on a host without ``/dev/kvm`` we refuse to launch and hand back the
ready compose file to run on a KVM host instead of failing obscurely.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - fixed argument lists, shell=False
from dataclasses import dataclass
from pathlib import Path

from .profiles import IMAGES_ROOT, OSProfile, OSStatus

KVM_DEVICE = "/dev/kvm"
_PROVISION_TIMEOUT = 1800  # image pulls/builds can be large
_DOCKER_TIMEOUT = 60


def kvm_available() -> bool:
    """True only if this host exposes /dev/kvm (never on Mac Docker Desktop)."""
    return Path(KVM_DEVICE).exists()


def docker_available(docker: str = "docker") -> bool:
    return shutil.which(docker) is not None


# --- pure argv builders (unit-tested without Docker) ------------------------

def pull_argv(profile: OSProfile, docker: str = "docker") -> list[str]:
    if not profile.image:
        raise ValueError(f"{profile.key} has no upstream image to pull")
    return [docker, "pull", profile.image]


def build_argv(profile: OSProfile, docker: str = "docker", context: Path | None = None) -> list[str]:
    if not profile.build_dir:
        raise ValueError(f"{profile.key} has no build_dir")
    ctx = (context or IMAGES_ROOT) / profile.build_dir
    return [docker, "build", "-t", profile.tag, str(ctx)]


def tag_argv(source: str, target: str, docker: str = "docker") -> list[str]:
    return [docker, "tag", source, target]


def run_argv(profile: OSProfile, host_port: int | None = None, docker: str = "docker") -> list[str]:
    """docker run -d for a profile, wiring ports, devices, caps, and env."""
    argv = [docker, "run", "-d", "--name", profile.container_name()]
    if profile.privileged:
        argv.append("--privileged")
    for dev in profile.run_devices:
        argv += ["--device", dev]
    for cap in profile.run_caps:
        argv += ["--cap-add", cap]
    for key, val in profile.run_env:
        argv += ["-e", f"{key}={val}"]
    if profile.web_port is not None:
        argv += ["-p", f"{host_port or profile.web_port}:{profile.web_port}"]
    argv += ["--restart", "unless-stopped", profile.tag]
    return argv


# --- execution --------------------------------------------------------------

@dataclass(frozen=True)
class StepResult:
    ok: bool
    message: str
    detail: str = ""


class OSManager:
    """Real Docker lifecycle for OS profiles."""

    def __init__(self, docker: str = "docker", images_root: Path | None = None) -> None:
        self.docker = docker
        self.images_root = images_root or IMAGES_ROOT

    def _run(self, argv: list[str], timeout: int = _DOCKER_TIMEOUT) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # nosec B603 - fixed argv, shell=False
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )

    def provision(self, profile: OSProfile) -> StepResult:
        """Pull or build the image and tag it auton/<key> (shows in Docker Desktop)."""
        if profile.status is OSStatus.EXTERNAL:
            return StepResult(True, _external_guidance(profile))
        if not docker_available(self.docker):
            return StepResult(False, "Docker CLI not found on PATH.")

        if profile.build_dir:
            cp = self._run(build_argv(profile, self.docker, self.images_root), timeout=_PROVISION_TIMEOUT)
            what = f"built {profile.tag} from {profile.build_dir}/"
        else:
            cp = self._run(pull_argv(profile, self.docker), timeout=_PROVISION_TIMEOUT)
            if cp.returncode == 0:
                self._run(tag_argv(profile.image or "", profile.tag, self.docker))
            what = f"pulled {profile.image} → tagged {profile.tag}"

        if cp.returncode != 0:
            return StepResult(False, f"provision failed for {profile.label}", cp.stderr.strip()[-500:])
        return StepResult(True, f"{profile.label}: {what}")

    def launch(self, profile: OSProfile, host_port: int | None = None) -> StepResult:
        """Run the container, honestly refusing KVM-only profiles off a KVM host."""
        if profile.status is OSStatus.EXTERNAL:
            return StepResult(False, _external_guidance(profile))
        if profile.requires_kvm and not kvm_available():
            compose = (self.images_root / profile.compose_file) if profile.compose_file else None
            return StepResult(
                False,
                (
                    f"{profile.label} needs /dev/kvm, which this host doesn't have. "
                    f"Run it on your Proxmox/KVM box:\n  docker compose -f {compose} up -d"
                    if compose
                    else f"{profile.label} needs /dev/kvm (a KVM host)."
                ),
            )
        if not docker_available(self.docker):
            return StepResult(False, "Docker CLI not found on PATH.")

        # Replace any stale container of the same name first.
        self._run([self.docker, "rm", "-f", profile.container_name()])
        cp = self._run(run_argv(profile, host_port, self.docker))
        if cp.returncode != 0:
            return StepResult(False, f"launch failed for {profile.label}", cp.stderr.strip()[-500:])
        url = profile.web_url(host_port)
        where = f" → open {url}" if url else ""
        return StepResult(True, f"{profile.label} is running ({profile.container_name()}){where}")

    def stop(self, profile: OSProfile) -> StepResult:
        cp = self._run([self.docker, "rm", "-f", profile.container_name()])
        if cp.returncode != 0:
            return StepResult(False, f"{profile.label} was not running.")
        return StepResult(True, f"Stopped {profile.label} ({profile.container_name()}).")

    def running(self) -> list[str]:
        """Names of currently-running AUTON OS containers."""
        cp = self._run(
            [self.docker, "ps", "--filter", "name=auton-", "--format", "{{.Names}}\t{{.Ports}}\t{{.Status}}"]
        )
        if cp.returncode != 0:
            return []
        return [ln for ln in cp.stdout.splitlines() if ln.strip()]


def _external_guidance(profile: OSProfile) -> str:
    have_corellium = bool(os.environ.get("CORELLIUM_API_TOKEN"))
    have_appetize = bool(os.environ.get("APPETIZE_API_TOKEN"))
    lines = [f"{profile.label}: {profile.summary}", profile.notes]
    if have_corellium:
        lines.append("✓ CORELLIUM_API_TOKEN detected — Corellium integration can be enabled.")
    if have_appetize:
        lines.append("✓ APPETIZE_API_TOKEN detected — Appetize.io integration can be enabled.")
    if not (have_corellium or have_appetize):
        lines.append("(No iOS service token set; this stays guidance-only until you add one.)")
    return "\n".join(lines)
