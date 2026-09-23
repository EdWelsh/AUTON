# AUTON on Windows and Linux

> **Closed 2026-09-23. Superseded for everything still open by**
> [`auton-completion.prd.md`](../auton-completion.prd.md).
>
> Phases 0, A1, A3, B1, B2, B4, B5, C2, D2 are carried to **R1, R9, D3, X4**, each with the gate that decides it. The phases below record what was built and what it was measured against; nothing open is tracked here any more, so there is one place to look rather than five.

**Status**: draft

> **Repo-state correction (2026-09-12).** This PRD observed that "two of the three declared
> target architectures have no source tree at all". That is now true of **all three**, by
> design: `kernels/` is gitignored as agent-generated output (`README.md:11`). A missing
> aarch64 or riscv64 tree is therefore no longer a gap to fill by hand — it is a generation
> target, and the HAL contract in `agent/kernel_spec/arch/hal.md` plus the per-arch specs are
> the input. Portability becomes "can the agents generate for this target?" rather than "who
> ports the tree?", which is a question about the generation engine
> ([`auton-service-kernel-factory.prd.md`](./auton-service-kernel-factory.prd.md)) and not
> about this PRD.
>
> What remains entirely valid here, and is unaffected: every verified fact is a fact about one
> Apple Silicon Mac, the kernel has only booted under emulation, the control plane has only
> run on macOS, and three of five OS profiles are gated behind an unwired KVM host. Real
> hardware and a second host OS are still the missing signals.

> Companion to [auton-e2e-train-boot-human-test.prd.md](./auton-e2e-train-boot-human-test.prd.md),
> which establishes the macOS-native bench. This PRD takes AUTON off one Mac —
> across dev hosts, onto real hardware, and toward other architectures.

## Problem Statement

Every verified fact about AUTON is a fact about one Apple Silicon Mac. The kernel has only
ever booted under emulation, the control plane has only ever run on macOS, three of the five
OS profiles are gated behind a KVM host nobody has wired up, and none of the three declared target
architectures has a tracked source tree — now by design rather than omission. AUTON is a chat OS that has never met real
hardware and cannot be built by anyone who isn't sitting at this laptop. The cost: no
performance signal (everything is TCG-emulated), no portability signal, and a growing gap
between what `arch_registry.py` and the specs claim and what exists.

## Evidence

- `kernels/` contains exactly one directory: `x86_64`. `arch_registry.py` defines complete
  `aarch64` (PL011/GICv2, DTB boot, Sv-style 4-level TT) and `riscv64` (NS16550/PLIC/CLINT,
  SBI+DTB, Sv39) profiles. `agent/kernel_spec/arch/{aarch64,riscv64,hal}.md` all exist.
  **Zero lines of aarch64 or riscv64 kernel source have been written.**
- The kernel has no `mm/`, no `fs/`, no `sched/`. `kernel_main.c` prints
  `[MM] PMM initialized: %u pages free` above the comment *"Minimal physical memory
  accounting (bitmap PMM lands later)"* and `[SCHED] Scheduler initialized` above
  *"Scheduler is a stub in the seed; the marker reflects init ran."*
- Exactly one NIC driver exists (`net/e1000.c`, matched on PCI id `8086:100e` — QEMU's
  emulated card). No storage driver of any kind. No USB. No AHCI/NVMe.
- `grub/grub.cfg` + `grub-mkrescue` produce a **BIOS/i386-pc El Torito** ISO. Most hardware
  manufactured in the last decade is UEFI-first, and many machines are UEFI-only.
- `controlplane/backends/os/profiles.py`: of five OS profiles, `linux` is `REAL`,
  `windows` is `EXPERIMENTAL` (Wine) or `NEEDS_KVM` (dockur), `android` and `macos` are
  `NEEDS_KVM`, `ios` is `EXTERNAL`. Three of five have never run, because no KVM host is wired in.
- Every kernel boot to date has been QEMU under TCG — on macOS, nested inside an emulated
  amd64 Docker container. There is no measurement of AUTON on native-speed x86 anywhere.
- The user owns a Proxmox KVM host. It is referenced in the OS backend's design and has
  never been used.

## Proposed Solution

