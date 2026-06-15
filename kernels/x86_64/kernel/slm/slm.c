/* Seed SLM runtime — rule-engine backend.
 * A tiny embedded knowledge base maps known PCI IDs to drivers, mirroring the
 * DRIVER_SELECT behavior in kernel_spec/subsystems/slm.md. */
#include "slm.h"
#include "kernel.h"

struct pci_driver_rule {
	uint16_t vendor;
	uint16_t device;
	const char *driver;
};

/* Seed knowledge base (extended later via knowledge/ data files). */
static const struct pci_driver_rule kb_rules[] = {
	{ 0x8086, 0x100E, "e1000" },   /* Intel 82540EM Gigabit Ethernet (QEMU) */
	{ 0x8086, 0x10D3, "e1000e" },  /* Intel 82574L */
	{ 0x1AF4, 0x1000, "virtio-net" },
	{ 0x1AF4, 0x1001, "virtio-blk" },
};

static int g_initialized;

int slm_init(const hw_summary_t *hw)
{
	(void)hw;
	g_initialized = 1;
	kprintf("[SLM] Rule engine initialized\n");
	return 0;
}

const char *slm_backend_name(void)
{
	return "rule-engine";
}

const char *slm_driver_for_pci(uint16_t vendor, uint16_t device)
{
	if (!g_initialized)
		return 0;
	for (unsigned i = 0; i < sizeof(kb_rules) / sizeof(kb_rules[0]); i++) {
		if (kb_rules[i].vendor == vendor && kb_rules[i].device == device)
			return kb_rules[i].driver;
	}
	return 0;
}
