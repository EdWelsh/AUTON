"""Probe a running image through QEMU's monitor, not through its own logs.

    python scripts/qmp_probe.py <qmp socket> <work dir>

Used by `run-intent-probe.sh doom`. Two questions, both answered from outside
the guest:

1. **Is anything drawn?** `screendump` writes the framebuffer as a PPM; a
   single-colour image means the guest printed "[DOOM] frame 1" and drew
   nothing. An image that grades itself by its own log line is exactly what the
   intent PRD's rubric exists to prevent.
2. **Does input reach the game?** Send keys, dump again, and compare. A frame
   that is identical after ten key presses is a game that is not listening —
   which would otherwise look like success, because something *is* on screen.

3. **Was that the input, or animation?** Doom's attract demo moves by itself,
   so a frame is first dumped twice with no input (the control), and the change
   after the keys must clearly exceed the change without them.

Exit 0 all hold, 2 the frame is a single colour, 3 the frame never changed on
input, 4 inconclusive: the frame changes as much by itself as after the keys.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

# Escape opens Doom's menu from the title screen and during the demo, so the
# key is visible whatever state the game is in.
KEYS = [k for k in os.environ.get("QMP_PROBE_KEYS", "esc").split(",") if k]
IDLE_SECONDS = 1
SETTLE_SECONDS = 1
MARGIN = 2.0          # the key-driven change must be at least twice the idle change
# ...and at least this much more of the frame. Calibrated live (2026-09-30) on
# GRUB's menu under QEMU: Escape removed the countdown line, 0.5% of the frame
# against ~0.03% idle; a 1% floor called that real input "inconclusive".
MIN_EXTRA = 0.002


class Monitor:
    """The smallest QMP client that can ask these two questions."""

    def __init__(self, path: str) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect(path)
        self.buf = b""
        self._read()                      # the greeting
        self.command("qmp_capabilities")

    def _read(self) -> dict:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("the monitor closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def command(self, name: str, **args) -> dict:
        payload: dict[str, object] = {"execute": name}
        if args:
            payload["arguments"] = args
        self.sock.sendall(json.dumps(payload).encode() + b"\n")
        while True:
            message = self._read()
            if "return" in message or "error" in message:
                return message          # events are not answers; keep reading

    def screendump(self, path: Path) -> None:
        self.command("screendump", filename=str(path))

    def sendkey(self, key: str) -> None:
        self.command("human-monitor-command", **{"command-line": f"sendkey {key}"})


def pixels(path: Path) -> bytes:
    """The PPM's pixel data, without its header."""
    data = path.read_bytes()
    fields, at = [], 0
    while len(fields) < 4:                # P6, width, height, maxval
        while at < len(data) and data[at : at + 1].isspace():
            at += 1
        if data[at : at + 1] == b"#":
            while at < len(data) and data[at : at + 1] != b"\n":
                at += 1
            continue
        start = at
        while at < len(data) and not data[at : at + 1].isspace():
            at += 1
        fields.append(data[start:at])
    return data[at + 1 :]


def changed_fraction(a: bytes, b: bytes) -> float:
    """Fraction of pixels that differ between two same-sized frames."""
    if len(a) != len(b) or not a:
        return 1.0
    n = len(a) // 3
    diff = sum(1 for i in range(0, n * 3, 3) if a[i:i + 3] != b[i:i + 3])
    return diff / n


def is_blank(body: bytes) -> bool:
    """One colour over the WHOLE frame. Sampling only the first rows judged a
    centred 640x400 Doom frame blank, because its top rows are border."""
    first = body[:3]
    return all(body[i:i + 3] == first for i in range(0, len(body) - 2, 3))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    qmp, work = argv[1], Path(argv[2])
    monitor = Monitor(qmp)
    frames = [work / f"frame-{n}.ppm" for n in ("a", "b", "c")]

    # a, then b with NO input: the control. Doom's attract demo animates on its
    # own, so "the frame changed after keys" alone proves nothing.
    monitor.screendump(frames[0])
    time.sleep(IDLE_SECONDS)
    monitor.screendump(frames[1])
    a, b = pixels(frames[0]), pixels(frames[1])
    if is_blank(a) and is_blank(b):
        print("the frame is a single colour: nothing was drawn")
        return 2
    idle = changed_fraction(a, b)

    for key in KEYS:
        monitor.sendkey(key)
    time.sleep(SETTLE_SECONDS)
    monitor.screendump(frames[2])
    keyed = changed_fraction(b, pixels(frames[2]))

    if keyed == 0.0:
        print("the frame is unchanged after the key presses: input is not reaching the game")
        return 3
    if idle > 0 and keyed < max(MARGIN * idle, idle + MIN_EXTRA):
        print(f"inconclusive: the frame changes by itself ({idle:.1%} with no input) about as "
              f"much as after the keys ({keyed:.1%}); input cannot be told from animation")
        return 4
    print(f"drawn, and input changed it: {keyed:.1%} of pixels after the keys, "
          f"{idle:.1%} with none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
