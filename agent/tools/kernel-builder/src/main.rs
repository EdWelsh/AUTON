//! kernel-builder: drive the kernel `make` build and stage the artifact.

use anyhow::{Context, Result};
use clap::Parser;
use kernel_builder::{artifact_path, make_args, ArchToolchain, BuildOutcome};
use std::path::PathBuf;
use tokio::process::Command;

#[derive(Parser)]
#[command(
    name = "kernel-builder",
    about = "Build orchestration for AUTON kernel"
)]
struct Cli {
    /// Path to the kernel source workspace (holds the Makefile).
    #[arg(short, long, default_value = "kernels/x86_64")]
    workspace: PathBuf,

    /// Target architecture.
    #[arg(short, long, default_value = "x86_64")]
    arch: String,

    /// Directory to copy the built kernel.bin into.
    #[arg(short, long, default_value = "build")]
    output: PathBuf,

    /// Override the C compiler (e.g. x86_64-linux-gnu-gcc).
    #[arg(long)]
    cc: Option<String>,

    /// Make target to build.
    #[arg(long, default_value = "all")]
    target: String,

    /// Clean before building.
    #[arg(long)]
    clean: bool,

    /// Emit the outcome as JSON.
    #[arg(long)]
    json: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();

    let toolchain = ArchToolchain::for_arch(&cli.arch)?;
    let cc = cli.cc.clone().unwrap_or_else(|| toolchain.cc.clone());

    tracing::info!(workspace = %cli.workspace.display(), arch = %cli.arch, cc = %cc, "building kernel");

    let args = make_args(&cli.workspace, &cli.target, cli.clean);
    let out = Command::new("make")
        .args(&args)
        .env("CC", &cc)
        .output()
        .await
        .context("failed to spawn `make` (is it installed?)")?;

    let artifact = artifact_path(&cli.workspace);
    let success = out.status.success() && artifact.exists();

    let mut artifact_out = None;
    if success {
        std::fs::create_dir_all(&cli.output)
            .with_context(|| format!("creating {}", cli.output.display()))?;
        let dest = cli.output.join("kernel.bin");
        std::fs::copy(&artifact, &dest).context("copying kernel artifact")?;
        artifact_out = Some(dest.display().to_string());
    }

    let outcome = BuildOutcome {
        success,
        arch: cli.arch.clone(),
        artifact: artifact_out,
        stdout: String::from_utf8_lossy(&out.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
    };

    if cli.json {
        println!("{}", serde_json::to_string_pretty(&outcome)?);
    } else if success {
        println!(
            "build ok: {}",
            outcome.artifact.as_deref().unwrap_or("(unknown)")
        );
    } else {
        eprintln!("build failed:\n{}", outcome.stderr);
    }

    if !success {
        std::process::exit(1);
    }
    Ok(())
}
