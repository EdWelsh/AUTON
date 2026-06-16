/* System-information queries (see sysinfo.h). */
#include "sysinfo.h"
#include "kstr.h"
#include "net.h"
#include "irq.h"
#include "slm.h"
#include "kernel.h"

#define MAX_DEVS 32

static uint32_t g_ram_mb;
static uint16_t g_vendor[MAX_DEVS];
static uint16_t g_device[MAX_DEVS];
static uint32_t g_ndev;
static char     g_hostname[64] = "auton";

void sysinfo_init(uint32_t ram_mb, const pci_device_t *devs, uint32_t ndev)
{
	g_ram_mb = ram_mb;
	g_ndev = ndev > MAX_DEVS ? MAX_DEVS : ndev;
	for (uint32_t i = 0; i < g_ndev; i++) {
		g_vendor[i] = devs[i].vendor_id;
		g_device[i] = devs[i].device_id;
	}
}

const char *sysinfo_hostname(void)
{
	return g_hostname;
}

/* Case-insensitive find: index of 'needle' in 'hay', or -1. */
static int ci_find(const char *hay, const char *needle)
{
	for (int i = 0; hay[i]; i++) {
		int j = 0;
		while (needle[j] && ks_lower(hay[i + j]) == ks_lower(needle[j]))
			j++;
		if (!needle[j])
			return i;
	}
	return -1;
}

static int is_word_char(char c)
{
	c = ks_lower(c);
	return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') ||
	       c == '-' || c == '.';
}

static int is_stopword(const char *w)
{
	return kstrcmp(w, "to") == 0 || kstrcmp(w, "is") == 0 ||
	       kstrcmp(w, "the") == 0 || kstrcmp(w, "a") == 0 ||
	       kstrcmp(w, "my") == 0 || kstrcmp(w, "of") == 0 ||
	       kstrcmp(w, "this") == 0 || kstrcmp(w, "machine") == 0;
}

/* Extract the hostname word that follows "hostname". Returns 1 if found. */
static int extract_hostname(const char *t, char *out, uint32_t cap)
{
	int p = ci_find(t, "hostname");
	if (p < 0)
		return 0;
	p += 8;                         /* past "hostname" */

	for (;;) {
		while (t[p] == ' ')
			p++;
		if (!is_word_char(t[p]))
			return 0;       /* nothing meaningful follows */
		char word[64];
		uint32_t n = 0;
		while (is_word_char(t[p]) && n < sizeof(word) - 1)
			word[n++] = t[p++];
		word[n] = '\0';
		if (is_stopword(word))
			continue;       /* skip "to"/"is"/... and keep scanning */
		uint32_t i = 0;
		for (; word[i] && i < cap - 1; i++)
			out[i] = word[i];
		out[i] = '\0';
		return i > 0;
	}
}

static void list_devices(char *buf, uint32_t cap)
{
	const char *hex = "0123456789abcdef";
	uint32_t p = 0;

	p = ks_append(buf, cap, p, "Devices: ");
	p = ks_append_dec(buf, cap, p, g_ndev);
	p = ks_append(buf, cap, p, " on PCI bus 0.");
	for (uint32_t i = 0; i < g_ndev; i++) {
		p = ks_append(buf, cap, p, " ");
		for (int s = 12; s >= 0; s -= 4)
			if (p < cap - 1)
				buf[p++] = hex[(g_vendor[i] >> s) & 0xF];
		buf[p] = '\0';
		p = ks_append(buf, cap, p, ":");
		for (int s = 12; s >= 0; s -= 4)
			if (p < cap - 1)
				buf[p++] = hex[(g_device[i] >> s) & 0xF];
		buf[p] = '\0';
		const char *drv = slm_driver_for_pci(g_vendor[i], g_device[i]);
		if (drv) {
			p = ks_append(buf, cap, p, "(");
			p = ks_append(buf, cap, p, drv);
			p = ks_append(buf, cap, p, ")");
		}
	}
}

