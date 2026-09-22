/* Network bring-up: locate the NIC, start the driver, run DHCP. Called once
 * from kernel_main after the PCI scan. */
#include "net.h"
#include "hal.h"
#include "e1000.h"
#include "pci.h"
#include "kernel.h"

/* Intel e1000-family controllers QEMU exposes. */
static int is_e1000(const pci_device_t *d)
{
	return d->vendor_id == 0x8086 &&
	       (d->device_id == 0x100E || d->device_id == 0x10D3);
}

static void print_mac(const uint8_t mac[6])
{
	const char *hex = "0123456789abcdef";
	char s[18];
	int p = 0;

	for (int i = 0; i < 6; i++) {
		s[p++] = hex[mac[i] >> 4];
		s[p++] = hex[mac[i] & 0xF];
		if (i < 5)
			s[p++] = ':';
	}
	s[p] = '\0';
	kprintf("%s", s);
}

static void print_ip(ipv4_t ip)
{
	kprintf("%u.%u.%u.%u", (ip >> 24) & 0xFF, (ip >> 16) & 0xFF,
		(ip >> 8) & 0xFF, ip & 0xFF);
}

int net_bringup(const struct pci_device *devs, uint32_t ndev)
{
	const pci_device_t *nic = 0;
	uint8_t mac[6];

	for (uint32_t i = 0; i < ndev; i++) {
		if (is_e1000(&devs[i])) {
			nic = &devs[i];
			break;
		}
	}
	if (!nic) {
		kprintf("[NET] no supported NIC found\n");
		return -1;
	}

	if (e1000_init(nic, mac) != 0) {
		kprintf("[NET] e1000 init failed\n");
		return -1;
	}
	kprintf("[NET] e1000 up MAC ");
	print_mac(mac);
	kprintf("\n");

	net_init(mac);

	/* A DHCP server cannot DHCP for itself. An image built with a static
	 * configuration skips the client entirely — services/dhcp.md, Task 1 of
	 * the F4 plan. NET_STATIC_IP is set by the build from the manifest. */
#ifdef NET_STATIC_IP
	net_set_ipcfg(NET_STATIC_IP, NET_STATIC_MASK, NET_STATIC_GW, NET_STATIC_DNS);
	kprintf("[NET] static IP ");
	print_ip(net_ip());
	kprintf("\n");
	/* Announce ourselves by ARPing the gateway, for the same reason the DHCP
	 * path does it: ip_send drops on an ARP miss. It matters more here.
	 * A statically-configured guest that never transmits is invisible to
	 * QEMU's user-mode NAT, which learns a guest from its outbound traffic —
	 * so a host port forward to a purely passive server is silently dropped,
	 * and the service looks broken when it is merely unheard of. */
	uint8_t gwmac[6];
	for (int i = 0; i < 300 && !arp_resolve(net_gw(), gwmac); i++) {
		arch_halt();
		net_poll();
	}
	return 0;
#else
	if (dhcp_run() == 0) {
		kprintf("[NET] IP ");
		print_ip(net_ip());
		kprintf("\n");
		/* Pre-resolve the gateway so outbound replies (e.g. a TCP
		 * SYN-ACK) are never dropped waiting on ARP. ip_send drops on an
		 * ARP miss, and SLIRP may send us a SYN without ARPing first. */
		uint8_t gwmac[6];
		for (int i = 0; i < 300 && !arp_resolve(net_gw(), gwmac); i++) {
			arch_halt();
			net_poll();
		}
	} else {
		kprintf("[NET] DHCP: no lease (link up, no address)\n");
	}
	return 0;
#endif
}
