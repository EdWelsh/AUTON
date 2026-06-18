# AUTON OS backend — five OS environments from chat

AUTON can create, boot, and manage five OS containers from natural language and
push them to Docker (they appear in Docker Desktop as `auton/<os>` images +
`auton-<os>` containers). The backend is **honest about what each can do**.

| OS | Status | Runs | Host needed |
|----|--------|------|-------------|
| **Linux** | ✓ real, runs here | real Linux apps (`.deb`, any ELF) | any Docker host (works on this Mac) |
| **Windows-style** | △ experimental | `.exe` via Wine | any host (x86 `.exe` on ARM needs box64) |
| **Android** | ⚙ real, needs KVM | APKs (real emulator + noVNC + ADB) | KVM host (Proxmox) |
| **macOS** | △ experimental | `.app` (Mach-O) | KVM host; x86 only; **violates Apple EULA** |
| **iOS** | ✗ not a container | `.ipa` | external service (Corellium / Appetize) |

## Use it from chat

```
auton> what os can you create        # the honest catalog
auton> boot the linux os             # pull + tag + run, returns the browser URL
auton> create the windows os         # build the Wine image, don't run it yet
auton> run the android os            # refuses cleanly off a KVM host, points at compose
auton> what oses are running         # docker ps for auton-* containers
auton> stop the linux os
auton> run an ios app                # explains the only real paths + token wiring
```

Linux boots locally and opens at **http://localhost:3000**.

## The KVM ones (Windows / Android / macOS)

These need `/dev/kvm`, which Docker Desktop on a Mac does not provide. AUTON
refuses to fake it and hands you a ready compose file to run on your Proxmox/KVM
host:

```bash
docker compose -f images/windows-dockur/compose.yml up -d   # real Windows :8006
docker compose -f images/android/compose.yml         up -d   # real Android :6080
docker compose -f images/macos-dockur/compose.yml    up -d   # real macOS   :8006
```

## iOS

There is no container that runs iOS apps. AUTON routes to the real options
(Corellium, Appetize.io, or Xcode's Simulator on a Mac). Set
`CORELLIUM_API_TOKEN` or `APPETIZE_API_TOKEN` and the backend reports the
integration as available. See `images/ios-guidance/GUIDANCE.md`.