int sysinfo_answer(const char *t, char *buf, uint32_t cap)
{
	uint32_t p = 0;

	/* Hostname (set or get). */
	if (ks_contains(t, "hostname")) {
		char name[64];
		if ((ks_contains(t, "set") || ks_contains(t, "change") ||
		     ks_contains(t, "call") || ks_contains(t, " to ") ||
		     ks_contains(t, "=")) && extract_hostname(t, name, sizeof(name))) {
			uint32_t i = 0;
			for (; name[i] && i < sizeof(g_hostname) - 1; i++)
				g_hostname[i] = name[i];
			g_hostname[i] = '\0';
			p = ks_append(buf, cap, p, "Hostname set to ");
			p = ks_append(buf, cap, p, g_hostname);
			ks_append(buf, cap, p, ".");
		} else {
			p = ks_append(buf, cap, p, "Hostname is ");
			p = ks_append(buf, cap, p, g_hostname);
			ks_append(buf, cap, p, ".");
		}
		return 1;
	}

	/* IP address. */
	if (ks_contains(t, "my ip") || ks_contains(t, "ip address") ||
	    (ks_contains(t, "ip") &&
	     (ks_contains(t, "what") || ks_contains(t, "address")))) {
		if (!net_is_up()) {
			ks_append(buf, cap, 0,
				  "No IP yet: the NIC is up but DHCP has not "
				  "completed.");
			return 1;
		}
		p = ks_append(buf, cap, p, "My IP is ");
		p = ks_append_ip(buf, cap, p, net_ip());
		p = ks_append(buf, cap, p, " (gateway ");
		p = ks_append_ip(buf, cap, p, net_gw());
		p = ks_append(buf, cap, p, ", dns ");
		p = ks_append_ip(buf, cap, p, net_dns());
		ks_append(buf, cap, p, ").");
		return 1;
	}

	/* Memory. */
	if (ks_contains(t, "memory") || ks_contains(t, "ram") ||
	    ks_contains(t, "how much mem")) {
		p = ks_append(buf, cap, p, "Memory: ");
		p = ks_append_dec(buf, cap, p, g_ram_mb);
		ks_append(buf, cap, p, " MB RAM.");
		return 1;
	}

	/* Uptime. */
	if (ks_contains(t, "uptime") ||
	    (ks_contains(t, "how long") && ks_contains(t, "up"))) {
		uint64_t sec = timer_ticks() / 1000;
		p = ks_append(buf, cap, p, "Uptime: ");
		p = ks_append_dec(buf, cap, p, (uint32_t)sec);
		ks_append(buf, cap, p, " seconds.");
		return 1;
	}

	/* Devices (but not the "what is pci VVVV:DDDD" identify query). */
	if ((ks_contains(t, "device") || ks_contains(t, "hardware") ||
	     ks_contains(t, "what do you see") || ks_contains(t, "nic")) &&
	    !ks_contains(t, ":")) {
		list_devices(buf, cap);
		return 1;
	}

	/* Status summary. */
	if (ks_contains(t, "status") || ks_contains(t, "how are you") ||
	    ks_contains(t, "summary")) {
		p = ks_append(buf, cap, p, "AUTON ");
		p = ks_append(buf, cap, p, g_hostname);
		p = ks_append(buf, cap, p, ": ");
		if (net_is_up()) {
			p = ks_append(buf, cap, p, "IP ");
			p = ks_append_ip(buf, cap, p, net_ip());
		} else {
			p = ks_append(buf, cap, p, "no IP");
		}
		p = ks_append(buf, cap, p, ", ");
		p = ks_append_dec(buf, cap, p, g_ram_mb);
		p = ks_append(buf, cap, p, " MB RAM, ");
		p = ks_append_dec(buf, cap, p, g_ndev);
		p = ks_append(buf, cap, p, " devices, up ");
		p = ks_append_dec(buf, cap, p, (uint32_t)(timer_ticks() / 1000));
		ks_append(buf, cap, p, "s.");
		return 1;
	}

	return 0;
}
