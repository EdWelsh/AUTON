//! Integration tests for `make` command generation.

use kernel_builder::{artifact_path, make_args};
use std::path::Path;

#[test]
fn plain_build_command() {
    let args = make_args(Path::new("kernels/x86_64"), "all", false);
    assert_eq!(args, vec!["-C", "kernels/x86_64", "all"]);
}

#[test]
fn clean_build_command() {
    let args = make_args(Path::new("kernels/aarch64"), "all", true);
    assert_eq!(args, vec!["-C", "kernels/aarch64", "clean", "all"]);
}

#[test]
fn artifact_is_build_kernel_bin() {
    assert!(artifact_path(Path::new("kernels/x86_64")).ends_with("build/kernel.bin"));
}
