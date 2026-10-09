"""The pure parts of the VM substrate (w23 C3). Booting is in the integration test."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "agent" / "tools"))

from app_probe import ProbeError
from vm_probe import forwards, guest_spec, refuse_unsupported


def test_guest_spec_reads_the_images_entrypoint_cmd_env_and_cwd():
    g = guest_spec({"Config": {"Entrypoint": ["/whoami"], "Cmd": None, "Env": ["A=1"],
                               "WorkingDir": ""}})
    assert g == {"entrypoint": ["/whoami"], "cmd": [], "env": ["A=1"], "cwd": "/"}


def test_each_checked_guest_port_gets_a_distinct_host_port():
    spec = {"checks": [{"kind": "http", "port": 80}, {"kind": "http", "port": 80},
                       {"kind": "tcp", "port": 25}]}
    assert forwards(spec, 4000) == [(4000, 25), (4001, 80)]


def test_an_exec_check_is_refused_not_faked():
    with pytest.raises(ProbeError, match="exec check"):
        refuse_unsupported({"checks": [{"kind": "exec", "command": ["true"]}]})
    refuse_unsupported({"checks": [{"kind": "http", "port": 80}]})


def test_the_failure_detail_drops_kernel_lines_and_keeps_the_applications():
    from vm_probe import _app_tail
    logs = "AUTON-VM: tcg\nImportError: libssl.so.3: cannot open\nAUTON-VM: application exited 1\n[    2.6] Memory Limit: none\n"
    assert "libssl.so.3" in _app_tail(logs) and "Memory Limit" not in _app_tail(logs)
    assert _app_tail("") == "(none)"
