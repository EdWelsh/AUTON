"""strace output → observed facts (application-to-environment A5).

Pure functions over text, so they are tested on traces captured from real
runs (`agent/tests/fixtures/traces/`) with no container involved.

What becomes a fact, and why only that:

- `lib:`    a shared object the process opened successfully, by soname —
            when that soname is in the index. One that is not is reported as
            *unindexed* for a person to review: this tool may not stretch the
            vocabulary any more than an agent may.
- `path:`   a file opened under /etc, /usr/share, /var, /run, /srv, /opt or
            /home, success or failure. A *failed* open is still a need: an
            image lacking /etc/ssl/certs fails exactly there. The dynamic
            loader's own files are not the application's needs.
- `device:` a /dev node opened, when indexed.
- `exec:`   a program execve'd, when indexed.
- `listen:` a port bound on a socket that was then listened on (tcp), or a
            bound datagram socket (udp).
- `dial:`   an AF_INET connect. Under `--network none` these fail, and are
            recorded with their result: an attempt is evidence of a need. A
            dial to port 53 is recorded as `resolver:53`, because the address
            is the sandbox's resolver, not anything the application chose.

The syscall set is returned separately, never as facts: syscall-scope.md
decided *report only*.
"""

from __future__ import annotations

import posixpath
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from artifact_spec import Index, load_index  # noqa: E402

LINE = re.compile(r"^(?P<pid>\d+)\s+(?P<call>[a-z_0-9]+)\((?P<args>.*)\)\s+=\s+(?P<ret>-?\d+|\?|0x[0-9a-f]+)(?P<rest>.*)$")
UNFINISHED = re.compile(r"^(?P<pid>\d+)\s+(?P<head>[a-z_0-9]+\(.*) <unfinished \.\.\.>$")
RESUMED = re.compile(r"^(?P<pid>\d+)\s+<\.\.\. (?P<call>[a-z_0-9]+) resumed>(?P<tail>.*)$")
QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
SONAME = re.compile(r"^(lib[A-Za-z0-9_+.-]*?\.so(?:\.[0-9]+)*)$")
PORT = re.compile(r"sin6?_port=htons\((\d+)\)")
ADDR = re.compile(r'(?:sin_addr=inet_addr\("([^"]+)"\)|inet_pton\(AF_INET6, "([^"]+)")')
SOCKET = re.compile(r"^(AF_INET6?), (SOCK_STREAM|SOCK_DGRAM)")

PATH_ROOTS = ("/etc/", "/usr/share/", "/var/", "/run/", "/srv/", "/opt/", "/home/")
# Not the application's needs: the loader's own files, and what the container
# runtime bind-mounts into every container whatever the image says.
NOT_NEEDS = ("/etc/ld.so.cache", "/etc/ld.so.preload", "/etc/hosts", "/etc/hostname",
             "/etc/resolv.conf")
# A soname counts only from the system's library directories: an application's
# own vendored /app/lib/libz.so.1 is part of the application, not a need.
LIB_DIRS = ("/lib/", "/lib64/", "/usr/lib/", "/usr/lib64/", "/usr/local/lib/")
LOOPBACK = ("127.", "::1", "0.0.0.0")
OPEN_CALLS = ("openat", "open", "openat2")


@dataclass(frozen=True)
class Call:
    pid: str
    name: str
    args: str
    ret: int | None
    errno: str


@dataclass
class Observed:
    facts: dict[str, dict] = field(default_factory=dict)     # capability -> detail
    unindexed: dict[str, list[str]] = field(default_factory=dict)
    syscalls: set[str] = field(default_factory=set)


def calls(text: str) -> list[Call]:
    """Every completed call, with `<unfinished ...>`/`resumed>` pairs joined."""
    pending: dict[str, str] = {}
    out = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if m := UNFINISHED.match(line):
            pending[m["pid"]] = m["head"]
            continue
        if m := RESUMED.match(line):
            head = pending.pop(m["pid"], None)
            if head is None:
                continue
            line = f"{m['pid']} {head}{m['tail']}"
        m = LINE.match(line)
        if not m:
            continue
        ret = m["ret"]
        value = None if ret == "?" else int(ret, 16) if ret.startswith("0x") else int(ret)
        errno = (m["rest"].split() or [""])[0] if value is not None and value < 0 else ""
        out.append(Call(m["pid"], m["call"], m["args"], value, errno))
    return out


