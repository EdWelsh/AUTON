/* See boot.S. Prints through the PL011 at the address the real dumped device
 * tree gives (tests/kernel/dtb_fixtures/virt.dtb: pl011@9000000), and checks
 * that X0 points at something with the FDT magic. */
#include <stdint.h>

#define PL011_BASE 0x09000000UL
#define UARTDR     0x00
#define UARTFR     0x18
#define UARTFR_TXFF (1u << 5)

#define FDT_MAGIC  0xd00dfeedu

static void putc_(char c)
{
	volatile uint32_t *fr = (volatile uint32_t *)(PL011_BASE + UARTFR);
	volatile uint32_t *dr = (volatile uint32_t *)(PL011_BASE + UARTDR);

	while (*fr & UARTFR_TXFF)
		;
	*dr = (uint32_t)c;
}

static void puts_(const char *s)
{
	for (; *s; s++) {
		if (*s == '\n')
			putc_('\r');
		putc_(*s);
	}
}

void smoke_main(uint64_t dtb);

void smoke_main(uint64_t dtb)
{
	const uint8_t *p = (const uint8_t *)dtb;
	uint32_t magic = dtb ? ((uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 |
	                        (uint32_t)p[2] << 8 | p[3]) : 0;

	puts_("[BOOT] aarch64 smoke\n");
	puts_(magic == FDT_MAGIC ? "[BOOT] dtb in x0\n" : "[BOOT] NO DTB IN X0\n");
	puts_("[BOOT] OK\n");
}
