"""Chat surfaces: terminal, UI, and desktop installs of the control plane.

Each surface owns its own I/O loop but shares one :class:`~controlplane.core.ChatEngine`
contract and the same persistent :class:`~controlplane.core.SessionStore`, so the
conversation is continuous across terminal, browser, and desktop.
"""
