//! diff-validator: static analysis of agent-proposed C-kernel diffs.

use anyhow::{Context, Result};
use clap::Parser;
use diff_validator::{has_errors, validate};
use std::io::Read;
use std::path::PathBuf;

#[derive(Parser)]
#[command(
    name = "diff-validator",
    about = "Validate agent-proposed C code diffs"
)]
struct Cli {
    /// Unified diff file to validate. Reads stdin if omitted.
    #[arg(short, long)]
    input: Option<PathBuf>,

    /// Emit findings as JSON.
    #[arg(long)]
    json: bool,
}

fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();

    let diff = match &cli.input {
        Some(path) => {
            std::fs::read_to_string(path).with_context(|| format!("reading {}", path.display()))?
        }
        None => {
            let mut buf = String::new();
            std::io::stdin()
                .read_to_string(&mut buf)
                .context("reading stdin")?;
            buf
        }
    };

    let findings = validate(&diff);

    if cli.json {
        println!("{}", serde_json::to_string_pretty(&findings)?);
    } else if findings.is_empty() {
        println!("diff-validator: no issues");
    } else {
        for f in &findings {
            println!(
                "{:?}\t{}:{}\t{}\t{}",
                f.severity, f.file, f.line, f.rule, f.message
            );
        }
    }

    if has_errors(&findings) {
        std::process::exit(1);
    }
    Ok(())
}
