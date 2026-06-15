//! Cross-compilation wiring tests: the QEMU binary paired with each toolchain.

use kernel_builder::ArchToolchain;

#[test]
fn toolchain_pairs_cc_with_matching_qemu() {
    let x86 = ArchToolchain::for_arch("x86_64").unwrap();
    assert_eq!(x86.qemu, "qemu-system-x86_64");

    let rv = ArchToolchain::for_arch("riscv64").unwrap();
    assert_eq!(rv.cc, "riscv64-elf-gcc");
    assert_eq!(rv.qemu, "qemu-system-riscv64");
}
