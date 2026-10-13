"""w24 F-2: inline assembly in portable kernel code is named by file:line."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "tests/kernel/portable_asm_check.sh"


def _run(tree: Path):
    return subprocess.run([str(SCRIPT), str(tree)], capture_output=True, text=True)


def test_reports_inline_asm_with_file_and_line(tmp_path):
    (tmp_path / "kernel/mm").mkdir(parents=True)
    (tmp_path / "kernel/mm/pmm.c").write_text('void p(void){ __asm__ volatile("cli; hlt"); }\n')
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "inline assembly in portable code" in r.stderr and "pmm.c:1" in r.stderr


def test_clean_tree_and_arch_dirs_pass(tmp_path):
    (tmp_path / "kernel/mm").mkdir(parents=True)
    (tmp_path / "kernel/mm/pmm.c").write_text("void p(void){ arch_halt(); }\n")
    (tmp_path / "kernel/arch").mkdir()
    (tmp_path / "kernel/arch/x.c").write_text('void h(void){ __asm__("hlt"); }\n')
    assert _run(tmp_path).returncode == 0
