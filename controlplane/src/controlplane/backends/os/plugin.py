"""OS backend plugin — the "os" capability wired into the AUTON chat router.

Natural language → (action, which OS). Examples:
  "create the linux os"        -> provision Linux
  "boot the linux os"          -> provision + run Linux, returns the browser URL
  "spin up windows"            -> Windows-style desktop
  "run the android os"         -> Android emulator (needs KVM)
  "what oses are running"      -> list AUTON OS containers
  "stop the macos"             -> stop that container
  "list os" / "what can the os do" -> the honest catalog
"""

from __future__ import annotations

from controlplane.core import Capability, CapabilityResult, CapabilityStatus

from .builder import OSManager, kvm_available
from .profiles import OSStatus, all_profiles, profile_for_text

_STATUS_MARK = {
    OSStatus.REAL: "✓ real, runs here",
    OSStatus.NEEDS_KVM: "⚙ real, needs a KVM host",
    OSStatus.EXPERIMENTAL: "△ experimental",
    OSStatus.EXTERNAL: "✗ not a container",
}


def _catalog() -> str:
    lines = ["AUTON can create these 5 OS environments (Docker):"]
    for p in all_profiles():
        lines.append(f"  • {p.label} [{_STATUS_MARK[p.status]}] — runs {p.app_kind}")
        lines.append(f"      {p.summary}")
    lines.append("")
    lines.append(
        "Say e.g. 'create the linux os', 'boot linux', 'run android', "
        "'what oses are running', 'stop windows'."
    )
    lines.append(f"(/dev/kvm on this host: {'yes' if kvm_available() else 'no'})")
    return "\n".join(lines)


def _wants(text: str, *words: str) -> bool:
    t = text.lower()
    return any(w in t for w in words)


def _handle(text: str) -> CapabilityResult:
    mgr = OSManager()

    # List running OS containers (must mention "running").
    if _wants(text, "running", "what's running", "list running", "ps"):
        names = mgr.running()
        if not names:
            return CapabilityResult.ok("No AUTON OS containers are running. Try 'boot the linux os'.")
        body = "\n".join(f"  {n}" for n in names)
        return CapabilityResult.ok(f"Running AUTON OS containers:\n{body}", running=names)

    # Catalog / help.
    if _wants(
        text, "list os", "what os can", "which os can", "what os do", "catalog",
        "what can the os", "options", "what oses", "create",
    ) and not profile_for_text(text):
        return CapabilityResult.ok(_catalog())

    profile = profile_for_text(text)
    if profile is None:
        return CapabilityResult.ok(_catalog())

    if _wants(text, "stop", "kill", "shut down", "shutdown", "halt"):
        r = mgr.stop(profile)
        return CapabilityResult.ok(r.message) if r.ok else CapabilityResult.fail(r.message)

    if _wants(text, "url", "open", "where", "address"):
        url = profile.web_url()
        if url:
            return CapabilityResult.ok(f"{profile.label}: {url} (boot it first if it isn't running).")
        return CapabilityResult.ok(f"{profile.label} has no web viewer. {profile.notes}")

    # create/build/provision only (no run)
    if _wants(text, "create", "build", "provision", "pull", "make", "prepare") and not _wants(
        text, "boot", "run", "start", "launch", "spin"
    ):
        r = mgr.provision(profile)
        return CapabilityResult.ok(r.message) if r.ok else CapabilityResult.fail(r.message, r.detail)

    # default: boot = provision + launch
    prov = mgr.provision(profile)
    if not prov.ok:
        return CapabilityResult.fail(prov.message, prov.detail)
    run = mgr.launch(profile)
    text_out = f"{prov.message}\n{run.message}"
    return CapabilityResult.ok(text_out) if run.ok else CapabilityResult(
        handled=True, text=text_out, error=run.message
    )


def get_capabilities() -> list[Capability]:
    return [
        Capability(
            name="os",
            keywords=(
                "operating system",
                "os image",
                "oses",
                " os",
                "boot ",
                "spin up",
                "linux",
                "windows",
                "android",
                "macos",
                "mac os",
                "ios",
                "iphone",
            ),
            status=CapabilityStatus.WORKING,
            note="create/boot 5 OS containers (Linux real; Windows/Android/macOS via KVM; iOS external)",
            handler=_handle,
        ),
    ]
