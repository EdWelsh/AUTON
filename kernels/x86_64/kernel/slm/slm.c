/* Seed SLM runtime — rule-engine backend.
 * A tiny embedded knowledge base maps known PCI IDs to drivers and answers
 * free-form console queries, mirroring the HARDWARE_IDENTIFY/DRIVER_SELECT
 * behavior in kernel_spec/subsystems/slm.md. */
#include "slm.h"
#include "kernel.h"
#include "net.h"
#include "neural.h"

#define NEURAL_MIN_RAM_MB 128u

struct pci_driver_rule {
	uint16_t vendor;
	uint16_t device;
	const char *name;       /* human-readable device name */
	const char *driver;
};

/* Seed knowledge base (extended later via knowledge/ data files). */
static const struct pci_driver_rule kb_rules[] = {
	{ 0x8086, 0x100E, "Intel 82540EM Gigabit Ethernet (e1000)", "e1000" },
	{ 0x8086, 0x10D3, "Intel 82574L Gigabit Ethernet (e1000e)", "e1000e" },
	{ 0x1AF4, 0x1000, "Virtio network device", "virtio-net" },
	{ 0x1AF4, 0x1001, "Virtio block device", "virtio-blk" },
};

static int g_initialized;
static int g_neural_active;     /* 1 if the neural backend loaded a model */

/* Select a backend per slm.md:487-502: rule engine unless there is enough RAM
 * AND a model boot module that the neural backend can load. The neural loader
 * returns -1 until Stage 2 lands, so this falls back cleanly today. */
int slm_init(const hw_summary_t *hw)
{
	kprintf("[SLM] Rule engine initialized\n");
	g_initialized = 1;
	g_neural_active = 0;

	if (hw) {
		uint32_t ram_mb = (uint32_t)(hw->total_ram_bytes / (1024u * 1024u));
		if (ram_mb >= NEURAL_MIN_RAM_MB) {
			for (uint32_t i = 0; i < hw->module_count; i++) {
				const boot_module_t *m = &hw->modules[i];
				const void *data = (const void *)(uintptr_t)m->start;
				uint64_t size = m->end - m->start;
				if (slm_neural_load_model(data, size,
							  MODEL_FORMAT_AUTON) == 0) {
					g_neural_active = 1;
					char info[96];
					slm_neural_model_info(info, sizeof(info));
					kprintf("[SLM] Loaded model: %s\n", info);
					break;
				}
			}
		}
	}
	return 0;
}

const char *slm_backend_name(void)
{
	return g_neural_active ? "neural" : "rule-engine";
}

static const struct pci_driver_rule *kb_lookup(uint16_t vendor, uint16_t device)
{
	for (unsigned i = 0; i < sizeof(kb_rules) / sizeof(kb_rules[0]); i++) {
		if (kb_rules[i].vendor == vendor && kb_rules[i].device == device)
			return &kb_rules[i];
	}
	return 0;
}

const char *slm_driver_for_pci(uint16_t vendor, uint16_t device)
{
	const struct pci_driver_rule *r;

	if (!g_initialized)
		return 0;
	r = kb_lookup(vendor, device);
	return r ? r->driver : 0;
}

/* ---- text helpers (case-insensitive, fixed-buffer, no libc) ---- */

static char lower(char c)
{
	return (c >= 'A' && c <= 'Z') ? (char)(c + 32) : c;
}

/* True if lowercased 'hay' contains 'needle' (needle must be lowercase). */
static int contains(const char *hay, const char *needle)
{
	for (uint32_t i = 0; hay[i]; i++) {
		uint32_t j = 0;
		while (needle[j] && lower(hay[i + j]) == needle[j])
			j++;
		if (!needle[j])
			return 1;
	}
	return 0;
}

static int hex_val(char c)
{
	c = lower(c);
	if (c >= '0' && c <= '9')
		return c - '0';
	if (c >= 'a' && c <= 'f')
		return c - 'a' + 10;
	return -1;
}

/* Parse a "vvvv:dddd" PCI id out of free text. Returns 1 on success. */
static int parse_pci_id(const char *text, uint16_t *vendor, uint16_t *device)
{
	for (uint32_t i = 0; text[i]; i++) {
		if (text[i] != ':')
			continue;
		/* Walk back over up to 4 hex digits. */
		uint32_t start = i;
		while (start > 0 && hex_val(text[start - 1]) >= 0)
			start--;
		if (start == i)
			continue;       /* nothing before the colon */
		if (hex_val(text[i + 1]) < 0)
			continue;       /* nothing after the colon */

		uint32_t v = 0, d = 0;
		for (uint32_t k = start; k < i; k++)
			v = (v << 4) | (uint32_t)hex_val(text[k]);
		uint32_t k = i + 1;
		for (uint32_t n = 0; n < 4 && hex_val(text[k]) >= 0; n++, k++)
			d = (d << 4) | (uint32_t)hex_val(text[k]);
		*vendor = (uint16_t)v;
		*device = (uint16_t)d;
		return 1;
	}
	return 0;
}

