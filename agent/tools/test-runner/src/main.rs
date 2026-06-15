//! test-runner: boot a kernel image in QEMU, capture serial, parse results.

use anyhow::{Context, Result};
use clap::Parser;
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;
use test_runner::{parse_serial, qemu_args, qemu_binary};
use tokio::process::Command;
use tokio::time::timeout;

#[derive(Parser)]
#[command(name = "test-runner", about = "QEMU-based kernel test execution")]
struct Cli {
    /// Path to the kernel image (.iso boots via -cdrom, else -kernel).
    #[arg(short, long)]
    kernel: PathBuf,

    /// Target architecture (selects the qemu binary).
    #[arg(short, long, default_value = "x86_64")]
    arch: String,

    /// QEMU machine type (e.g. "virt" for aarch64/riscv64).
    #[arg(long)]
    machine: Option<String>,

    /// Memory in MiB.
    #[arg(long, default_value = "128")]
    memory: u32,

    /// Timeout in seconds (a hang counts as failure).
    #[arg(short, long, default_value = "60")]
    timeout: u64,

    /// Emit the summary as JSON.
    #[arg(long)]
    json: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();

    let qemu = qemu_binary(&cli.arch)
        .with_context(|| format!("unsupported architecture: {}", cli.arch))?;
    let image = cli.kernel.display().to_string();
    let args = qemu_args(&image, cli.machine.as_deref(), cli.memory);

    tracing::info!(qemu, image = %image, "launching QEMU");

    let child = Command::new(qemu)
        .args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .with_context(|| format!("failed to spawn {qemu} (is it installed?)"))?;

    let output = match timeout(Duration::from_secs(cli.timeout), child.wait_with_output()).await {
        Ok(res) => res.context("waiting for QEMU")?,
        Err(_) => {
            // Timed out: the kernel likely hung. Report a clean failure.
            eprintln!(
                "test-runner: QEMU timed out after {}s (possible hang)",
                cli.timeout
            );
            std::process::exit(2);
        }
    };

    let serial = String::from_utf8_lossy(&output.stdout);
    let summary = parse_serial(&serial);

    if cli.json {
        println!("{}", serde_json::to_string_pretty(&summary)?);
    } else {
        println!(
            "boot_ok={} tests {}/{} passed",
            summary.boot_ok, summary.passed, summary.total
        );
        for t in &summary.tests {
            let status = if t.passed { "PASS" } else { "FAIL" };
            println!("  {status} {} {}", t.name, t.message);
        }
    }

    if !summary.success {
        std::process::exit(1);
    }
    Ok(())
}
