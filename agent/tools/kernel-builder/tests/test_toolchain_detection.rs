//! Integration tests for toolchain mapping/detection.

use kernel_builder::{toolchain_available, ArchToolchain};

#[test]
fn maps_each_supported_arch() {
    assert_eq!(
        ArchToolchain::for_arch("x86_64").unwrap().cc,
        "x86_64-elf-gcc"
    );
    assert_eq!(
        ArchToolchain::for_arch("aarch64").unwrap().cc,
        "aarch64-elf-gcc"
    );
    assert_eq!(
        ArchToolchain::for_arch("riscv64").unwrap().cc,
        "riscv64-elf-gcc"
    );
}

#[test]
fn rejects_unsupported_arch() {
    assert!(ArchToolchain::for_arch("powerpc").is_err());
}

#[test]
fn detects_missing_compiler() {
    assert!(!toolchain_available("no-such-compiler-12345"));
}
