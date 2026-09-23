# Plan: Chat-driven server roles — the OS provisions itself

## Summary
Extends the chat-OS plan (`scratch-os-ondevice-chat-slm.plan.md`) toward AUTON's product
promise: **you never touch a terminal.** You ask the chat for the machine's IP, or tell it
"be a web server," and the OS configures the hardware it runs on to fulfil that role. This
plan builds the real subsystems **bottom-up so one role works end-to-end first** (an HTTP
server reachable from the host), then generalizes the chat into a **capability/role control
plane** that hosts every server role (web, file, email, DNS, DHCP, database, SSH) and every
system query (IP, hostname, memory, devices) behind the same `auton>` prompt — implemented
where the subsystem exists, honestly reported as roadmap where it does not.

## User Story
As an operator running AUTON on a machine,
I want to type "be a web server" or "what is my IP" into the chat and have the OS do it,
So that turning a box into infrastructure needs no shell, no config files, no manual setup.

## Problem → Solution
**Current state (after Stage 1 Phase A):** boots to an `auton>` rule-engine REPL. No
network stack, no sockets, no filesystem, no daemons; the e1000 is only *named* by the KB.
The OS cannot actually *do* anything to the machine.
**Desired state:** the e1000 NIC really transmits/receives; the kernel obtains an IP via
DHCP; `what is my IP` returns it; `be a web server` starts an in-kernel HTTP daemon that
answers `curl http://host:8080`. A capability registry routes all role/query requests and
reports truthful per-prerequisite status for roles not yet built.

## Metadata
- **Complexity**: XL (freestanding NIC driver + TCP/IP stack + in-kernel servers + chat control plane)
- **Depends on**: Stage 1 Phase A (chat REPL) — done. Foundation Phases 0–4.
- **MVP boundary**: **Phase H delivers one real role end-to-end (web server + "what is my IP").**
  Phase I generalizes to all roles with honest status.
- **Verification env**: QEMU user-mode networking (SLIRP): `-netdev user,id=n0 -device e1000,netdev=n0`.
  SLIRP runs a DHCP server (guest gets 10.0.2.15, gw 10.0.2.2) and supports `hostfwd` for inbound TCP.

---

## Decisions (locked)
- **Approach: bottom-up, web role end-to-end first** (user choice). Build NIC→IP→TCP→HTTP so
  traffic really flows, then wire the chat verb — not a plan-only framework.
- **Roles in scope (eventual):** system queries; web + file; email + DNS + DHCP; database +
  SSH. First real role = **web**; first real query = **what is my IP** (DHCP).
- **No terminal, ever.** Every capability is reached through `slm_process_text` / the chat REPL.

## Hard contracts / gotchas
```
GOTCHA: boot.S identity-maps only low 1 GiB. e1000 MMIO BAR (~0xFEBCxxxx, <4 GiB) is unmapped
  → must extend identity map to 4 GiB (4 PDPT entries / 4 PDs of 512×2 MiB) BEFORE MMIO.
GOTCHA: PCI command register bit 2 (bus master) + bit 1 (memory space) must be set or e1000
  DMA descriptor rings never advance.
GOTCHA: e1000 descriptor rings + buffers must live in identity-mapped low RAM (phys==virt) so
  the card's DMA addresses match kernel pointers. Allocate from a simple low-RAM bump arena.
GOTCHA: all of IP/UDP/TCP need the one's-complement checksum; TCP/UDP include a pseudo-header.
GOTCHA: SLIRP does NOT reliably forward inbound ICMP echo to the guest — verify the stack with
  DHCP (UDP) and TCP (hostfwd+curl), not host->guest ping.
GOTCHA: network RX is polled in the chat idle path (no IRQs in the seed) — poll the e1000 RX
  ring between/within REPL reads so DHCP/TCP make progress.
```

---

## Phases

### Phase G — NIC + L2/L3/UDP, milestone: a real DHCP-assigned IP
| File | Action | Justification |
|---|---|---|
| `kernel/arch/x86_64/boot/boot.S` | UPDATE | identity-map 4 GiB so the e1000 MMIO BAR is addressable |
| `kernel/dev/pci.c` + `include/pci.h` | UPDATE | add config write, BAR0 read, enable bus-master+memory; return bus/slot for found dev |
| `kernel/lib/phys.c` + `include/phys.h` | CREATE | low-RAM bump allocator (page-aligned, phys==virt) for DMA rings/buffers |
| `kernel/net/e1000.c` + `include/e1000.h` | CREATE | reset, MAC read (RAL/RAH/EEPROM), RX/TX rings, `e1000_tx(frame,len)`, `e1000_poll(buf)` |
| `kernel/net/netif.c` + `include/net.h` | CREATE | ethernet framing, htons/ntohs, inet checksum, MAC/IP state, `net_poll()` |
| `kernel/net/arp.c` | CREATE | ARP cache + request/reply (resolve gateway, answer who-has) |
| `kernel/net/ipv4.c` | CREATE | IPv4 build/parse + checksum; dispatch to udp/icmp/tcp; ICMP echo reply |
| `kernel/net/udp.c` | CREATE | UDP build/parse + pseudo-header checksum; port demux |
| `kernel/net/dhcp.c` | CREATE | DHCP client DISCOVER/REQUEST → store ip/mask/gw/dns; print `[NET] IP a.b.c.d` |
| `kernel/boot/kernel_main.c` | UPDATE | `net_init()` after PCI; run DHCP; expose IP to SLM |