Four independent lanes, each of which stands alone if the others stall. **Lane A** ports the
E2E bench to Linux and Windows dev hosts — Linux natively (apt gives the entire toolchain
*and* KVM), Windows via WSL2 (GRUB has no native Windows path; pretending otherwise wastes a
week). **Lane B** takes AUTON to real hardware in stages — KVM-accelerated on Proxmox first
(same virtual devices, real speed, ~zero new driver work), then a real machine, which forces
UEFI, real NICs, and storage. **Lane C** makes the Windows and Linux control-plane profiles
honest by giving them a real KVM host to run on. **Lane D** attacks the architecture debt by
building the HAL that `hal.md` already specifies and standing up one non-x86 target.

Lane A is sequenced first and Lane B's KVM step second, because together they turn a
15-minute emulated boot loop into a near-instant one — every other lane gets faster.

## Key Hypothesis

We believe a Linux dev bench with KVM will make AUTON's build-boot-test loop fast enough to
iterate on, and that booting on real hardware will convert "AUTON is a chat OS" from a demo
into a claim.
We'll know we're right when the same `scripts/e2e.sh` passes on macOS, Linux, and WSL2; when
the KVM boot is at least 10x faster than the TCG boot; and when AUTON boots on a physical
machine and answers `what is my ip` with an address from a real DHCP server.

## What We're NOT Building

- **Native Windows kernel builds.** `grub-mkrescue` has no supported native-Windows path.
  Windows support means WSL2, stated plainly. Windows *is* first-class for the control plane.
- **A general-purpose OS.** No process model, no multi-user, no package manager runtime. Real
  hardware means "boots and chats on real hardware," not "replaces your Linux install."
- **Dual-boot installers or disk partitioning.** AUTON boots from removable media (USB/ISO)
  or as a VM. Nothing writes to a host's system disk.
- **Driver breadth.** One NIC family and one storage controller family per hardware target,
  chosen to match one specific test machine. Not a driver ecosystem.
- **All three architectures.** Lane D delivers the HAL plus **one** additional arch. The
  third stays a spec.

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| Hosts running the full E2E green | 3 of 3 (macOS, Linux, WSL2) | `scripts/e2e.sh` per host, artifacts retained |
| KVM boot speedup vs TCG | ≥ 10x on boot-to-`auton>` | Timed, same ISO, both hosts |
| Real-hardware boot | Boots to `auton>` on one physical x86 machine | Serial capture over USB-TTL or IPMI |
| Real-hardware networking | `what is my ip` returns a real LAN DHCP lease | Cross-checked against the router's lease table |
| Control-plane profiles honest | 5/5 profiles either run or refuse with a stated reason | Lane C assertion suite |
| KVM-only profiles proven | ≥ 2 of {windows-dockur, android, macos-dockur} actually boot | Manual, on Proxmox |
| HAL adoption | 0 direct arch calls left in portable `kernel/` code | Grep gate in the build |
| Second architecture | Boots to `auton>` in QEMU | Arch-specific acceptance markers |

## Open Questions

- [ ] Which physical machine is the hardware target? Everything in Lane B — UEFI vs BIOS, NIC
      driver, storage controller, serial access method — is determined by that one choice.
      **Cannot plan Lane B further without it.**
- [ ] Is the Proxmox host reachable from this Mac, and how (SSH, API token, VPN)? Lanes B and C
      both depend on it.
- [ ] UEFI: add a `x86_64-efi` GRUB target, or sidestep with a BIOS/CSM-capable test machine?
      CSM is disappearing from firmware, so this is a "when," not an "if."
- [ ] Does the Windows control plane need a native install, or is WSL2 acceptable there too?
      The desktop surface (pywebview) and app-launch backend behave differently.
- [ ] aarch64 or riscv64 for Lane D? aarch64 has the better hardware story (the dev machine is
      arm64 — QEMU would run it *natively*, making it the fastest target of all). riscv64 is
      the cleaner spec. Leaning aarch64 on iteration speed.
- [ ] Does the HAL refactor invalidate the neural-backend SSE work, which is x86-specific by
      construction? `kmath.c` and the SSE compile profile need an arch-conditional story.

---

## Users & Context

**Primary User**
- **Who**: The AUTON developer, working across a Mac laptop and a Proxmox KVM host, and
  intermittently a Windows machine.
