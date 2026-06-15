//! Kernel build orchestration: toolchain mapping and `make` command building.
//!
//! Pure functions live here so they can be unit-tested without a cross
//! compiler; `main.rs` handles process spawning and artifact copying.

use anyhow::{bail, Result};
use serde::Serialize;
use std::path::{Path, PathBuf};

/// Toolchain + QEMU names for a target architecture (mirrors
/// `orchestrator/arch_registry.py`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ArchToolchain {
    pub arch: String,
    pub cc: String,
    pub qemu: String,
}

impl ArchToolchain {
    pub fn for_arch(arch: &str) -> Result<Self> {
        let (cc, qemu) = match arch {
            "x86_64" => ("x86_64-elf-gcc", "qemu-system-x86_64"),
            "aarch64" => ("aarch64-elf-gcc", "qemu-system-aarch64"),
            "riscv64" => ("riscv64-elf-gcc", "qemu-system-riscv64"),
            other => bail!("unsupported architecture: {other}"),
        };
        Ok(Self {
            arch: arch.to_string(),
            cc: cc.to_string(),
            qemu: qemu.to_string(),
        })
    }
}

/// Build the `make` argument vector for a kernel build.
/// Order: `-C <workspace> [clean] <target>`.
pub fn make_args(workspace: &Path, target: &str, clean: bool) -> Vec<String> {
    let mut args = vec!["-C".to_string(), workspace.display().to_string()];
    if clean {
        args.push("clean".to_string());
    }
    args.push(target.to_string());
    args
}

/// Path to the kernel artifact a successful build produces.
pub fn artifact_path(workspace: &Path) -> PathBuf {
    workspace.join("build").join("kernel.bin")
}

/// Whether the given cross compiler is available on PATH.
pub fn toolchain_available(cc: &str) -> bool {
    which::which(cc).is_ok()
}

#[derive(Debug, Serialize)]
pub struct BuildOutcome {
    pub success: bool,
    pub arch: String,
    pub artifact: Option<String>,
    pub stdout: String,
    pub stderr: String,
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn toolchain_for_known_arches() {
        let tc = ArchToolchain::for_arch("x86_64").unwrap();
        assert_eq!(tc.cc, "x86_64-elf-gcc");
        assert_eq!(tc.qemu, "qemu-system-x86_64");
        assert_eq!(
            ArchToolchain::for_arch("aarch64").unwrap().cc,
            "aarch64-elf-gcc"
        );
    }

    #[test]
    fn toolchain_for_unknown_arch_errors() {
        assert!(ArchToolchain::for_arch("m68k").is_err());
    }

    #[test]
    fn make_args_without_clean() {
        let args = make_args(Path::new("kernels/x86_64"), "all", false);
        assert_eq!(args, vec!["-C", "kernels/x86_64", "all"]);
    }

    #[test]
    fn make_args_with_clean_inserts_clean_before_target() {
        let args = make_args(Path::new("/k"), "all", true);
        assert_eq!(args, vec!["-C", "/k", "clean", "all"]);
    }

    #[test]
    fn artifact_path_is_build_kernel_bin() {
        let p = artifact_path(Path::new("kernels/x86_64"));
        assert!(p.ends_with("build/kernel.bin"));
    }

    #[test]
    fn nonexistent_toolchain_is_unavailable() {
        assert!(!toolchain_available("definitely-not-a-real-compiler-xyz"));
    }
}
