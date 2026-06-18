"""Desktop install surface: a native window onto the AUTON web UI.

``main()`` is the ``auton-desktop`` console entrypoint. It starts the Unit 6
web surface (``controlplane.surfaces.ui.app``) on a background thread and opens
a native ``pywebview`` window pointed at it.

Design constraints:

* The ``ui`` and ``desktop`` extras may be installed independently, and Unit 6
  lands in a sibling PR. So every heavy dependency (``webview``, ``uvicorn``,
  the UI app) is imported **lazily inside functions** — a bare
  ``import controlplane.surfaces.desktop.shell`` must always succeed.
* ``build_window_config`` is pure and side-effect free so it can be unit-tested
  headlessly, with no display and no pywebview installed.
"""

from __future__ import annotations

import socket
import threading
from typing import Any

#: Default native-window dimensions (width, height) in CSS pixels.
DEFAULT_WINDOW_SIZE: tuple[int, int] = (1100, 760)

#: Default window/title-bar caption.
DEFAULT_TITLE: str = "AUTON"

#: Loopback host the embedded UI server binds to. Never expose externally.
HOST: str = "127.0.0.1"

_MIN_PORT = 1
_MAX_PORT = 65535


def build_window_config(
    port: int,
    title: str = DEFAULT_TITLE,
    size: tuple[int, int] = DEFAULT_WINDOW_SIZE,
) -> dict[str, Any]:
    """Build the native-window configuration. Pure and testable.

    Args:
        port: TCP port the embedded UI server listens on. Must be a valid
            (1..65535) port number.
        title: Window caption.
        size: ``(width, height)`` in CSS pixels; both must be positive.

    Returns:
        A dict with ``url``, ``title``, and ``size`` keys.

    Raises:
        ValueError: If ``port`` or ``size`` is out of range.
    """
    if not _MIN_PORT <= port <= _MAX_PORT:
        raise ValueError(f"port out of range (1..65535): {port}")
    width, height = size
    if width <= 0 or height <= 0:
        raise ValueError(f"window size must be positive: {size}")

    return {
        "url": f"http://{HOST}:{port}",
        "title": title,
        "size": (width, height),
    }


def _find_free_port() -> int:
    """Reserve an ephemeral loopback port and return it.

    The socket is closed before returning, so there's a small race window; the
    UI server rebinds the same port immediately after, which is acceptable for
    a single-user desktop launcher.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def _start_ui_server(port: int) -> threading.Thread:
    """Start the Unit 6 web UI on a daemon thread.

    Imports are deferred so this module loads without the ``ui`` extra. Raises
    ``RuntimeError`` with actionable guidance when the dependencies or the
    sibling UI surface are missing.
    """
    try:
        import uvicorn  # noqa: PLC0415 — intentional lazy import
        from controlplane.surfaces.ui import app as ui_app  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised via main()
        raise RuntimeError(
            "The web UI is unavailable. Install the UI extra and ensure the "
            "ui surface is present: pip install 'auton-controlplane[ui,desktop]'"
        ) from exc

    asgi_app = getattr(ui_app, "app", None)
    if asgi_app is None:  # pragma: no cover - depends on sibling surface
        raise RuntimeError(
            "controlplane.surfaces.ui.app does not expose an ASGI 'app'."
        )

    config = uvicorn.Config(asgi_app, host=HOST, port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="auton-ui", daemon=True)
    thread.start()
    return thread


def main() -> None:
    """``auton-desktop`` entrypoint: serve the UI and open a native window."""
    try:
        import webview  # noqa: PLC0415 — intentional lazy import
    except ImportError as exc:
        raise SystemExit(
            "pywebview is required for the desktop surface. Install it with: "
            "pip install 'auton-controlplane[desktop]'"
        ) from exc

    port = _find_free_port()

    try:
        _start_ui_server(port)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    config = build_window_config(port)
    webview.create_window(config["title"], config["url"], width=config["size"][0], height=config["size"][1])
    webview.start()


if __name__ == "__main__":  # pragma: no cover
    main()
