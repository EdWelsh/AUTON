# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub:

1. Go to the [Security tab](https://github.com/EdWelsh/AUTON/security) of this
   repository.
2. Choose **Report a vulnerability**.
3. Describe the problem, how to reproduce it, and what an attacker gets.

This creates a private advisory visible only to you and the maintainers. If
private reporting is not available on the repository, open a normal issue that
says only *"security report, please enable private reporting"* — with no
details — and wait to be contacted.

There is no published security email. That is deliberate: this is a personal
project and a scraped address helps nobody.

## What to expect

This is a single-maintainer project with no funded on-call rotation, so please
calibrate: there is no guaranteed response time and no bug bounty. Reports are
handled on a best-effort basis, and you will get an acknowledgement when the
maintainer next picks up the repository.

If a report is valid and you would like credit, say so and you will be credited
in the advisory.

## Scope

This repository contains an **agent orchestration system** and the
**specifications and test harnesses** for an operating system kernel. What is
in scope follows from that.

### In scope

- **The orchestrator** (`agent/`) — in particular anything that lets a model's
  output escape its sandbox: path traversal in the file tools, the shell
  allowlist in `orchestrator/agents/base_agent.py`, or command construction that
  could be injected into.
- **The host control plane** (`controlplane/`) — it launches processes, sends
  email and drives desktop applications on the user's machine. Privilege
  mistakes, unsafe command construction and approval bypasses matter here. The
  approval gate defaulting to anything other than *deny* is a security bug, not
  a usability one.
- **Build and CI scripts** (`scripts/`, `.github/workflows/`) — anything that
  executes untrusted input, or that would let a fork's pull request obtain
  secrets.
- **The kernel specifications and gates** (`agent/kernel_spec/`,
  `tests/kernel/`) — a gate that can be made to pass a vulnerable
  implementation is a real finding. So is a specification that mandates
  something unsafe.

### Out of scope

- **Vulnerabilities in a kernel the agents generated.** Generated kernels are
  experimental output, are not distributed, and are not intended to be run
  anywhere but a disposable VM. A weakness there is a *specification or gate*
  problem — report it as that, which is in scope and more useful.
- **The absence of features.** There is no TLS, no authentication in the
  in-kernel HTTP server, and no isolation between chat roles. These are stated
  gaps, not undiscovered ones. See
  [`docs/OPEN-WORK.md`](docs/OPEN-WORK.md).
- **Anything requiring a model to be deliberately adversarial while you supply
  the model, the prompt and the API key.** Running an untrusted model against
  your own machine is the threat model you chose.
- Findings from automated scanners with no demonstrated impact.

## Running AUTON safely

Some of this is worth saying plainly, because the defaults are permissive by
design in an experimental tool:

- **Boot generated kernels in a VM.** QEMU with no host devices passed through.
  They are unreviewed machine-generated systems software.
- **The control plane really does act on your machine.** `auton-do` launches
  processes, edits files and sends email. Its approval gate defaults to *deny*;
  `--yes` and `always_allow` remove that. Do not run it unattended against
  anything you care about.
- **Agents run with your credentials.** An orchestration run can spend real
  money against a real API key and commits to real git branches. Prefer a
  scratch workspace and a spend limit.
- **`.gitignore` is load-bearing.** `agent/config/auton.toml` holds API keys and
  is ignored; only `auton.toml.example` is tracked. Check before you commit.

## Supported versions

The project is pre-1.0 and under active development. Only `main` is supported;
there are no maintained release branches and no backports.
