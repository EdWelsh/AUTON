//! Timeout-handling behavior is exercised at the binary level (a hung kernel
//! exits with code 2). Here we assert the parsing invariant the timeout path
//! relies on: partial/garbage serial with no [BOOT] OK is not a success.

use test_runner::parse_serial;

#[test]
fn partial_output_without_boot_ok_is_not_success() {
    // Simulates a kernel that hung mid-boot (timeout would kill it).
    let out = "AUTON Kernel booting\n[BOOT] Long mode enabled\n";
    let s = parse_serial(out);
    assert!(!s.boot_ok);
    assert!(!s.success);
}

#[test]
fn empty_output_is_not_success() {
    let s = parse_serial("");
    assert!(!s.success);
    assert_eq!(s.total, 0);
}