**Verify:** boot with `-netdev user,id=n0 -device e1000,netdev=n0`; serial shows
`[NET] e1000 up MAC ...` then `[NET] IP 10.0.2.15`. `auton> what is my ip` → `10.0.2.15`.

### Phase H — TCP + HTTP, milestone: `curl` reaches the OS (the web role, real)
| File | Action | Justification |
|---|---|---|
| `kernel/net/tcp.c` + `include/tcp.h` | CREATE | minimal TCP: LISTEN/SYN_RCVD/ESTABLISHED/CLOSE, single conn, ACK + basic retransmit, MSS |
| `kernel/net/socket.c` | CREATE | tiny API: `tcp_listen(port)`, `tcp_accept/poll`, `tcp_recv`, `tcp_send`, `tcp_close` |
| `kernel/server/http.c` + `include/server.h` | CREATE | parse request line, respond 200 with an AUTON/hardware page |
| `kernel/slm/roles.c` | CREATE | capability registry; `be a web server` → start HTTP daemon on :80 |
| `kernel/slm/chat.c` | UPDATE | poll `net_poll()` while idle so connections progress during the REPL |

**Verify:** boot with `-netdev user,hostfwd=tcp::8080-:80,id=n0 -device e1000,netdev=n0`;
`auton> be a web server` → `[HTTP] listening on :80`; host `curl http://localhost:8080`
returns the page.

### Phase I — Capability/role control plane + remaining roles (the generalization)
| File | Action | Justification |
|---|---|---|
| `kernel/slm/roles.c` | UPDATE | full registry: each role = {name, triggers, prereqs[], handler, status} |
| `kernel/slm/sysinfo.c` | CREATE | system queries: ip, hostname (get/set), memory, devices, uptime, status |
| `kernel/server/dns.c`, `smtp.c`, ... | CREATE | implement cheap roles (DNS responder, SMTP greeter, TCP file/echo); honest "roadmap" status for the rest (database, SSH, full email/IMAP) |
| `kernel/slm/slm.c` | UPDATE | `slm_process_text` routes role/query intents through the registry |
| acceptance + README | UPDATE | `net_dhcp_ip`, `http_get` acceptance tests; document chat-driven roles |

**Verify:** chat answers every selected role/query by name with truthful status; web + IP
actually function.

## NOT building
- IRQ-driven networking (polled is fine for the seed), TCP congestion control / window scaling,
  IPv6, TLS/HTTPS, multi-connection concurrency beyond a small fixed pool.
- A real filesystem — "file server" serves from an in-RAM docroot until an FS lands.
- Full SMTP/IMAP mail delivery, a real SQL engine, real SSH crypto — these report honest
  roadmap status from the registry until built.

## Acceptance criteria
- [ ] e1000 transmits and receives real frames in QEMU (MAC read from the card).
- [ ] Kernel obtains an IP via DHCP; `what is my IP` returns it over chat.
- [ ] `be a web server` starts an in-kernel HTTP daemon; host `curl` gets a 200 + body.
- [ ] Capability registry routes all selected roles/queries with truthful per-prereq status.
- [ ] No terminal/manual step anywhere — every action is a chat sentence.
- [ ] `net_dhcp_ip` + `http_get` acceptance tests pass under Docker.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| e1000 MMIO faults (paging/BAR) | High | No NIC | 4 GiB identity map + read BAR at runtime; `[NET]` probe markers |
| DMA ring addresses wrong (phys≠virt) | High | No RX/TX | low-RAM bump arena, phys==virt; assert <1 GiB |
| TCP state-machine bugs | High | curl hangs | single-conn minimal TCP; verify with curl + pcap-style serial trace |
| Polled RX starves during REPL | Med | DHCP/TCP stall | poll net in console getc wait + REPL idle |
| Scope explosion across all roles | High | Slips MVP | web + IP first; other roles are registry stubs w/ honest status |

## Notes
- This is the payoff of "the OS is the chat interface": the chat is the **only** control plane
  and it actually reconfigures the machine. Build the lower stack once; every role reuses it.
- Sequencing: G (IP) → H (web end-to-end) → I (all roles + queries, honest status).
```
