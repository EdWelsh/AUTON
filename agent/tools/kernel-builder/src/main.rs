use anyhow::Result;
use clap::Parser;
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "kernel-builder", about = "Build orchestration for AUTON kernel")]
struct Cli {
    /// Path to the kernel source workspace
    #[arg(short, long, default_value = "workspace")]
    workspace: PathBuf,

    /// Target architecture
    #[arg(short, long, default_value = "x86_64")]
    arch: String,

    /// Output directory for build artifacts
    #[arg(short, long, default_value = "build")]
    output: PathBuf,

    /// Clean build (remove all artifacts first)
    #[arg(long)]
    clean: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();

    tracing::info!(
        workspace = %cli.workspace.display(),
        arch = %cli.arch,
        "Starting kernel build"
    );

    // TODO: Implement cross-compilation pipeline
    // 1. Assemble boot code (nasm)
    // 2. Compile C kernel sources (x86_64-elf-gcc)
    // 3. Link into bootable image
    // 4. Generate QEMU-bootable disk image

    println!("kernel-builder: not yet implemented");
    Ok(())
}
