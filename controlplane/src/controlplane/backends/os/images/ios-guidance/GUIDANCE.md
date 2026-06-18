# iOS — why there is no container, and what AUTON routes to instead

iOS apps (`.ipa`, ARM Mach-O, Apple-signed, sandboxed against iOS frameworks)
**cannot run in any Docker container.** There is no honest image for this. The
only real ways to run iOS apps are:

| Path | What it is | AUTON integration |
|------|-----------|-------------------|
| **Corellium** | ARM-virtualized iOS (cloud or on-prem appliance), the only true iOS virtualization | REST API — set `CORELLIUM_API_TOKEN` |
| **Appetize.io** | Cloud-hosted iOS in your browser, upload an `.ipa` | REST API — set `APPETIZE_API_TOKEN` |
| **Xcode iOS Simulator** | Runs sim-built apps (not App Store `.ipa`) on a real Mac | local, needs macOS + Xcode |

So AUTON's honest answer for "run iOS apps" is: **provision an external service,
not a container.** When a token is set, the `os` backend reports the integration
is available; wiring the actual upload/boot calls is the next step.

This directory intentionally has no Dockerfile — the `ios` profile is
`OSStatus.EXTERNAL` and never builds an image.