- **Current behavior**: Builds and boots only on the Mac, under nested emulation, at a speed
  that discourages iteration. Never runs the KVM-only OS profiles because the plumbing to
  the Proxmox box doesn't exist.
- **Trigger**: Wanting a fast loop; wanting to know whether AUTON is real outside QEMU;
  wanting the OS profiles that were designed and never exercised.
- **Success state**: Builds anywhere, boots fast on Linux, boots at all on metal, and the
  control plane tells the truth on every host it runs on.

**Job to Be Done**
When I sit down at whichever machine I have, I want to build, boot, and talk to AUTON at a
speed that doesn't punish me, so I can find out whether it works outside the one place it
was born.

**Non-Users**
Not for people installing AUTON as their OS. Not for cloud/server deployment. Not for
Windows users wanting a native (non-WSL) kernel build — that path is explicitly closed.

---

## Solution Detail

### Core Capabilities (MoSCoW)

| Priority | Capability | Rationale |
|----------|------------|-----------|
| Must | Linux dev bench (native toolchain + KVM) | Strictly the best bench: apt has everything, and KVM removes the emulation tax entirely |
| Must | Host-agnostic E2E entry point | One script, per-host preflight; without it "works on 3 hosts" can't be asserted |
| Must | KVM boot on Proxmox | Same virtual hardware, real speed — the highest value-per-unit-work item in this PRD |
| Should | WSL2 Windows dev bench | Third host; mostly a documentation and preflight exercise once Linux works |
| Should | Control-plane KVM profiles made real | Three designed-and-never-run profiles finally exercised |
| Should | Real-hardware boot (one machine) | The claim that turns AUTON from demo to OS |
| Could | UEFI boot path | Required for most modern metal; deferrable if the test machine has CSM |
| Could | HAL extraction + second architecture | Pays down the largest spec-vs-reality gap in the repo |
| Won't | Third architecture, driver breadth, installers | Explicitly deferred above |

### MVP Scope

Lane A's Linux bench plus Lane B's KVM step: AUTON builds natively on Linux and boots
KVM-accelerated on Proxmox, with the same E2E script and the same pass bars as macOS. That
alone validates half the hypothesis and makes every subsequent phase cheaper.

### User Flow

```
# On the Proxmox box, over SSH:
$ ./scripts/e2e.sh --accel kvm
  [0/7] preflight ..... gcc/grub/xorriso/qemu ok, /dev/kvm present
  ...
  [5/7] boot+markers .. 12/12 PASS   (boot-to-prompt: 0.9s   [Mac/TCG: 14.2s])
  GREEN

# Later, on metal:
$ dd if=build/auton-neural.iso of=/dev/diskN     # USB stick
  (boot the test machine from USB, serial console attached)
  AUTON Kernel booting
  [DEV] PCI scan: 9 devices found
  auton> what is my ip
  My IP is 192.168.1.47 (gateway 192.168.1.1, dns 192.168.1.1)
```

---

## Technical Approach

**Feasibility**: **HIGH** for Lane A (Linux) and Lane B's KVM step. **MEDIUM** for Lane C and
WSL2. **LOW** for real metal and Lane D — both are real engineering, not configuration.

**Architecture Notes**
- **Linux is the best bench, by a wide margin.** `apt install build-essential grub-pc-bin
  xorriso qemu-system-x86 qemu-utils` covers the entire toolchain; the Makefile's `CC`
  override already accommodates `x86_64-linux-gnu-gcc`; and `/dev/kvm` makes x86 boots
  native-speed rather than emulated. It also unlocks Lane C for free.
- **Windows has no native GRUB.** WSL2 gives a real Linux userspace; `/dev/kvm` is
  unavailable but WHPX/Hyper-V acceleration for QEMU is. Treat WSL2 as "a Linux host with a
  slower accelerator," not as a separate port.
- **KVM changes nothing about the kernel.** Proxmox exposes the same virtual devices QEMU
  does — including the e1000 the driver already targets. This is why it comes before metal:
  maximum speed gain, near-zero driver work.
- **Real metal breaks four assumptions at once**: UEFI instead of BIOS (`grub.cfg` is
  i386-pc), a NIC that isn't `8086:100e`, a storage controller where none is supported, and
  no `-serial stdio` (needs USB-TTL, IPMI SoL, or a framebuffer console). Sequence them:
  boot-only first (no net, no storage), then NIC, then the rest.
