# Status and Roadmap

As of 2026-10-17. The live index is
[`docs/OPEN-WORK.md`](https://github.com/EdWelsh/AUTON/blob/HEAD/docs/OPEN-WORK.md); the
latest audit is [`w26`](https://github.com/EdWelsh/AUTON/blob/HEAD/.claude/PRPs/plans/w26-drift-and-slm-readiness.plan.md).

## What works

- Two generated results pass their frozen gates: TFTP (31/31) and the VirtIO console driver
  (29 checks).
- The kernel base boots to the chat with DHCP and an in-kernel web server; the neural backend
  loads an AUTON-format model and matches PyTorch token for token.
- Application to environment: 1 of 3 subjects fully agent-driven, 2 of 3 with a longer budget.
- Hardware knowledge: 5,164 vendors, 284 processor models, every x86 CPUID bit, cited
  exceptions.
- Four swarms with launchers that keep their output in testing areas.

## What does not yet

| Item | State | Next step |
|---|---|---|
| Generation campaign | 1 of 12 passed; R1 attempt 3 stopped by the owner | pre-register the next attempt (specialists are the change), run R1 |
| Kernel chat quality | 78% correct-or-honest, 22% garbage; bar <10% garbage | SLM swarm on the kernel set; more grounded phrasings |
| `cpu` subsystem | specified, not generated | frozen host suite with a fake `cpuid()`, then a run |
| Vendor coverage | 18 of 5,164 vendors documented; 9 exceptions unverified | run the Vendor Scout and Spec Reader |
| e2e spine | trains on the 12-row legacy corpus | point it at the kernel set with `chat_tiny` |
| Default kernel paths | scripts default to `kernels/x86_64` at the repo root | move the default to `.artifacts/kernels/x86_64` |
| TLS | none, deliberately | its own phase: reuse or port, never synthesise (blocks scenarios C4, C5) |

## Owner decisions

| Decision | Where |
|---|---|
| Kernel tokenizer: stay word-level, or move to subword | `SLM/DATA.md` |
| Doom engine licence (distribution only) | `agent/kernel_spec/decisions/doom-engine-licence.md` |
| Fleet conformance endpoint, if any | `decisions/fleet-endpoint.md` |
| First substrate; syscall scope; subject trust | `decisions/first-substrate.md`, `syscall-scope.md`, `subject-trust.md` |
| Hardware: an x86 machine, Intel NIC docs, Proxmox / Windows 11 / bare metal | `docs/ACQUIRE.md` |

## The scenarios: the swarm's exam

| # | Sentence | Proved by |
|---|---|---|
| C1 | "I want to play Doom" | a non-blank frame that Escape changes beyond idle animation |
| C2 | "host this repo" | `git clone` of the served URL matches HEAD |
| C3 | "be an email server" | smtplib delivers; a reboot keeps it |
| C4 | "a database with RBAC and OAuth" | needs TLS |
| C5 | "interact with yedgi.com" | needs TLS |
| C6 | "my laptop won't connect to wifi" | real silicon and a wifi driver |
