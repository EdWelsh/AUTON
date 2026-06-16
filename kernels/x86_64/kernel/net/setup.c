/* Network bring-up: locate the NIC, start the driver, run DHCP. Called once
 * from kernel_main after the PCI scan. */
#include "net.h"
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

	if (dhcp_run() == 0) {
		kprintf("[NET] IP ");
		print_ip(net_ip());
		kprintf("\n");
		/* Pre-resolve the gateway so outbound replies (e.g. a TCP
		 * SYN-ACK) are never dropped waiting on ARP. ip_send drops on an
		 * ARP miss, and SLIRP may send us a SYN without ARPing first. */
		uint8_t gwmac[6];
		for (int i = 0; i < 300 && !arp_resolve(net_gw(), gwmac); i++) {
			__asm__ volatile("hlt");
			net_poll();
		}
	} else {
		kprintf("[NET] DHCP: no lease (link up, no address)\n");
	}
	return 0;
}