def _first_path(args: str) -> str | None:
    q = QUOTED.search(args)
    return q.group(1) if q else None


def observe_text(text: str, index: Index | None = None) -> Observed:
    index = index or load_index()
    obs = Observed()
    # Keyed by fd alone: under `strace -f` the pid column is a thread id, and a
    # server may socket() on one thread and listen() on another (Go does).
    # Cleared on close(), so a reused fd number is not the old socket.
    sockets: dict[str, str] = {}        # fd -> "tcp"/"udp"
    bound: dict[str, str] = {}          # fd -> port

    def add(cap: str, detail: str) -> None:
        if index.refusal(cap) is None:
            obs.facts.setdefault(cap, {"detail": detail})
        else:
            kind = cap.partition(":")[0]
            obs.unindexed.setdefault(kind, [])
            if cap not in obs.unindexed[kind]:
                obs.unindexed[kind].append(cap)

    for c in calls(text):
        obs.syscalls.add(c.name)
        if c.name in OPEN_CALLS:
            path = _first_path(c.args)
            if not path:
                continue
            # The loader opens `/usr/local/bin/../lib/libpython3.12.so.1.0`;
            # classify what was opened, not how it was spelled.
            path = posixpath.normpath(path) if path.startswith("/") else path
            ok = c.ret is not None and c.ret >= 0
            base = path.rsplit("/", 1)[-1]
            if ok and SONAME.match(base) and path.startswith(LIB_DIRS):
                add(f"lib:{base}", path)
            elif path.startswith("/dev/"):
                add(f"device:{path[5:]}", path)
            elif path.startswith(PATH_ROOTS) and path not in NOT_NEEDS:
                add(f"path:{path.rstrip('/')}", "opened" if ok else f"failed {c.errno}")
        elif c.name == "execve" and c.ret == 0:
            path = _first_path(c.args)
            if path:
                add(f"exec:{path.rsplit('/', 1)[-1]}", path)
        elif c.name == "socket" and c.ret is not None and c.ret >= 0:
            if m := SOCKET.match(c.args):
                sockets[str(c.ret)] = "tcp" if m.group(2) == "SOCK_STREAM" else "udp"
                bound.pop(str(c.ret), None)
        elif c.name == "close" and c.ret == 0:
            fd = c.args.strip()
            sockets.pop(fd, None)
            bound.pop(fd, None)
        elif c.name == "bind" and c.ret == 0:
            fd = c.args.split(",", 1)[0].strip()
            if (p := PORT.search(c.args)) and int(p.group(1)):
                bound[fd] = p.group(1)
                if sockets.get(fd) == "udp":
                    add(f"listen:udp/{p.group(1)}", "bound datagram socket")
        elif c.name == "listen" and c.ret == 0:
            fd = c.args.split(",", 1)[0].strip()
            if port := bound.get(fd):
                add(f"listen:tcp/{port}", "bound and listening")
        elif c.name == "connect":
            fd = c.args.split(",", 1)[0].strip()
            p, a = PORT.search(c.args), ADDR.search(c.args)
            if not (p and a):
                continue
            proto = sockets.get(fd, "tcp")
            host = a.group(1) or a.group(2)
            if host.startswith(LOOPBACK):
                continue                # the application talking to itself
            if p.group(1) == "53":
                # The resolver's address comes from the sandbox's resolv.conf,
                # not from the application; the need is name resolution.
                host = "resolver"
            result = ("connected" if c.ret == 0 else "attempted" if c.errno == "EINPROGRESS"
                      else c.errno or "failed")
            add(f"dial:{proto}/{host}:{p.group(1)}", result)
    return obs
