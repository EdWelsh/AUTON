"""OS backend — create, boot, and manage five OS containers from chat.

Linux (real, local), Windows-style (Wine local / real dockur on KVM), Android
(real emulator on KVM), macOS (dockur on KVM, experimental), and iOS (no
container — routes to Corellium/Appetize). See :mod:`.profiles` for the honest
per-OS definitions and :mod:`.builder` for the Docker lifecycle.
"""
