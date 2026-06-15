//! QEMU test-runner core: serial-output parsing and QEMU command construction.
//!
//! Mirrors the marker contract in
//! `orchestrator/validation/test_validator.py`:
//!   [TEST] name: PASS
//!   [TEST] name: FAIL - reason
//!   [BOOT] OK

use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct TestCase {
    pub name: String,
    pub passed: bool,
    pub message: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct TestSummary {
    pub success: bool,
    pub total: usize,
    pub passed: usize,
    pub failed: usize,
    pub boot_ok: bool,
    pub tests: Vec<TestCase>,
}

fn parse_test_line(line: &str) -> Option<TestCase> {
    let idx = line.find("[TEST]")?;
    let rest = line[idx + "[TEST]".len()..].trim();
    let (name, after) = rest.split_once(':')?;
    let after = after.trim();
    let (result, message) = match after.split_once('-') {
        Some((r, m)) => (r.trim(), m.trim().to_string()),
        None => (after, String::new()),
    };
    let passed = match result {
        "PASS" => true,
        "FAIL" => false,
        _ => return None,
    };
    Some(TestCase {
        name: name.trim().to_string(),
        passed,
        message,
    })
}

/// Parse serial output into a structured test summary.
pub fn parse_serial(output: &str) -> TestSummary {
    let tests: Vec<TestCase> = output.lines().filter_map(parse_test_line).collect();
    let boot_ok =
        output.contains("[BOOT] OK") || output.to_lowercase().contains("kernel initialized");
    let passed = tests.iter().filter(|t| t.passed).count();
    let failed = tests.len() - passed;
    // Success requires the kernel to have booted with no failing tests. Garbage
    // serial output (no `[BOOT] OK`, no tests) is a failure, not a vacuous pass.
    let success = failed == 0 && boot_ok;
    TestSummary {
        success,
        total: tests.len(),
        passed,
        failed,
        boot_ok,
        tests,
    }
}

/// Build the QEMU argument vector for booting a kernel image.
///
/// `.iso` images boot via `-cdrom` (GRUB/Multiboot2 ELF64 path); everything
/// else boots via `-kernel`. `machine` adds `-machine <m>` for non-x86 arches.
pub fn qemu_args(image: &str, machine: Option<&str>, memory_mb: u32) -> Vec<String> {
    let mut args = Vec::new();
    if let Some(m) = machine {
        args.push("-machine".to_string());
        args.push(m.to_string());
    }
    let media = if image.ends_with(".iso") {
        "-cdrom"
    } else {
        "-kernel"
    };
    args.push(media.to_string());
    args.push(image.to_string());
    for a in ["-serial", "stdio", "-display", "none", "-no-reboot", "-m"] {
        args.push(a.to_string());
    }
    args.push(format!("{memory_mb}M"));
    args
}

/// QEMU binary name for a target architecture.
pub fn qemu_binary(arch: &str) -> Option<&'static str> {
    match arch {
        "x86_64" => Some("qemu-system-x86_64"),
        "aarch64" => Some("qemu-system-aarch64"),
        "riscv64" => Some("qemu-system-riscv64"),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_pass_and_fail_with_reason() {
        let out = "[TEST] pmm_alloc: PASS\n[TEST] vmm_map: FAIL - null page\n[BOOT] OK\n";
        let s = parse_serial(out);
        assert_eq!(s.total, 2);
        assert_eq!(s.passed, 1);
        assert_eq!(s.failed, 1);
        assert!(s.boot_ok);
        assert!(!s.success); // a failure present
        assert_eq!(s.tests[1].message, "null page");
    }

    #[test]
    fn boot_only_no_tests_is_success() {
        let s = parse_serial("AUTON Kernel booting\n[BOOT] OK\n");
        assert!(s.success);
        assert_eq!(s.total, 0);
        assert!(s.boot_ok);
    }

    #[test]
    fn no_boot_marker_with_no_tests_is_failure() {
        let s = parse_serial("garbage\n");
        assert!(!s.success);
        assert!(!s.boot_ok);
    }

    #[test]
    fn iso_image_uses_cdrom() {
        let args = qemu_args("build/auton.iso", None, 128);
        assert!(args.windows(2).any(|w| w == ["-cdrom", "build/auton.iso"]));
        assert!(args.contains(&"128M".to_string()));
    }

    #[test]
    fn raw_image_uses_kernel_and_machine() {
        let args = qemu_args("build/kernel.bin", Some("virt"), 256);
        assert!(args.windows(2).any(|w| w == ["-machine", "virt"]));
        assert!(args
            .windows(2)
            .any(|w| w == ["-kernel", "build/kernel.bin"]));
    }

    #[test]
    fn qemu_binary_known_arches() {
        assert_eq!(qemu_binary("x86_64"), Some("qemu-system-x86_64"));
        assert_eq!(qemu_binary("riscv64"), Some("qemu-system-riscv64"));
        assert_eq!(qemu_binary("sparc"), None);
    }
}