- **`[MM]` and `[SCHED]` are decorative.** Real hardware with a real memory map will expose
  this immediately — a bitmap PMM behind `[MM]` is a prerequisite for Lane B's metal step,
  not an optional cleanup. This is shared work with the service-kernel factory PRD.
- **The HAL is specified but absent.** `kernel_spec/arch/hal.md` defines `arch_boot_init()`,
  `arch_interrupt_init()`, `arch_serial_early_init()`, `arch_map_page()`, etc. Portable code
  currently calls x86 functions directly. Lane D is: implement the contract, refactor
  x86_64 behind it, add a grep gate, *then* port.
- **aarch64 would run natively on this Mac.** `qemu-system-aarch64 -M virt -cpu cortex-a53`
  on Apple Silicon needs no CPU emulation at all — potentially the fastest bench in the
  entire project, and an argument for aarch64 over riscv64 in Lane D.

**Technical Risks**

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| No physical test machine identified → Lane B stalls | **H** | Lane B's KVM step delivers most of the value and needs no metal. Metal step stays blocked-but-scoped until a machine is named |
| Test machine is UEFI-only | **H** | Plan the `x86_64-efi` GRUB target as part of Lane B rather than discovering it at the USB stick |
| No serial port on modern hardware | **H** | Require USB-TTL adapter or IPMI SoL in the machine-selection criteria; a framebuffer console is a much larger project |
| NIC isn't e1000 | **H** | Stage it: boot-only acceptance first. Then one driver for that machine's actual chip (likely Realtek 8168 or Intel I219) |
| Proxmox unreachable / no API access | **M** | Lanes A and D are unaffected; C and B-KVM block. Establish access in Phase 0 |
| HAL refactor destabilizes the working x86 kernel | **M** | Refactor behind the full E2E suite from PRD #1; no behavior change permitted in the same commit |
| Neural SSE path is unportable to Lane D's arch | **M** | Accept it: the second arch ships with the rule engine, neural stays x86-only until `kmath.c` gets an arch-conditional backend |
| WSL2 filesystem performance / networking quirks | **L** | Keep the repo on the WSL2 ext4 side, not `/mnt/c` |

---

## Implementation Phases

<!--
  STATUS: pending | in-progress | complete
  PARALLEL: phases that can run concurrently
  DEPENDS: phases that must complete first
  PRP: link to generated plan file once created
-->

