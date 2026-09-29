"""strace → observed facts, on traces captured from real sandboxed runs (A5).

`dlopen-only.strace`: a C program that dlopens a library whose name it builds
from a config file. `flask-hello.strace.gz`: the Flask fixture, exercised over
HTTP, then asked to dial a database under --network none. Both captured on
aarch64 Linux (Rancher Desktop), 2026-09-29, with the sandbox's own flags.
"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from observe_parse import calls, observe_text  # noqa: E402

TRACES = ROOT / "agent" / "tests" / "fixtures" / "traces"
DLOPEN = (TRACES / "dlopen-only.strace").read_text()
FLASK = gzip.decompress((TRACES / "flask-hello.strace.gz").read_bytes()).decode()


def test_a_dlopened_library_is_observed():
    obs = observe_text(DLOPEN)
    assert "lib:libz.so.1" in obs.facts
    assert obs.facts["lib:libz.so.1"]["detail"].endswith("/libz.so.1")


def test_the_loaders_own_files_are_not_needs():
    assert not any(c.startswith("path:/etc/ld.so") for c in observe_text(DLOPEN).facts)


def test_a_name_outside_the_index_is_reported_not_stamped():
    """The tool may not stretch the vocabulary any more than an agent may."""
    obs = observe_text(FLASK)
    assert "lib:libpython3.12.so.1.0" in obs.unindexed["lib"]
    assert "lib:libpython3.12.so.1.0" not in obs.facts


def test_the_flask_app_needs_what_it_actually_loaded():
    facts = observe_text(FLASK).facts
    assert {"lib:libssl.so.3", "lib:libcrypto.so.3", "listen:tcp/8000"} <= set(facts)
    assert facts["listen:tcp/8000"]["detail"] == "bound and listening"


def test_a_failed_open_is_still_a_need():
    facts = observe_text(FLASK).facts
    assert facts["path:/usr/share/locale/locale.alias"]["detail"] == "failed ENOENT"


def test_a_dial_is_recorded_with_its_result_and_dns_by_role():
    facts = observe_text(FLASK).facts
    assert facts["dial:udp/resolver:53"]["detail"] == "ENETUNREACH"
    assert not any("192.168.5.2" in c for c in facts), "the sandbox's resolver is not a need"


def test_syscalls_are_reported_never_facts():
    obs = observe_text(FLASK)
    assert {"openat", "bind", "listen"} <= obs.syscalls
    assert not any(c.startswith("syscalls:") for c in obs.facts)


def test_unfinished_and_resumed_calls_are_joined():
    text = ('7 openat(AT_FDCWD, "/lib/x/libssl.so.3", O_RDONLY <unfinished ...>\n'
            '8 getpid() = 8\n'
            '7 <... openat resumed>) = 3\n')
    [first, second] = calls(text)
    assert first.name == "getpid" and second.name == "openat" and second.ret == 3
    assert "lib:libssl.so.3" in observe_text(text).facts
