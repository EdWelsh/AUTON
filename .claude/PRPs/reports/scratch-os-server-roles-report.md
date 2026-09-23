# Implementation Report: Chat-driven server roles

## Summary
Executed `scratch-os-server-roles.plan.md` via `/prp-implement`. The plan's
substantive subsystems (Phases G/H/I) were already built and verified in prior
sessions: a polled in-kernel IPv4 stack (e1000, ARP, IPv4/ICMP, UDP, DHCP) with
`what is my IP`; a minimal TCP stack + in-kernel HTTP server reached by
`be a web server`; and a capability/role registry plus system queries. This run
closed the **last open acceptance criterion** — codifying `net_dhcp_ip` and
`http_get` as automated acceptance tests — and documented the chat-driven
workflow (Phase F).

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | XL | XL overall (G/H/I prior); this run = S (Phase F only) |
| Files changed | ~28 created | 2 modified this run (rest landed earlier) |
| MVP boundary | Phase H (web role end-to-end) | Met earlier; all criteria now green |

## Tasks Completed

| Phase | Task | Status | Notes |
|---|---|---|---|
| G | NIC + L2/L3/UDP → DHCP IP | ✅ (prior) | `[NET] IP`, chat reports it |
| H | TCP + HTTP → `be a web server` | ✅ (prior) | real HTTP 200 via hostfwd |
| I | Capability registry + sysinfo + DNS | ✅ (prior) | ready/roadmap status |
| F.1 | `net_dhcp_ip` + `http_get` acceptance | ✅ (this run) | automated in run-acceptance.sh |
| F.2 | README chat-roles docs | ✅ (this run) | "The OS is the chat" section |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static / build | ✅ Pass | kernel builds (gcc) in the acceptance image |
| Integration (QEMU) | ✅ Pass | `docker compose run acceptance` => **ALL PASS** |
| `net_dhcp_ip` | ✅ Pass | `[NET] IP 10.0.2.15` from a real DHCP exchange |
| `http_get` | ✅ Pass | in-kernel web server returns the AUTON page over TCP |
| Edge cases | ✅ Pass | `SKIP_NET=1` opt-out; first-byte-drop absorbed by a leading newline |

## Files Changed (this run)

| File | Action | Notes |
|---|---|---|
| `scripts/run-acceptance.sh` | UPDATED | +networking section (DHCP + HTTP via /dev/tcp) |
| `README.md` | UPDATED | chat-driven roles + on-device-model quickstart |

## Deviations from Plan
- **`http_get` uses bash `/dev/tcp`, not `curl`.** The `base` acceptance image
  has no curl; `/dev/tcp` needs only bash (already present) and exercises the
  same path. Functionally equivalent.
- **No new `os-neural` compose service here.** That belonged to the on-device-SLM
  plan and was delivered there as `make run-neural` / `iso-neural`.

## Issues Encountered
- **QEMU `-serial stdio` drops the first stdin byte.** The acceptance driver
  prefixes a blank line so `be a web server` arrives intact; the role detector
  is also robust to a dropped leading character.

## Tests Written

| Test | Coverage |
|---|---|
| `net_dhcp_ip` (run-acceptance.sh) | DHCP lease over the in-kernel IPv4 stack |
| `http_get` (run-acceptance.sh) | TCP + in-kernel HTTP 200 end-to-end |

## Next Steps
- [ ] Make a roadmap role real (file server from an in-RAM docroot reuses HTTP)
- [ ] `/code-review` the diff