/* Capacity of the response buffer (shared by all answer_* helpers). */
#define R_CAP (uint32_t)sizeof(((slm_intent_result_t *)0)->response)

/* Append 's' to dst[pos..cap), NUL-terminating. Returns new length. */
static uint32_t append(char *dst, uint32_t cap, uint32_t pos, const char *s)
{
	while (*s && pos < cap - 1)
		dst[pos++] = *s++;
	dst[pos] = '\0';
	return pos;
}

static uint32_t append_hex4(char *dst, uint32_t cap, uint32_t pos, uint16_t v)
{
	const char *hex = "0123456789abcdef";
	for (int shift = 12; shift >= 0; shift -= 4) {
		if (pos < cap - 1)
			dst[pos++] = hex[(v >> shift) & 0xF];
	}
	dst[pos] = '\0';
	return pos;
}

static uint32_t append_dec(char *dst, uint32_t cap, uint32_t pos, uint32_t v)
{
	char tmp[12];
	int n = 0;

	if (v == 0)
		tmp[n++] = '0';
	while (v > 0 && n < (int)sizeof(tmp)) {
		tmp[n++] = (char)('0' + v % 10);
		v /= 10;
	}
	while (n > 0 && pos < cap - 1)
		dst[pos++] = tmp[--n];
	dst[pos] = '\0';
	return pos;
}

static uint32_t append_ip(char *dst, uint32_t cap, uint32_t pos, uint32_t ip)
{
	pos = append_dec(dst, cap, pos, (ip >> 24) & 0xFF);
	pos = append(dst, cap, pos, ".");
	pos = append_dec(dst, cap, pos, (ip >> 16) & 0xFF);
	pos = append(dst, cap, pos, ".");
	pos = append_dec(dst, cap, pos, (ip >> 8) & 0xFF);
	pos = append(dst, cap, pos, ".");
	pos = append_dec(dst, cap, pos, ip & 0xFF);
	return pos;
}

/* True if the query is asking for this machine's IP address. */
static int is_ip_query(const char *t)
{
	return contains(t, "my ip") || contains(t, "ip address") ||
	       (contains(t, "ip") &&
		(contains(t, "what") || contains(t, "address")));
}

int slm_is_web_server_request(const char *t)
{
	if (!(contains(t, "web server") || contains(t, "http server") ||
	      (contains(t, "web") && contains(t, "server"))))
		return 0;
	/* Mentioning a web server means "make this one" — unless it's a question
	 * about web servers. (Robust to a dropped leading char like "e a web
	 * server" from the serial console.) */
	if (contains(t, "what") || contains(t, "how") ||
	    contains(t, "why") || contains(t, "explain"))
		return 0;
	return 1;
}

static void answer_ip(slm_intent_result_t *r)
{
	uint32_t p = 0;

	if (!net_is_up()) {
		append(r->response, R_CAP, 0,
		       "No IP yet: the NIC is up but DHCP did not complete. "
		       "Networking is being brought up at boot.");
		return;
	}
	p = append(r->response, R_CAP, p, "My IP is ");
	p = append_ip(r->response, R_CAP, p, net_ip());
	p = append(r->response, R_CAP, p, " (gateway ");
	p = append_ip(r->response, R_CAP, p, net_gw());
	p = append(r->response, R_CAP, p, ", dns ");
	p = append_ip(r->response, R_CAP, p, net_dns());
	append(r->response, R_CAP, p, ").");
}

slm_intent_t slm_classify_intent(const char *text, uint32_t text_len)
{
	uint16_t v, d;

	(void)text_len;
	/* A bare PCI id, or "what/identify ... pci/device" → identify. */
	if (parse_pci_id(text, &v, &d) &&
	    (contains(text, "what") || contains(text, "identif") ||
	     contains(text, "pci") || contains(text, "device")))
		return SLM_INTENT_HARDWARE_IDENTIFY;
	if (contains(text, "driver"))
		return SLM_INTENT_DRIVER_SELECT;
	if (contains(text, "network") || contains(text, "set up") ||
	    contains(text, "setup") || contains(text, "dhcp") ||
	    contains(text, "configure") || contains(text, "hostname"))
		return SLM_INTENT_INSTALL_CONFIGURE;
	if (contains(text, "install") || contains(text, "package"))
		return SLM_INTENT_APP_INSTALL;
	if (contains(text, "why") || contains(text, "down") ||
	    contains(text, "broken") || contains(text, "diagnos"))
		return SLM_INTENT_TROUBLESHOOT;
	if (contains(text, "memory") || contains(text, "disk") ||
	    contains(text, "usage") || contains(text, "status") ||
	    contains(text, "service"))
		return SLM_INTENT_SYSTEM_MANAGE;
	return SLM_INTENT_COUNT;        /* unclassified */
}

