"""The HAL boundary gate (windows-linux D1)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from hal_gate import scan, strip_comments  # noqa: E402


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def test_each_violation_kind_in_the_v4_base_is_caught(tmp_path):
    t = _tree(tmp_path, {
        "kernel/net/dhcp.c": 'void f(void) { __asm__ volatile("hlt"); }\n',
        "kernel/boot/kernel_main.c":
            'static void h(void) { for (;;) __asm__ volatile("cli; hlt"); }\n',
        "kernel/dev/pci.c":
            '#include "../arch/x86_64/io/io.h"\nunsigned r(void) { return io_read32(0xCFC); }\n',
    })
    rules = sorted((v.path, v.rule) for v in scan(t))
    assert rules == [("kernel/boot/kernel_main.c", "inline assembly"),
                     ("kernel/dev/pci.c", "architecture header"),
                     ("kernel/dev/pci.c", "port I/O"),
                     ("kernel/net/dhcp.c", "inline assembly")]


def test_arch_territory_is_exempt(tmp_path):
    t = _tree(tmp_path, {
        "kernel/arch/x86_64/hal.c": 'void arch_halt(void) { __asm__ volatile("hlt"); }\n',
        "kernel/drivers/arch/serial_16550.c": '#include "../../arch/x86_64/io/io.h"\n',
    })
    assert scan(t) == []


def test_comments_and_strings_do_not_trip_it(tmp_path):
    """A gate that fires on prose about "hlt-yielding poll loops" gets ignored."""
    t = _tree(tmp_path, {"kernel/net/setup.c": (
        "/* the old code did __asm__ volatile(\"hlt\") here */\n"
        "// io_write32(0xCF8, x) was the x86 path\n"
        'static const char *s = "asm(\\"hlt\\")";\n'
        "char q = '\"';\n"
        "void f(void) { arch_halt(); }\n")})
    assert scan(t) == []


def test_line_numbers_survive_stripping():
    src = '/* a\n b */\nint x;\n__asm__("nop");\n'
    assert strip_comments(src).splitlines()[3].startswith("__asm__")


def test_an_include_path_after_another_include_is_still_seen(tmp_path):
    """The first stripper treated the first include's closing quote as an
    opening one and blanked the next line: 0 violations on a tree with 10."""
    t = _tree(tmp_path, {
        "kernel/dev/pci.c": '#include "pci.h"\n#include "../arch/x86_64/io/io.h"\n'})
    assert [v.rule for v in scan(t)] == ["architecture header"]
