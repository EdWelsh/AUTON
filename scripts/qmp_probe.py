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

Exit 0 both hold, 2 the frame is a single colour, 3 the frame never changed.
"""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

KEYS = ["up"] * 10
SETTLE_SECONDS = 2


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


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    qmp, work = argv[1], Path(argv[2])

    monitor = Monitor(qmp)
    before = work / "frame-before.ppm"
    after = work / "frame-after.ppm"

    monitor.screendump(before)
    time.sleep(SETTLE_SECONDS)
    body = pixels(before)
    if len(set(body[i : i + 3] for i in range(0, min(len(body), 30000), 3))) <= 1:
        print("the frame is a single colour: nothing was drawn")
        return 2

    for key in KEYS:
        monitor.sendkey(key)
    time.sleep(SETTLE_SECONDS)
    monitor.screendump(after)
    if pixels(after) == body:
        print("the frame is unchanged after ten key presses: input is not reaching the game")
        return 3

    print(f"drawn, and the frame changed on input ({before.name} -> {after.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