| # | Phase | Description | Status | Parallel | Depends | PRP Plan |
|---|-------|-------------|--------|----------|---------|----------|
| 0 | Access + target selection | Proxmox reachability; name the physical test machine; record its firmware/NIC/storage/serial | planned | - | - | [`w15-portability-proxmox`](../../plans/completed/w15-portability-proxmox.plan.md) |
| A1 | Linux dev bench — **wired, unrun**: the `linux-e2e` CI job exists with expected markers; it has never run because the branch is unpushed | Native apt toolchain, per-host preflight, E2E green on Linux | planned | with C1 | PRD#1 ph.2 | [`w12-portability-linux-bench`](../../plans/completed/w12-portability-linux-bench.plan.md) |
| A2 | Host-agnostic entry point — **complete**, [report](../../reports/w11-portability-host-agnostic-entry-report.md); `docs/HOST-MATRIX.md` | One `e2e.sh` with host detection + `--accel` selection; three-host matrix documented | complete | - | A1 | `completed/w11-portability-host-agnostic-entry` |
| A3 | WSL2 Windows bench | WSL2 setup path, WHPX acceleration, E2E green; native-Windows explicitly ruled out in docs | planned | with B1 | A2 | [`w15-portability-wsl2`](../../plans/completed/w15-portability-wsl2.plan.md) |
| B1 | KVM boot on Proxmox | Same ISO, `/dev/kvm`, timed against TCG; the 10x metric | planned | with A3 | 0, A1 | [`w12-portability-linux-bench`](../../plans/completed/w12-portability-linux-bench.plan.md), [`w15-portability-proxmox`](../../plans/completed/w15-portability-proxmox.plan.md) |
| B2 | Real PMM — generation run **in flight** on a qualified model; gemma4 produced 0 allocator lines | Bitmap physical allocator behind the `[MM]` marker; real memory map from boot_info | generation run: 0 allocator lines on gemma4 (1 non-compiling header); [report](../../reports/w13-generate-mm-report.md). Awaits a capable model (owner) or the labelled human fallback | with C2 | A1 | [`w13-generate-mm`](../../plans/completed/w13-generate-mm.plan.md) |
| B3 | UEFI boot path | `x86_64-efi` GRUB target + `grub-efi.cfg`; boots in QEMU/OVMF | planned | - | A1 | [`w12-portability-uefi`](../../plans/completed/w12-portability-uefi.plan.md) |
| B4 | Metal boot-only | USB media, serial capture, boots to `auton>` on the physical machine. No net, no storage | planned | - | 0, B2, B3 | [`w16-portability-metal`](../../plans/completed/w16-portability-metal.plan.md) |
| B5 | Metal networking | One real NIC driver for that machine; real DHCP lease from the LAN | planned | - | B4 | [`w16-portability-metal`](../../plans/completed/w16-portability-metal.plan.md) |
| C1 | Control-plane on Linux+Windows — **Linux green** (178 passed in a container), three host bugs fixed, 3-OS CI matrix wired and unrun | controlplane test suite + all three surfaces green on both hosts | Linux green (178 passed, container), 3 host bugs fixed; CI matrix + per-surface smoke wired for macOS/Linux/Windows, unrun until push; [report](../../reports/w13-portability-controlplane-hosts-report.md) | with A1 | - | [`w13-portability-controlplane-hosts`](../../plans/completed/w13-portability-controlplane-hosts.plan.md) |
| C2 | KVM OS profiles made real | windows-dockur / android / macos-dockur actually booted on Proxmox; profiles.py corrected to observed truth | planned | with B2 | 0, C1 | [`w15-portability-proxmox`](../../plans/completed/w15-portability-proxmox.plan.md) |
| D1 | HAL extraction — **complete**, [report](../../reports/w12-portability-hal-extraction-report.md); `[gate: hal]` refuses direct arch calls in portable code | Implement `hal.md`; refactor x86_64 behind it; grep gate forbidding direct arch calls in portable code | planned | - | A1, PRD#1 ph.2 | [`w12-portability-hal-extraction`](../../plans/completed/w12-portability-hal-extraction.plan.md) |
| D2 | Second architecture — **scaffold, DTB parser (21 checks, 9/9) and a boot smoke test done**; the smoke test found HVF refuses GICv2, which changed the spec. The arch layer needs a generation run | aarch64 (recommended) port to `auton>` in QEMU, rule-engine backend, arch acceptance markers | planned | - | D1 | [`w14-portability-aarch64`](../../plans/completed/w14-portability-aarch64.plan.md) |

### Phase Details

**Phase 0: Access + target selection**
- **Goal**: Remove the two unknowns that block half this PRD.
- **Scope**: Establish and document Proxmox access (SSH/API token, network path). Choose the
  physical test machine and record firmware mode (UEFI/BIOS/CSM), NIC PCI id, storage
  controller, and serial access method. Write it into the PRD as fact.
- **Success signal**: A named machine with a recorded hardware profile, and a Proxmox command
  that runs from this Mac.
- **Note**: Cheap, and everything in Lanes B and C is guesswork until it's done. Do it first.

**Phase A1: Linux dev bench**
- **Goal**: AUTON builds and boots on Linux with the same script and pass bars as macOS.
- **Scope**: apt toolchain list; extend PRD #1's preflight with per-host toolchain checks and
  the free-disk floor; run the full E2E; record timings for comparison.
- **Success signal**: `scripts/e2e.sh` green on Linux, artifacts identical in shape to macOS.

**Phase A2: Host-agnostic entry point**
- **Goal**: One command, three hosts, no per-host forks.
- **Scope**: Host detection (macOS/Linux/WSL2), `--accel {tcg,kvm,whpx}`, per-host toolchain
  resolution (`grub-mkrescue` vs `i686-elf-grub-mkrescue`), a documented support matrix.
- **Success signal**: The same invocation works on all three; unsupported combinations fail
  at preflight with a specific message, never mid-run.

