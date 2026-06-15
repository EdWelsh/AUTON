//! Integration tests for serial-output parsing.

use test_runner::parse_serial;

#[test]
fn full_boot_sequence_is_success() {
    let out = "\
AUTON Kernel booting
[BOOT] Long mode enabled
[DRV] Serial 16550 initialized
[SLM] Ready
[BOOT] OK
";
    let s = parse_serial(out);
    assert!(s.success);
    assert!(s.boot_ok);
    assert_eq!(s.failed, 0);
}

#[test]
fn captures_named_test_results() {
    let out = "[TEST] pmm_alloc_free: PASS\n[TEST] vmm_map_page: PASS\n[BOOT] OK\n";
    let s = parse_serial(out);
    assert_eq!(s.passed, 2);
    assert_eq!(s.tests[0].name, "pmm_alloc_free");
    assert!(s.success);
}

#[test]
fn a_single_failure_fails_the_run() {
    let out = "[TEST] a: PASS\n[TEST] b: FAIL - bad\n[BOOT] OK\n";
    let s = parse_serial(out);
    assert!(!s.success);
    assert_eq!(s.failed, 1);
}
