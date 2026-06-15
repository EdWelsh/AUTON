//! Integration tests for QEMU command construction.

use test_runner::{qemu_args, qemu_binary};

#[test]
fn x86_iso_launch_args() {
    let args = qemu_args("build/auton.iso", None, 128);
    assert!(args.windows(2).any(|w| w == ["-cdrom", "build/auton.iso"]));
    assert!(args.iter().any(|a| a == "-serial"));
    assert!(args.iter().any(|a| a == "stdio"));
    assert!(args.iter().any(|a| a == "-no-reboot"));
}

#[test]
fn aarch64_raw_launch_uses_machine_and_kernel() {
    let args = qemu_args("build/kernel.bin", Some("virt"), 256);
    assert!(args.windows(2).any(|w| w == ["-machine", "virt"]));
    assert!(args
        .windows(2)
        .any(|w| w == ["-kernel", "build/kernel.bin"]));
    assert!(args.contains(&"256M".to_string()));
}

#[test]
fn binary_resolution_per_arch() {
    assert_eq!(qemu_binary("x86_64"), Some("qemu-system-x86_64"));
    assert_eq!(qemu_binary("aarch64"), Some("qemu-system-aarch64"));
    assert_eq!(qemu_binary("unknown"), None);
}