static void answer_identify(const char *text, slm_intent_result_t *r)
{
	uint16_t v, d;
	uint32_t p = 0;

	if (!parse_pci_id(text, &v, &d)) {
		append(r->response, R_CAP, 0,
		       "Give me a PCI id like 8086:100e and I'll identify it.");
		return;
	}
	const struct pci_driver_rule *e = kb_lookup(v, d);
	if (e) {
		p = append(r->response, R_CAP, p, e->name);
		p = append(r->response, R_CAP, p, ". Recommended driver: ");
		p = append(r->response, R_CAP, p, e->driver);
		p = append(r->response, R_CAP, p, ".");
	} else {
		p = append(r->response, R_CAP, p, "Unknown PCI device ");
		p = append_hex4(r->response, R_CAP, p, v);
		p = append(r->response, R_CAP, p, ":");
		p = append_hex4(r->response, R_CAP, p, d);
		p = append(r->response, R_CAP, p,
			   ". No matching driver in the knowledge base.");
	}
}

static void answer_driver(const char *text, slm_intent_result_t *r)
{
	uint16_t v, d;
	uint32_t p = 0;

	if (!parse_pci_id(text, &v, &d)) {
		append(r->response, R_CAP, 0,
		       "Name the device, e.g. 'driver for 8086:100e'.");
		return;
	}
	const struct pci_driver_rule *e = kb_lookup(v, d);
	if (e) {
		p = append(r->response, R_CAP, p, "Recommended driver: ");
		p = append(r->response, R_CAP, p, e->driver);
		p = append(r->response, R_CAP, p, ".");
	} else {
		append(r->response, R_CAP, 0,
		       "No driver known for that device.");
	}
}

int slm_process_text(const char *text, uint32_t text_len,
		     slm_intent_result_t *result)
{
	if (!result)
		return -1;
	kmemset(result, 0, sizeof(*result));
	result->status = 0;

	/* Neural backend (when a model is loaded): generate free-form text.
	 * On empty/failed generation, fall through to the rule engine so the
	 * chat never leaves the user without an answer (slm.md:639). */
	if (g_neural_active && slm_neural_available()) {
		uint32_t in_ids[64], out_ids[64];
		uint32_t nin = slm_neural_tokenize(text, text_len, in_ids, 64);
		if (nin > 0) {
			inference_config_t cfg = { 0.0f, 1.0f, 48, 1 };
			uint32_t nout = slm_neural_infer(in_ids, nin, out_ids,
							 64, &cfg);
			if (nout > 0) {
				slm_neural_detokenize(out_ids, nout,
						      result->response, R_CAP);
				result->response_len = kstrlen(result->response);
				if (result->response_len > 0)
					return 0;
			}
		}
		/* else: fall through to the deterministic rule engine. */
	}

	/* System queries answered directly from runtime state. */
	if (is_ip_query(text)) {
		result->intent = SLM_INTENT_SYSTEM_MANAGE;
		answer_ip(result);
		result->response_len = kstrlen(result->response);
		return 0;
	}

	slm_intent_t intent = slm_classify_intent(text, text_len);
	result->intent = intent;

	switch (intent) {
	case SLM_INTENT_HARDWARE_IDENTIFY:
		answer_identify(text, result);
		break;
	case SLM_INTENT_DRIVER_SELECT:
		answer_driver(text, result);
		break;
	case SLM_INTENT_INSTALL_CONFIGURE:
		append(result->response, R_CAP, 0,
		       "Plan: identify NIC -> load e1000 -> dhcp. "
		       "Say 'go' to proceed.");
		result->requires_followup = 1;
		break;
	case SLM_INTENT_APP_INSTALL:
		append(result->response, R_CAP, 0,
		       "Package install needs a filesystem and network, "
		       "which are roadmap in the seed.");
		break;
	case SLM_INTENT_SYSTEM_MANAGE:
		append(result->response, R_CAP, 0,
		       "Backend: rule-engine. Knowledge base loaded; "
		       "ask about a PCI device or driver.");
		break;
	case SLM_INTENT_TROUBLESHOOT:
		append(result->response, R_CAP, 0,
		       "Diagnostics: confirm the NIC driver is loaded and "
		       "DHCP completed. Full network stack is roadmap.");
		break;
	default:
		append(result->response, R_CAP, 0,
		       "I can identify PCI devices, recommend drivers, and "
		       "outline setup. Try: what is pci 8086:100e");
		break;
	}

	result->response_len = kstrlen(result->response);
	return 0;
}
