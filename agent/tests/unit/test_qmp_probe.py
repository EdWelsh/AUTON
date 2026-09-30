"""The Doom probe, proved against a fake QEMU monitor (R12, C1).

A probe that has never been shown to fail is not evidence. Each verdict is
exercised here with scripted frames served through a real QMP socket
conversation, and each defect found while writing it is a test:

- the blank check sampled only the first rows, so a centred 640x400 frame in a
  1024x768 framebuffer — black border on top — read as "nothing was drawn";
- "the frame changed after keys" proved nothing, because Doom's attract demo
  animates by itself; the probe now measures the change with no input first.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import qmp_probe  # noqa: E402

W, H = 64, 48


def ppm(fill=(0, 0, 0), rect=None, color=(200, 30, 30)) -> bytes:
    """A W x H frame, `fill` everywhere, `color` inside rect (x0, y0, x1, y1)."""
    rows = []
    for y in range(H):
        for x in range(W):
            inside = rect and rect[0] <= x < rect[2] and rect[1] <= y < rect[3]
            rows.append(bytes(color if inside else fill))
    return b"P6\n# fake\n%d %d\n255\n" % (W, H) + b"".join(rows)


class FakeMonitor:
    """Speaks just enough QMP: greeting, qmp_capabilities, screendump (writes
    the next scripted frame), human-monitor-command (records the key)."""

    def __init__(self, path: Path, frames: list[bytes]):
        self.frames, self.keys = list(frames), []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(path))
        self.server.listen(1)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.server.accept()
        conn.sendall(b'{"QMP": {"version": {}}}\n')
        buf = b""
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                cmd = json.loads(line)
                args = cmd.get("arguments", {})
                if cmd["execute"] == "screendump":
                    Path(args["filename"]).write_bytes(self.frames.pop(0))
                elif cmd["execute"] == "human-monitor-command":
                    self.keys.append(args["command-line"])
                conn.sendall(b'{"return": {}}\n')


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(qmp_probe.time, "sleep", lambda _s: None)


def _run(tmp_path, frames):
    import tempfile
    # macOS caps an AF_UNIX path at 104 bytes; pytest's tmp paths exceed it.
    sock = Path(tempfile.mkdtemp(prefix="qmp", dir="/tmp")) / "s"
    mon = FakeMonitor(sock, frames)
    return qmp_probe.main(["qmp_probe", str(sock), str(tmp_path)]), mon


TITLE = ppm(rect=(8, 8, 56, 40))                          # the title screen, centred
MENU = ppm(rect=(8, 8, 56, 40), color=(200, 200, 30))     # the menu drawn over it


def test_a_static_title_that_opens_a_menu_on_escape_worked(tmp_path):
    rc, mon = _run(tmp_path, [TITLE, TITLE, MENU])
    assert rc == 0
    assert mon.keys == ["sendkey esc"]


def test_a_blank_frame_is_nothing_drawn(tmp_path):
    rc, _ = _run(tmp_path, [ppm(), ppm(), ppm()])
    assert rc == 2


def test_a_centred_frame_with_a_black_border_is_not_blank(tmp_path):
    """The old check sampled the first 10,000 pixels: all border."""
    centred = ppm(rect=(20, 30, 44, 46))                  # nothing in the top 30 rows
    rc, _ = _run(tmp_path, [centred, centred, ppm(rect=(20, 30, 44, 46), color=(9, 9, 9))])
    assert rc == 0


def test_input_that_changes_nothing_fails(tmp_path):
    rc, _ = _run(tmp_path, [TITLE, TITLE, TITLE])
    assert rc == 3


def test_animation_alone_is_inconclusive_not_worked(tmp_path):
    """The attract demo: the frame moves as much with no input as after it."""
    a = ppm(rect=(0, 0, 32, 48))
    b = ppm(rect=(32, 0, 64, 48))                         # half the frame changed, no input
    c = ppm(rect=(0, 0, 32, 48))                          # the same amount after the key
    rc, _ = _run(tmp_path, [a, b, c])
    assert rc == 4


def test_a_key_that_changes_far_more_than_animation_worked(tmp_path):
    a = ppm(rect=(0, 0, 4, 4))
    b = ppm(rect=(0, 0, 4, 4), color=(1, 2, 3))           # 16 pixels flicker on their own
    c = ppm(rect=(0, 0, 64, 48), color=(90, 90, 90))      # the whole frame after the key
    rc, _ = _run(tmp_path, [a, b, c])
    assert rc == 0


def test_the_blank_check_reads_the_whole_frame():
    assert qmp_probe.is_blank(bytes([7, 7, 7]) * 100)
    assert not qmp_probe.is_blank(bytes([7, 7, 7]) * 99 + bytes([1, 2, 3]))