**Phase A3: WSL2 Windows bench**
- **Goal**: A Windows developer can run the bench, honestly.
- **Scope**: WSL2 install path, repo placement on ext4, WHPX/Hyper-V acceleration for QEMU,
  E2E run. Documentation states plainly that native-Windows kernel builds are unsupported
  and why (`grub-mkrescue`).
- **Success signal**: E2E green under WSL2; the docs make the WSL2 requirement unmissable.

**Phase B1: KVM boot on Proxmox**
- **Goal**: Kill the emulation tax.
- **Scope**: Ship the ISO to Proxmox, boot a VM with `-enable-kvm` and an e1000, run the
  marker suite and the scripted transcript, time boot-to-prompt against the Mac's TCG run.
- **Success signal**: ≥ 10x faster boot, 12/12 markers, transcript green. Highest
  value-per-unit-effort phase in this document.

**Phase B2: Real PMM**
- **Goal**: Put an allocator behind the `[MM]` marker before real hardware exposes its absence.
- **Scope**: Bitmap physical page allocator over the real Multiboot2 memory map (currently
  only `total_ram_bytes` is used); reserve kernel image and module regions; `kmalloc`/`kfree`;
  the marker reports real free pages. Extend the acceptance harness to assert allocation
  actually works, not just that a line printed.
- **Success signal**: The `[MM]` marker becomes a true statement, verified by a test.
- **Shared with**: the service-kernel-factory PRD, which needs the same allocator. Build once.

**Phase B3: UEFI boot path**
- **Goal**: Be bootable on hardware made after ~2015.
- **Scope**: `x86_64-efi` GRUB target, `grub/grub-efi.cfg`, a hybrid or separate ISO, OVMF
  boot in QEMU. Multiboot2 handoff differs under EFI — verify `boot_info` parsing survives.
- **Success signal**: Boots to `auton>` under QEMU+OVMF with all markers.

**Phase B4: Metal boot-only**
- **Goal**: AUTON runs on a computer.
- **Scope**: Write the ISO to USB; attach serial (USB-TTL or IPMI SoL); boot; capture output.
  Networking and storage explicitly out — success is `auton>` on real silicon, plus a real
  PCI scan of real devices.
- **Success signal**: Serial capture showing the boot markers and an interactive prompt on
  the named machine.
- **Expect**: the first attempt to fail on firmware or serial, not on kernel code. Budget for it.

**Phase B5: Metal networking**
- **Goal**: The chat OS answers a real network question on a real network.
- **Scope**: Identify the machine's actual NIC; write or port one driver; DHCP against the real
  LAN; verify the lease in the router's table. Reuse every hard-won e1000 lesson: `volatile`
  descriptor rings, `hlt`-yielding poll loops, pre-resolved gateway ARP.
- **Success signal**: `what is my ip` returns a LAN address the router agrees it issued.

**Phase C1: Control plane on Linux + Windows**
- **Goal**: The host half of the chat OS is not macOS-only.
- **Scope**: Run the controlplane suite on both; exercise terminal, UI, and desktop surfaces;
  fix path/process assumptions (`~/.auton`, the desktop app-launch backend is per-OS by design
  — verify the Windows and Linux branches actually work).
- **Success signal**: Suite green on both; all three surfaces smoke-tested per host.

**Phase C2: KVM OS profiles made real**
- **Goal**: Stop shipping three profiles nobody has ever run.
- **Scope**: On Proxmox, actually boot windows-dockur, android (budtmo), macos-dockur from the
  existing compose files. Record what really happens — EULA gates, x86-on-ARM, boot times —
  and correct `profiles.py` to observed truth, including downgrading anything that doesn't work.
- **Success signal**: ≥ 2 of 3 boot and run a real app; `profiles.py` matches reality; any
  failure is encoded as an honest status rather than removed.

**Phase D1: HAL extraction**
- **Goal**: Make the portable kernel actually portable.
- **Scope**: Implement the `hal.md` contract as headers; refactor x86_64 behind it; add a
  build-time grep gate rejecting direct arch symbol use from portable code. **No behavior
  change** — the full E2E suite must stay green across the refactor.
- **Success signal**: Zero direct arch calls in portable code; E2E unchanged, green.

