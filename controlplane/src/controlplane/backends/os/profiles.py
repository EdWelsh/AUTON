"""The five AUTON OS profiles — honest, data-driven definitions.

Each profile says exactly what it is, what host it needs, and whether it can run
real apps. The control plane never pretends: Linux is real and local; Windows,
Android and macOS are real but need a KVM host (your Proxmox box); iOS cannot run
in any container and routes to an external service instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

IMAGES_ROOT = Path(__file__).resolve().parent / "images"


class OSStatus(str, Enum):
    """How real, and how runnable, an OS profile is."""

    REAL = "real"  # runs real apps locally on any Docker host (no KVM needed)
    NEEDS_KVM = "needs_kvm"  # runs real apps, but only on a KVM host (Proxmox)
    EXPERIMENTAL = "experimental"  # runs, with caveats (EULA, x86-on-ARM, Wine)
    EXTERNAL = "external"  # not a container — needs an external service/host


@dataclass(frozen=True)
class OSProfile:
    key: str  # linux | windows | android | macos | ios
    label: str  # display name
    summary: str  # one-line what-it-is
    app_kind: str  # what it runs: ".deb / Linux", "APK", ".ipa / iOS", ...
    status: OSStatus
    runs_real_apps: bool
    requires_kvm: bool
    tag: str  # local image tag AUTON gives it (shows in Docker Desktop)
    image: str | None = None  # upstream image to pull (None => build_dir)
    build_dir: str | None = None  # subdir of IMAGES_ROOT holding a Dockerfile
    web_port: int | None = None  # in-container web/noVNC viewer port
    web_path: str = "/"
    run_devices: tuple[str, ...] = ()  # e.g. ("/dev/kvm", "/dev/net/tun")
    run_caps: tuple[str, ...] = ()  # e.g. ("NET_ADMIN",)
    run_env: tuple[tuple[str, str], ...] = ()
    privileged: bool = False
    compose_file: str | None = None  # ready-to-run compose (KVM host) under build_dir
    notes: str = ""

    def web_url(self, host_port: int | None = None) -> str | None:
        if self.web_port is None:
            return None
        return f"http://localhost:{host_port or self.web_port}{self.web_path}"

    def container_name(self) -> str:
        return f"auton-{self.key}"


_PROFILES: tuple[OSProfile, ...] = (
    OSProfile(
        key="linux",
        label="Linux",
        summary="Native-ARM Ubuntu KDE desktop in your browser; runs real Linux apps.",
        app_kind=".deb / any Linux binary",
        status=OSStatus.REAL,
        runs_real_apps=True,
        requires_kvm=False,
        tag="auton/linux:latest",
        image="lscr.io/linuxserver/webtop:ubuntu-kde",
        web_port=3000,
        notes="Works on this Mac right now. apt-get install anything inside it.",
    ),
    OSProfile(
        key="windows",
        label="Windows-style (Wine)",
        summary="A Windows-style noVNC desktop with Wine that runs .exe apps.",
        app_kind=".exe / Windows",
        status=OSStatus.EXPERIMENTAL,
        runs_real_apps=True,
        requires_kvm=False,
        tag="auton/windows:latest",
        build_dir="windows-wine",
        web_port=3000,
        compose_file="windows-dockur/compose.yml",
        notes=(
            "Local Wine desktop builds anywhere; running x86 .exe on ARM needs "
            "box64/hangover and is slow. For REAL Windows use windows-dockur/"
            "compose.yml on your Proxmox/KVM host (web viewer on :8006)."
        ),
    ),
    OSProfile(
        key="android",
        label="Android",
        summary="Real Android emulator with noVNC + ADB; installs and runs APKs.",
        app_kind="APK / Android",
        status=OSStatus.NEEDS_KVM,
        runs_real_apps=True,
        requires_kvm=True,
        tag="auton/android:latest",
        image="budtmo/docker-android:emulator_11.0",
        web_port=6080,
        run_devices=("/dev/kvm",),
        privileged=True,
        run_env=(("EMULATOR_DEVICE", "Samsung Galaxy S10"), ("WEB_VNC", "true")),
        compose_file="android/compose.yml",
        notes=(
            "Needs /dev/kvm (your Proxmox host). noVNC on :6080, ADB on :5555 — "
            "`adb install app.apk` to side-load. x86 emulator: KVM required."
        ),
    ),
    OSProfile(
        key="macos",
        label="macOS",
        summary="Real macOS via KVM/QEMU (dockur/macos), web viewer.",
        app_kind=".app / macOS (Mach-O)",
        status=OSStatus.EXPERIMENTAL,
        runs_real_apps=True,
        requires_kvm=True,
        tag="auton/macos:latest",
        image="dockurr/macos",
        web_port=8006,
        run_devices=("/dev/kvm", "/dev/net/tun"),
        run_caps=("NET_ADMIN",),
        run_env=(("VERSION", "13"),),
        compose_file="macos-dockur/compose.yml",
        notes=(
            "Needs /dev/kvm (Proxmox). x86 only (slow under emulation on Apple "
            "Silicon) and running macOS on non-Apple hardware violates Apple's "
            "EULA — for testing only."
        ),
    ),
    OSProfile(
        key="ios",
        label="iOS",
        summary="Cannot run in Docker — routes to a real iOS service (Corellium/Appetize).",
        app_kind=".ipa / iOS",
        status=OSStatus.EXTERNAL,
        runs_real_apps=False,
        requires_kvm=False,
        tag="auton/ios:guidance",
        build_dir="ios-guidance",
        notes=(
            "No container runs iOS apps. Real options AUTON can wire to: "
            "Corellium (ARM iOS virtualization, API), Appetize.io (cloud iOS in "
            "browser, API), or Xcode's iOS Simulator on a real Mac. Set "
            "CORELLIUM_API_TOKEN or APPETIZE_API_TOKEN to enable an integration."
        ),
    ),
)

_BY_KEY = {p.key: p for p in _PROFILES}

# Aliases people actually type, mapped to a profile key. Order/specificity does
# not matter here — lookup is exact-substring against these.
_ALIASES: dict[str, str] = {
    "linux": "linux",
    "ubuntu": "linux",
    "windows": "windows",
    "win": "windows",
    "android": "android",
    "apk": "android",
    "macos": "macos",
    "mac os": "macos",
    "osx": "macos",
    "ios": "ios",
    "iphone": "ios",
    "ipad": "ios",
}


def all_profiles() -> tuple[OSProfile, ...]:
    return _PROFILES


def profile_by_key(key: str) -> OSProfile | None:
    return _BY_KEY.get(key)


def profile_for_text(text: str) -> OSProfile | None:
    """Find which OS an utterance refers to (most specific alias wins).

    "mac os" must beat "os"; "macos" must not be shadowed by a bare "mac". We
    test longer aliases first so multi-word names match before short ones.
    """
    t = text.lower()
    for alias in sorted(_ALIASES, key=len, reverse=True):
        if alias in t:
            return _BY_KEY[_ALIASES[alias]]
    return None