**Phase D2: Second architecture**
- **Goal**: Prove the HAL by using it.
- **Scope**: aarch64 recommended — QEMU runs it natively on this Apple Silicon host, making
  it potentially the fastest bench in the project. Boot path (DTB), PL011 UART, GICv2, ARM
  timer, per `arch/aarch64.md`. Rule-engine SLM only; the SSE neural path stays x86-only and
  that limitation is documented, not hidden.
- **Success signal**: `auton>` in `qemu-system-aarch64 -M virt`, arch-specific markers passing.

### Parallelism Notes

- **A1 ∥ C1** — kernel toolchain vs host Python; disjoint.
- **A3 ∥ B1** — WSL2 setup needs no Proxmox; KVM needs no Windows.
- **B2 ∥ C2** — kernel allocator vs container profiles; entirely unrelated.
- **B3 ∥ B2** — GRUB/EFI packaging vs in-kernel allocator; coordinate only on the boot path.
- **Strictly serial**: 0 → B1 → (B2, B3) → B4 → B5, and D1 → D2. Metal is the end of a chain,
  not a starting point; the HAL must exist before a second arch, or the port forks the kernel.
- **Cross-PRD**: A1 depends on PRD #1 Phase 2 (the E2E spine) — there is nothing to port until
  the spine exists. B2 (real PMM) is shared with the service-kernel-factory PRD.

---

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| Scope | All four lanes | Dev-host portability only | User selected all four. Sequenced so each stands alone if others stall |
| Windows strategy | WSL2 only | Native MSYS2/mingw build | `grub-mkrescue` has no supported native-Windows path; pretending otherwise burns a week for nothing |
| Hardware sequencing | KVM on Proxmox before metal | Straight to metal | KVM gives the 10x speedup with near-zero driver work; metal is a long chain of firmware and driver problems |
| Metal scope | Boot-only, then one NIC | Full hardware support | Driver breadth is unbounded. One named machine, staged |
| Second architecture | aarch64 (recommended, not final) | riscv64 | Runs natively on this arm64 host — likely the fastest bench in the project |
| PMM ownership | Lane B2, shared with the factory PRD | Duplicate in each | Both need it; a second allocator would be a genuine mistake |
| Profile honesty | Correct `profiles.py` to observed truth, downgrade failures | Quietly drop broken profiles | The backend's entire design premise is that it never pretends |

---

## Research Summary

**Market Context**
Not researched — no competitive set for a research chat-OS. Relevant convention: hobby and
research kernels universally stage hardware bring-up as emulator → accelerated VM → one known
machine, and treat UEFI + serial access as the two gates that decide whether metal is even
attemptable. Both conventions adopted.

**Technical Context (verified in-repo, 2026-09-10)**
- `kernels/` = `x86_64` only. `arch_registry.py` has full `aarch64`/`riscv64` profiles;
  `kernel_spec/arch/{aarch64,riscv64,hal}.md` exist; no corresponding source.
- No `kernel/mm/`, `kernel/fs/`, or `kernel/sched/`. `[MM]`/`[SCHED]` markers are decorative
  by the authors' own comments in `kernel/boot/kernel_main.c`.
- Drivers: `serial_16550.c`, `pci.c`, `e1000.c` (id `8086:100e`), `idt.c`+`isr.S` (PIC+PIT).
  No storage, no USB, no framebuffer.
- `grub/grub.cfg` and `grub-neural.cfg` target BIOS/i386-pc via `grub-mkrescue`. No EFI config.
- `toolchain.mk` documents the `CC=x86_64-linux-gnu-gcc` override — the Linux path is already
  anticipated in the build.
- `controlplane/backends/os/profiles.py`: 5 profiles, statuses REAL / EXPERIMENTAL /
  NEEDS_KVM ×3 / EXTERNAL; ready compose files for android, macos-dockur, windows-dockur; a
  Wine Dockerfile for local Windows-style; `ios-guidance/GUIDANCE.md` for the impossible case.
- Known networking lessons that must carry to any new NIC driver: descriptor rings must be
  `volatile`; poll loops must `hlt`-yield or SLIRP/TCG starves; `net_bringup` must pre-resolve
  the gateway ARP or inbound SYNs are dropped.

---

*Generated: 2026-09-10*
*Status: DRAFT - needs validation (Phase 0 answers two blocking unknowns)*
